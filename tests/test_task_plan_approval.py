import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from copia.api import service
from copia.data.invariants_repository import InvariantsRepository
from copia.data.sessions_repository import SessionsRepository
from copia.domain.models.config import LLMResponse
from copia.domain.models.task import (
    TaskPlan,
    TaskPlanStep,
    TaskPlanStepStatus,
    TaskStage,
    TaskState,
    TaskStatus,
    TaskValidationResult,
)
from copia.domain.services.task_state_machine import (
    InvalidTaskTransition,
    TaskEvent,
    TaskStateMachine,
)


def make_task() -> TaskState:
    return TaskState(
        id="task-1",
        original_instruction="Do the task",
        plan=TaskPlan(
            steps=[
                TaskPlanStep(
                    id="step-1",
                    order=1,
                    title="First",
                    instruction="First",
                    success_criteria="First is complete",
                ),
                TaskPlanStep(
                    id="step-2",
                    order=2,
                    title="Second",
                    instruction="Second",
                    success_criteria="Second is complete",
                ),
            ]
        ),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_plan_must_be_approved_before_execution() -> None:
    task = make_task()
    machine = TaskStateMachine()

    machine.apply(task, TaskEvent.PLAN_CREATED)

    assert task.stage == TaskStage.PLAN_REVIEW
    assert task.status == TaskStatus.WAITING_FOR_APPROVAL
    with pytest.raises(InvalidTaskTransition):
        machine.apply(task, TaskEvent.STEP_COMPLETED, next_step=1)

    machine.apply(task, TaskEvent.PLAN_APPROVED)
    assert task.stage == TaskStage.EXECUTION
    assert task.status == TaskStatus.RUNNING


def test_plan_creation_requires_a_plan() -> None:
    task = TaskState(
        id="task-1",
        original_instruction="Do the task",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with pytest.raises(InvalidTaskTransition):
        TaskStateMachine().apply(task, TaskEvent.PLAN_CREATED)


def test_strict_preconditions_reject_skips_and_unvalidated_completion() -> None:
    task = make_task()
    machine = TaskStateMachine()
    machine.apply(task, TaskEvent.PLAN_CREATED)
    machine.apply(task, TaskEvent.PLAN_APPROVED)

    with pytest.raises(InvalidTaskTransition):
        machine.apply(task, TaskEvent.STEP_COMPLETED, next_step=2)

    assert task.plan is not None
    task.plan.steps[0].status = TaskPlanStepStatus.COMPLETED
    machine.apply(task, TaskEvent.STEP_COMPLETED, next_step=1)
    task.plan.steps[1].status = TaskPlanStepStatus.COMPLETED
    machine.apply(task, TaskEvent.STEP_COMPLETED, next_step=2)

    with pytest.raises(InvalidTaskTransition):
        machine.apply(task, TaskEvent.VALIDATION_PASSED)
    task.validation_result = TaskValidationResult(
        passed=True,
        issues=[],
        checked_step_ids=["step-1"],
    )
    with pytest.raises(InvalidTaskTransition):
        machine.apply(task, TaskEvent.VALIDATION_PASSED)

    task.validation_result.checked_step_ids.append("step-2")
    machine.apply(task, TaskEvent.VALIDATION_PASSED)
    with pytest.raises(InvalidTaskTransition):
        machine.apply(task, TaskEvent.REPORT_SAVED)

    task.completion_report = "## Итоговый ответ\n\nDone"
    machine.apply(task, TaskEvent.REPORT_SAVED)
    assert task.stage == TaskStage.DONE
    assert task.status == TaskStatus.COMPLETED


class ApprovalTaskRouter:
    def __init__(self) -> None:
        self.plan_calls = 0
        self.execution_calls = 0
        self.planning_prompts: list[str] = []

    def complete(self, messages, config):
        properties = (
            config.structured_output.json_schema.get("properties", {})
            if config.structured_output is not None
            else {}
        )
        if "steps" in properties:
            self.plan_calls += 1
            self.planning_prompts.append(messages[-1].content)
            title = "Initial plan" if self.plan_calls == 1 else "Revised plan"
            data = {
                "steps": [
                    {
                        "title": title,
                        "instruction": "Complete the task",
                        "success_criteria": "The task is complete",
                    }
                ]
            }
            return LLMResponse(
                content=json.dumps(data),
                structured_data=data,
                provider=config.provider,
                model=config.model,
            )
        if "passed" in properties:
            data = {
                "passed": True,
                "issues": [],
                "checked_step_ids": ["step-1"],
                "checked_invariant_ids": [],
                "invariant_issues": [],
            }
            return LLMResponse(
                content=json.dumps(data),
                structured_data=data,
                provider=config.provider,
                model=config.model,
            )
        if any(
            message.role == "system" and "report writer" in message.content for message in messages
        ):
            return LLMResponse(
                content=(
                    "## Итоговый ответ\n\nDone\n\n### Детали\n\n"
                    "The task is complete.\n\n### Ограничения\n\nНет"
                ),
                provider=config.provider,
                model=config.model,
            )
        self.execution_calls += 1
        return LLMResponse(content="done", provider=config.provider, model=config.model)


def test_plan_review_waits_for_approval_and_replans_from_feedback(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service, "invariants_repository", InvariantsRepository(tmp_path / "invariants.json")
    )
    router = ApprovalTaskRouter()
    monkeypatch.setattr(service, "router", router)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service.app), base_url="http://test"
        ) as client:
            session = (
                await client.post(
                    "/sessions",
                    json={
                        "config": {"name": "Copia", "provider": "openai", "model": "test"},
                        "task_mode_enabled": True,
                    },
                )
            ).json()
            started = await client.post(
                f"/sessions/{session['id']}/tasks", json={"instruction": "Test task"}
            )
            task_id = started.json()["id"]
            review = await wait_for_status(client, session["id"], task_id, "waiting_for_approval")
            assert review["stage"] == "plan_review"
            assert router.execution_calls == 0

            changed = await client.post(
                f"/sessions/{session['id']}/tasks/{task_id}/request-plan-changes",
                json={"feedback": "Make the plan shorter"},
            )
            assert changed.status_code == 202
            assert changed.json()["stage"] == "planning"
            assert changed.json()["plan"] is None
            assert changed.json()["plan_feedback"] == "Make the plan shorter"

            revised = await wait_for_status(client, session["id"], task_id, "waiting_for_approval")
            assert revised["plan"]["steps"][0]["title"] == "Revised plan"
            assert "Make the plan shorter" in router.planning_prompts[-1]
            assert router.execution_calls == 0

            approved = await client.post(f"/sessions/{session['id']}/tasks/{task_id}/approve-plan")
            assert approved.status_code == 202
            completed = await wait_for_terminal(client, session["id"], task_id)
            assert completed["status"] == "completed"
            assert completed["stage"] == "done"
            assert router.execution_calls == 1

    asyncio.run(run())


async def wait_for_status(
    client: httpx.AsyncClient, session_id: str, task_id: str, status_value: str
) -> dict:
    for _ in range(100):
        task = (await client.get(f"/sessions/{session_id}/tasks/{task_id}")).json()
        if task["status"] == status_value:
            return task
        await asyncio.sleep(0.01)
    raise AssertionError(f"task did not reach {status_value}")


async def wait_for_terminal(client: httpx.AsyncClient, session_id: str, task_id: str) -> dict:
    for _ in range(100):
        task = (await client.get(f"/sessions/{session_id}/tasks/{task_id}")).json()
        if task["status"] in {"completed", "failed"}:
            return task
        await asyncio.sleep(0.01)
    raise AssertionError("task did not finish")

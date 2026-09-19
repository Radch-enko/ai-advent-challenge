import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from copia.api import service
from copia.data.agent_log_repository import JsonAgentLogRepository
from copia.data.agent_log_store import AgentLogStore
from copia.data.invariants_repository import InvariantsRepository
from copia.data.sessions_repository import SessionsRepository
from copia.domain.models.config import LLMResponse
from copia.domain.models.task import TaskStage, TaskState, TaskStatus
from copia.domain.services.task_state_machine import (
    InvalidTaskTransition,
    TaskEvent,
    TaskStateMachine,
)


class RetryTaskRouter:
    def __init__(self) -> None:
        self.validation_calls = 0
        self.execution_payloads: list[str] = []

    def complete(self, messages, config):
        properties = (
            config.structured_output.json_schema.get("properties", {})
            if config.structured_output is not None
            else {}
        )
        if "steps" in properties:
            data = {
                "steps": [
                    {
                        "title": "First",
                        "instruction": "Do the first step",
                        "success_criteria": "First is complete",
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
            self.validation_calls += 1
            data = {
                "passed": self.validation_calls > 1,
                "issues": [] if self.validation_calls > 1 else ["First is not complete"],
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
            content = (
                "## Итоговый ответ\n\nDone\n\n### Детали\n\n"
                "The requested task was completed.\n\n### Ограничения\n\nНет"
            )
            return LLMResponse(content=content, provider=config.provider, model=config.model)
        self.execution_payloads.append(messages[-1].content)
        return LLMResponse(content="done", provider=config.provider, model=config.model)


def test_retry_validation_restarts_execution_with_feedback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service, "invariants_repository", InvariantsRepository(tmp_path / "invariants.json")
    )
    monkeypatch.setattr(
        service,
        "agent_log_store",
        AgentLogStore(repository=JsonAgentLogRepository(tmp_path / "logs")),
    )
    router = RetryTaskRouter()
    monkeypatch.setattr(service, "router", router)

    async def run() -> None:
        transport = httpx.ASGITransport(app=service.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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
            await _wait_for_task_status(
                client, session["id"], started.json()["id"], "waiting_for_approval"
            )
            assert (
                await client.post(
                    f"/sessions/{session['id']}/tasks/{started.json()['id']}/approve-plan"
                )
            ).status_code == 202
            failed = await _wait_for_task(client, session["id"], started.json()["id"])

            assert failed["status"] == "failed"
            assert failed["stage"] == "validation"
            assert failed["validation_result"]["passed"] is False
            assert failed["validation_result"]["issues"] == ["First is not complete"]

            retried = await client.post(f"/sessions/{session['id']}/tasks/{failed['id']}/retry")
            assert retried.status_code == 202
            assert retried.json()["status"] == "running"
            assert retried.json()["stage"] == "execution"
            assert retried.json()["current_step"] == 0
            assert retried.json()["validation_result"]["issues"] == ["First is not complete"]
            assert all(step["status"] == "pending" for step in retried.json()["plan"]["steps"])

            completed = await _wait_for_task(client, session["id"], failed["id"])
            assert completed["status"] == "completed"
            assert completed["stage"] == "done"
            assert [call["kind"] for call in completed["llm_calls"]] == [
                "task_planning",
                "task_execution_step",
                "task_validation",
                "task_execution_step",
                "task_validation",
                "task_report",
            ]
            assert "First is not complete" in router.execution_payloads[1]
            stored = (await client.get(f"/sessions/{session['id']}")).json()
            step_messages = [
                message for message in stored["messages"] if message.get("task_step_id") == "step-1"
            ]
            assert len(step_messages) == 1

    asyncio.run(run())


def test_retry_execution_transition_requires_failed_validation() -> None:
    task = TaskState(
        id="task-1",
        original_instruction="Do the task",
        stage=TaskStage.EXECUTION,
        status=TaskStatus.FAILED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with pytest.raises(InvalidTaskTransition):
        TaskStateMachine().apply(task, TaskEvent.RETRY_EXECUTION)


async def _wait_for_task(client: httpx.AsyncClient, session_id: str, task_id: str) -> dict:
    for _ in range(100):
        task = (await client.get(f"/sessions/{session_id}/tasks/{task_id}")).json()
        if task["status"] in {"completed", "failed"}:
            return task
        await asyncio.sleep(0.01)
    raise AssertionError("task did not finish")


async def _wait_for_task_status(
    client: httpx.AsyncClient, session_id: str, task_id: str, status_value: str
) -> dict:
    for _ in range(100):
        task = (await client.get(f"/sessions/{session_id}/tasks/{task_id}")).json()
        if task["status"] == status_value:
            return task
        await asyncio.sleep(0.01)
    raise AssertionError(f"task did not reach {status_value}")

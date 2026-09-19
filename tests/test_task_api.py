import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from copia.api import service
from copia.data.invariants_repository import InvariantsRepository
from copia.data.pending_memory_repository import PendingMemoryRepository
from copia.data.sessions_repository import SessionsRepository
from copia.data.working_memory_repository import WorkingMemoryRepository
from copia.domain.models.config import LLMResponse
from copia.domain.models.session import ChatSession
from copia.domain.models.task import TaskStage, TaskState, TaskStatus


class FakeTaskRouter:
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
                    },
                    {
                        "title": "Second",
                        "instruction": "Do the second step",
                        "success_criteria": "Second is complete",
                    },
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
                "checked_step_ids": ["step-1", "step-2"],
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
        return LLMResponse(content="done", provider=config.provider, model=config.model)


def test_legacy_session_json_defaults_task_fields() -> None:
    session = ChatSession.model_validate_json(
        json.dumps(
            {
                "id": "session-1",
                "config": {"name": "Copia", "provider": "openai", "model": "test"},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )
    )
    assert session.task_mode_enabled is False
    assert session.task is None


def test_task_structured_output_schemas_are_strict() -> None:
    planner_schema = service._task_plan_schema()
    assert planner_schema["additionalProperties"] is False
    assert set(planner_schema["required"]) == set(planner_schema["properties"])

    planner_step_schema = planner_schema["$defs"]["_PlannerStep"]
    assert planner_step_schema["additionalProperties"] is False
    assert set(planner_step_schema["required"]) == set(planner_step_schema["properties"])

    validation_schema = service._task_validation_schema()
    assert validation_schema["additionalProperties"] is False
    assert set(validation_schema["required"]) == set(validation_schema["properties"])


def test_task_pipeline_persists_calls_and_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service, "invariants_repository", InvariantsRepository(tmp_path / "invariants.json")
    )
    monkeypatch.setattr(service, "router", FakeTaskRouter())

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
            assert started.status_code == 202
            review = await _wait_for_task_status(
                client, session["id"], started.json()["id"], "waiting_for_approval"
            )
            approved = await client.post(
                f"/sessions/{session['id']}/tasks/{review['id']}/approve-plan"
            )
            assert approved.status_code == 202
            task = await _wait_for_task(client, session["id"], started.json()["id"])
            assert task["status"] == "completed"
            assert task["stage"] == "done"
            assert len(task["llm_calls"]) == 5
            assert len({call["agent_log_id"] for call in task["llm_calls"]}) == 5
            stored = (await client.get(f"/sessions/{session['id']}")).json()
            assert len(stored["messages"]) == 4
            assert [message["role"] for message in stored["messages"]] == [
                "user",
                "assistant",
                "assistant",
                "assistant",
            ]
            assert all(message["task_id"] == task["id"] for message in stored["messages"])
            assert stored["messages"][-1]["agent_log_id"] == task["llm_calls"][-1]["agent_log_id"]
            for call in task["llm_calls"]:
                assert (
                    await client.get(f"/sessions/{session['id']}/agent-logs/{call['agent_log_id']}")
                ).status_code == 200

    asyncio.run(run())


def test_task_history_keeps_multiple_tasks_in_one_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service, "invariants_repository", InvariantsRepository(tmp_path / "invariants.json")
    )
    monkeypatch.setattr(service, "router", FakeTaskRouter())

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
            first = await client.post(
                f"/sessions/{session['id']}/tasks", json={"instruction": "First task"}
            )
            first_review = await _wait_for_task_status(
                client, session["id"], first.json()["id"], "waiting_for_approval"
            )
            assert (
                await client.post(
                    f"/sessions/{session['id']}/tasks/{first_review['id']}/approve-plan"
                )
            ).status_code == 202
            first_task = await _wait_for_task(client, session["id"], first.json()["id"])
            second = await client.post(
                f"/sessions/{session['id']}/tasks", json={"instruction": "Second task"}
            )
            second_review = await _wait_for_task_status(
                client, session["id"], second.json()["id"], "waiting_for_approval"
            )
            assert (
                await client.post(
                    f"/sessions/{session['id']}/tasks/{second_review['id']}/approve-plan"
                )
            ).status_code == 202
            second_task = await _wait_for_task(client, session["id"], second.json()["id"])

            stored = (await client.get(f"/sessions/{session['id']}")).json()
            assert [task["id"] for task in stored["tasks"]] == [
                first_task["id"],
                second_task["id"],
            ]
            assert stored["task"]["id"] == second_task["id"]
            assert [
                message["content"] for message in stored["messages"] if message["role"] == "user"
            ] == ["First task", "Second task"]
            assert {
                message["task_id"]
                for message in stored["messages"]
                if message["role"] == "assistant"
            } == {first_task["id"], second_task["id"]}

    asyncio.run(run())


def test_task_mode_off_preserves_regular_message_route(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service, "invariants_repository", InvariantsRepository(tmp_path / "invariants.json")
    )
    monkeypatch.setattr(service, "working_memory", WorkingMemoryRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service,
        "pending_memory_repository",
        PendingMemoryRepository(tmp_path / "sessions"),
    )
    monkeypatch.setattr(
        service,
        "router",
        type(
            "Router",
            (),
            {
                "complete": lambda self, messages, config: LLMResponse(
                    content="reply", provider=config.provider, model=config.model
                )
            },
        )(),
    )

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service.app), base_url="http://test"
        ) as client:
            session = (
                await client.post(
                    "/sessions",
                    json={"config": {"name": "Copia", "provider": "openai", "model": "test"}},
                )
            ).json()
            response = await client.post(
                f"/sessions/{session['id']}/messages", json={"content": "hello"}
            )
            assert response.status_code == 200
            assert (
                await client.post(f"/sessions/{session['id']}/tasks", json={"instruction": "x"})
            ).status_code == 409

    asyncio.run(run())


def test_active_task_rejects_regular_message(monkeypatch, tmp_path: Path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    monkeypatch.setattr(
        service, "invariants_repository", InvariantsRepository(tmp_path / "invariants.json")
    )

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
            stored = repository.load(session["id"])
            assert stored is not None
            now = datetime.now(UTC)
            stored.task = TaskState(
                id="task-1",
                original_instruction="active",
                status=TaskStatus.RUNNING,
                stage=TaskStage.PLANNING,
                created_at=now,
                updated_at=now,
            )
            repository.save(stored)
            response = await client.post(
                f"/sessions/{session['id']}/messages", json={"content": "hello"}
            )
            assert response.status_code == 409

    asyncio.run(run())


async def _wait_for_task(client: httpx.AsyncClient, session_id: str, task_id: str) -> dict:
    for _ in range(80):
        task = (await client.get(f"/sessions/{session_id}/tasks/{task_id}")).json()
        if task["status"] in {"completed", "failed"}:
            return task
        await asyncio.sleep(0.01)
    raise AssertionError("task did not finish")


async def _wait_for_task_status(
    client: httpx.AsyncClient, session_id: str, task_id: str, status_value: str
) -> dict:
    for _ in range(80):
        task = (await client.get(f"/sessions/{session_id}/tasks/{task_id}")).json()
        if task["status"] == status_value:
            return task
        await asyncio.sleep(0.01)
    raise AssertionError(f"task did not reach {status_value}")

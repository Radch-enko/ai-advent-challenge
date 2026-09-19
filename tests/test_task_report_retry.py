import asyncio
import json
from pathlib import Path

import httpx

from copia.api import service
from copia.data.agent_log_repository import JsonAgentLogRepository
from copia.data.agent_log_store import AgentLogStore
from copia.data.invariants_repository import InvariantsRepository
from copia.data.sessions_repository import SessionsRepository
from copia.domain.models.config import LLMResponse


class MalformedThenValidReportRouter:
    def __init__(self) -> None:
        self.report_calls = 0
        self.report_prompts: list[str] = []

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
                        "title": "Complete the task",
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
            self.report_calls += 1
            self.report_prompts.append(messages[-1].content)
            if self.report_calls == 1:
                content = (
                    "## Итоговый ответ\n\nDone\n\n### Детали\n\n"
                    "The task is complete.\n\n### Ограничения\n\nНет\n\n"
                    "### Рекомендации\n\nKeep going."
                )
            else:
                content = (
                    "## Итоговый ответ\n\nDone\n\n### Детали\n\n"
                    "The task is complete.\n\n### Ограничения\n\nНет"
                )
            return LLMResponse(content=content, provider=config.provider, model=config.model)
        return LLMResponse(content="done", provider=config.provider, model=config.model)


def test_task_retries_report_when_model_adds_an_extra_heading(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service, "invariants_repository", InvariantsRepository(tmp_path / "invariants.json")
    )
    monkeypatch.setattr(
        service,
        "agent_log_store",
        AgentLogStore(repository=JsonAgentLogRepository(tmp_path / "logs")),
    )
    router = MalformedThenValidReportRouter()
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
            await wait_for_status(client, session["id"], task_id, "waiting_for_approval")
            approved = await client.post(f"/sessions/{session['id']}/tasks/{task_id}/approve-plan")
            assert approved.status_code == 202

            completed = await wait_for_terminal(client, session["id"], task_id)
            assert completed["status"] == "completed"
            assert completed["stage"] == "done"
            assert completed["completion_report"].startswith("## Итоговый ответ")
            assert router.report_calls == 2
            assert "format correction attempt" in router.report_prompts[1]
            assert [call["kind"] for call in completed["llm_calls"]] == [
                "task_planning",
                "task_execution_step",
                "task_validation",
                "task_report",
                "task_report",
            ]

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

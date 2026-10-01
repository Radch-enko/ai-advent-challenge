from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from copia import service
from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.providers.domain.models.llm_response import LLMResponse
from copia.sessions.data.sessions_repository import SessionsRepository


class FakeTaskRouter:
    def __init__(self) -> None:
        self.messages_by_call = []

    def complete(self, messages, config):
        self.messages_by_call.append(messages)
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
                        "instruction": "Fetch release facts",
                        "success_criteria": "The release facts are recorded",
                    },
                    {
                        "title": "Second",
                        "instruction": "Review platform limits",
                        "success_criteria": "The platform limits are recorded",
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
            "report writer" in message.content for message in messages if message.role == "system"
        ):
            content = (
                "## Итоговый ответ\n\nDone\n\n### Детали\n\n"
                "The requested task was completed.\n\n### Ограничения\n\nНет"
            )
            return LLMResponse(content=content, provider=config.provider, model=config.model)
        return LLMResponse(content="done", provider=config.provider, model=config.model)


def test_task_retrieves_again_for_each_llm_stage_and_saves_sources(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service,
        "invariants_repository",
        InvariantsRepository(tmp_path / "invariants.json"),
    )
    router = FakeTaskRouter()
    monkeypatch.setattr(service, "router", router)
    retrieval_queries: list[str] = []

    def retrieve(query: str) -> RetrievedChunk:
        retrieval_queries.append(query)
        return RetrievedChunk(
            text=f"Evidence for {query}",
            source=KnowledgeSource(
                chunk_id=f"chunk-{len(retrieval_queries)}",
                source="guide.md",
                title="Guide",
                section="Facts",
            ),
        )

    monkeypatch.setattr(service.document_indexing_composition.retriever, "retrieve", retrieve)

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
                        "rag_enabled": True,
                    },
                )
            ).json()
            started = await client.post(
                f"/sessions/{session['id']}/tasks", json={"instruction": "Task request"}
            )
            assert started.status_code == 202
            task_id = started.json()["id"]
            await wait_for_status(client, session["id"], task_id, "waiting_for_approval")
            approved = await client.post(f"/sessions/{session['id']}/tasks/{task_id}/approve-plan")
            assert approved.status_code == 202
            task = await wait_for_status(client, session["id"], task_id, "completed")
            saved_session = (await client.get(f"/sessions/{session['id']}")).json()

            assert task["rag_enabled"] is True
            assert retrieval_queries == [
                "Task request",
                "Fetch release facts",
                "Review platform limits",
                "Task request",
                "Task request",
            ]
            assert len(router.messages_by_call) == 5
            assert all(
                "untrusted reference data" in messages[0].content
                for messages in router.messages_by_call
            )
            assert [call["sources"][0]["chunk_id"] for call in task["llm_calls"]] == [
                "chunk-1",
                "chunk-2",
                "chunk-3",
                "chunk-4",
                "chunk-5",
            ]
            assert [
                message["sources"][0]["chunk_id"]
                for message in saved_session["messages"]
                if message["role"] == "assistant"
            ] == ["chunk-2", "chunk-3", "chunk-5"]

    asyncio.run(run())


async def wait_for_status(client: httpx.AsyncClient, session_id: str, task_id: str, expected: str):
    for _ in range(200):
        response = await client.get(f"/sessions/{session_id}/tasks/{task_id}")
        task = response.json()
        if task["status"] == expected:
            return task
        await asyncio.sleep(0.01)
    raise AssertionError(f"task did not reach {expected}")

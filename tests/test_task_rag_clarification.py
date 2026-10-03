from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from copia import service
from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.document_indexing.domain.models.rag_retrieval_result import RagRetrievalResult
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.providers.domain.models.llm_response import LLMResponse
from copia.sessions.data.sessions_repository import SessionsRepository

QUOTE = "Synthetic evidence supports the sample task."


class StrictTaskRouter:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, config):
        self.calls += 1
        properties = config.structured_output.json_schema["properties"]
        if "steps" in properties:
            chunk = _first_context_chunk(messages)
            data = {
                "answer": f'The plan uses this evidence: "{QUOTE}"',
                "citations": [{"chunk_id": chunk["chunk_id"], "quote": QUOTE}],
                "steps": [
                    {
                        "title": "Record sample evidence",
                        "instruction": "Record the synthetic evidence",
                        "success_criteria": "The synthetic evidence is recorded",
                    }
                ],
            }
        elif "passed" in properties:
            data = {
                "passed": True,
                "issues": [],
                "checked_step_ids": ["step-1"],
                "checked_invariant_ids": [],
                "invariant_issues": [],
            }
        else:
            chunk = _first_context_chunk(messages)
            is_report = any(
                "report writer" in message.content
                for message in messages
                if message.role == "system"
            )
            answer = (
                "## Итоговый ответ\n\nDone\n\n### Детали\n\n"
                f'The sample task used this evidence: "{QUOTE}"\n\n### Ограничения\n\nНет'
                if is_report
                else f'The sample task used this evidence: "{QUOTE}"'
            )
            data = {
                "answer": answer,
                "citations": [{"chunk_id": chunk["chunk_id"], "quote": QUOTE}],
            }
        return LLMResponse(
            content=json.dumps(data, ensure_ascii=False),
            structured_data=data,
            provider=config.provider,
            model=config.model,
        )


def _first_context_chunk(messages):
    context = next(
        message.content
        for message in messages
        if "Retrieved document excerpts (JSON):\n" in message.content
    )
    context_json = context.split("Retrieved document excerpts (JSON):\n", 1)[1]
    return json.JSONDecoder().raw_decode(context_json)[0][0]


@pytest.mark.parametrize("missing_context_on_call", [1, 2, 3, 4])
def test_task_stops_and_requests_clarification_when_any_stage_has_no_context(
    monkeypatch, tmp_path: Path, missing_context_on_call: int
) -> None:
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service,
        "invariants_repository",
        InvariantsRepository(tmp_path / "invariants.json"),
    )
    router = StrictTaskRouter()
    monkeypatch.setattr(service, "router", router)
    retrieval_queries: list[str] = []

    def retrieve(query: str, settings=None, **kwargs) -> RagRetrievalResult:
        retrieval_queries.append(query)
        if len(retrieval_queries) == missing_context_on_call:
            return RagRetrievalResult()
        chunk = RetrievedChunk(
            text=QUOTE,
            source=KnowledgeSource(
                chunk_id=f"fixture-{len(retrieval_queries)}",
                source="sample-notebook.md",
                title="Sample Notebook",
                section="Task evidence",
            ),
        )
        return RagRetrievalResult.from_single_chunk(chunk)

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
                f"/sessions/{session['id']}/tasks",
                json={"instruction": "Complete the synthetic notebook task"},
            )
            assert started.status_code == 202
            task_id = started.json()["id"]

            if missing_context_on_call > 1:
                await wait_for_status(client, session["id"], task_id, "waiting_for_approval")
                approved = await client.post(
                    f"/sessions/{session['id']}/tasks/{task_id}/approve-plan"
                )
                assert approved.status_code == 202

            task = await wait_for_status(client, session["id"], task_id, "needs_clarification")
            saved_session = (await client.get(f"/sessions/{session['id']}")).json()
            assistant_messages = [
                message
                for message in saved_session["messages"]
                if message["role"] == "assistant" and message.get("task_id") == task_id
            ]

            assert task["status"] == "needs_clarification"
            assert task["expected_action"] == "Create a new task after clarifying the request"
            assert len(retrieval_queries) == missing_context_on_call
            assert router.calls == missing_context_on_call - 1
            assert len(assistant_messages) >= 1
            assert assistant_messages[-1]["content"] == "Не знаю. Уточните вопрос."
            assert assistant_messages[-1]["sources"] == []
            assert all(call["status"] == "completed" for call in task["llm_calls"])
            if missing_context_on_call == 3:
                assert task["plan"]["steps"][0]["status"] == "completed"
                assert len(assistant_messages) == 2
            if missing_context_on_call == 4:
                assert task["plan"]["steps"][0]["status"] == "completed"
                assert task["validation_result"]["passed"] is True
                assert len(assistant_messages) == 2

    asyncio.run(run())


async def wait_for_status(client: httpx.AsyncClient, session_id: str, task_id: str, expected: str):
    for _ in range(200):
        response = await client.get(f"/sessions/{session_id}/tasks/{task_id}")
        task = response.json()
        if task["status"] == expected:
            return task
        await asyncio.sleep(0.01)
    raise AssertionError(f"task did not reach {expected}")

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from copia import service
from copia.agent_logs.data.agent_log_repository import JsonAgentLogRepository
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agent_logs.domain.models.agent_log_exchange import AgentLogExchange
from copia.scheduled_jobs.data.scheduled_runs_repository import ScheduledRunsRepository
from copia.scheduled_jobs.domain.models.scheduled_run import ScheduledRun


def test_scheduled_log_endpoint_uses_the_displayed_run(monkeypatch, tmp_path) -> None:
    runs = ScheduledRunsRepository(tmp_path / "runs")
    logs = AgentLogStore(repository=JsonAgentLogRepository(tmp_path / "sessions"))
    scheduled_at = datetime(2026, 9, 25, 7, 28, tzinfo=UTC)
    session_id = "scheduled-summary"
    log_id = logs.start_turn(session_id)
    logs.append(
        AgentLogExchange(
            id="provider-request",
            agent_turn_id=log_id,
            session_id=session_id,
            operation="primary",
            provider="openai",
            model="test-model",
            method="POST",
            url="https://provider.example/chat",
            request_headers={},
            request_body=b'{"messages":[{"role":"tool","content":"expense"}]}',
            response_headers={},
            response_body=b'{"answer":"report"}',
            status_code=200,
            duration_seconds=0.01,
            created_at=scheduled_at,
        )
    )
    logs.finish_turn(log_id, status="completed")
    runs.save(
        ScheduledRun(
            job_id="summary",
            kind="expense_summary",
            scheduled_at=scheduled_at,
            period_from=scheduled_at - timedelta(hours=1),
            period_to=scheduled_at,
            status="completed",
            answer="report",
            agent_log_id=log_id,
            started_at=scheduled_at,
            finished_at=scheduled_at,
        )
    )
    runs.save(
        ScheduledRun(
            job_id="summary",
            kind="expense_summary",
            scheduled_at=scheduled_at + timedelta(minutes=1),
            period_from=scheduled_at,
            period_to=scheduled_at + timedelta(minutes=1),
            status="failed",
            error="provider failed",
            started_at=scheduled_at,
            finished_at=scheduled_at,
        )
    )
    monkeypatch.setattr(service, "scheduled_runs", runs)
    monkeypatch.setattr(service, "agent_log_store", logs)
    monkeypatch.setattr(service, "scheduled_runner", SimpleNamespace(jobs={"summary": object()}))

    client = TestClient(service.app)
    response = client.get("/scheduled-jobs/summary/runs/2026-09-25T07:28:00Z/log")
    assert response.status_code == 200
    body = response.json()
    assert body["agent_log_id"] == log_id
    assert body["exchanges"][0]["request_body"]["content"] == (
        '{"messages":[{"role":"tool","content":"expense"}]}'
    )
    assert client.get("/scheduled-jobs/summary/runs/2026-09-25T07:27:00Z/log").status_code == 404
    assert client.get("/scheduled-jobs/other/runs/2026-09-25T07:28:00Z/log").status_code == 404

from __future__ import annotations

import asyncio
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from copia.agent_logs.api.mappers.agent_log_response import (
    agent_log_body,
    agent_log_exchange_response,
)
from copia.agent_logs.api.mappers.agent_log_response import (
    agent_log_response as _agent_log_response,
)
from copia.agent_logs.api.routes import AgentLogRoutes
from copia.agent_logs.data.agent_log_repository import JsonAgentLogRepository
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agents.api.agent_route_runtime import AgentRouteRuntime
from copia.agents.api.routes import AgentRoutes
from copia.agents.data.profiles_repository import ProfilesRepository
from copia.agents.domain.models.agent import Agent, AgentFactory
from copia.expenses.api.router import create_expenses_router
from copia.expenses.api.validation import expense_validation_error_response
from copia.expenses.data.expenses_repository import ExpensesRepository
from copia.invariants.api.router import create_invariants_router
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.mcp.api.discovery import mcp_header
from copia.mcp.api.router import create_mcp_router
from copia.mcp.api.service_composition import McpServiceComposition
from copia.mcp.application.models.mcp_turn_runtime import McpTurnRuntime
from copia.mcp.data.mcp_client import call_mcp_tool as call_mcp_tool
from copia.mcp.data.mcp_client import discover_mcp_tools
from copia.mcp.data.mcp_connections_repository import McpConnectionsRepository
from copia.profile_memory.api.errors import memory_storage_error as _memory_storage_error
from copia.profile_memory.api.router import create_profile_memory_router
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.providers.api.provider_route_runtime import ProviderRouteRuntime
from copia.providers.api.routes import ProviderRoutes
from copia.providers.application.llm_router import LLMRouter
from copia.providers.data.llm import ProviderError
from copia.providers.data.model_catalog import context_window_for
from copia.providers.domain.models.provider_name import ProviderName
from copia.scheduled_jobs.api.router import create_scheduled_jobs_router
from copia.scheduled_jobs.api.service_composition import ScheduledSummaryServiceComposition
from copia.scheduled_jobs.application.scheduled_runner import ScheduledRunner
from copia.scheduled_jobs.data.scheduled_runs_repository import ScheduledRunsRepository
from copia.scheduled_jobs.domain.services import expense_summary_prompt
from copia.security.domain.services.credential_sanitizer import sanitize_value
from copia.session_memory.api.models.long_term_memory_mutation_response import (
    LongTermMemoryMutationResponse,
)
from copia.session_memory.api.service_composition import SessionMemoryServiceComposition
from copia.session_memory.application.approved_memory_mutation_cache import (
    ApprovedMemoryMutationCache,
)
from copia.session_memory.application.session_memory_access import SessionMemoryAccess
from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.session_memory.domain.services.llm_memory_classifier import (
    LLMMemoryClassifier as LLMMemoryClassifier,
)
from copia.sessions.api.message_response_mapper import make_session_message_response
from copia.sessions.api.message_sanitizer import (
    safe_facts_events,
    safe_memory_events,
    safe_summarization_events,
    safe_trace,
    session_failure_trace,
)
from copia.sessions.api.service_composition import SessionServiceComposition
from copia.sessions.application.models.session_lock_state import (
    SessionLockState as _SessionLockState,
)
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.tasks.api.routes import TaskRoutes
from copia.tasks.api.service_composition import TaskServiceComposition
from copia.tasks.application.models.task_mcp_approval_runtime import (
    TaskMcpApprovalRuntime as _TaskMcpApprovalRuntime,
)
from copia.tasks.domain.services import task_prompt, task_text
from copia.tasks.domain.services import task_state_rules as task_state_rules
from copia.tasks.domain.services.task_state_machine import TaskStateMachine
from copia.user_profiles.api.router import create_user_profiles_router
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository

load_dotenv()

_mcp_header = mcp_header
session_composition = SessionServiceComposition.from_service(sys.modules[__name__])
session_memory_composition = SessionMemoryServiceComposition.from_service(sys.modules[__name__])
scheduled_summary_composition = ScheduledSummaryServiceComposition.from_service(
    sys.modules[__name__]
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
data_root = Path(os.getenv("COPIA_DATA_ROOT", "~/.copia"))
profiles_path = Path(os.getenv("COPIA_PROFILES_PATH", PROJECT_ROOT / "profiles.json"))
sessions_path = Path(os.getenv("COPIA_SESSIONS_PATH", data_root / "sessions"))
invariants_path = Path(os.getenv("COPIA_INVARIANTS_PATH", sessions_path.parent / "invariants.json"))
agent_log_store = AgentLogStore(repository=JsonAgentLogRepository(sessions_path))
router = LLMRouter(agent_log_store=agent_log_store)
factory = AgentFactory(router, ProfilesRepository(profiles_path))
agents: dict[str, Agent] = {}
sessions = SessionsRepository(sessions_path)
profile_memory = ProfileMemoryRepository(Path(os.getenv("COPIA_MEMORY_PATH", data_root / "memory")))
working_memory = WorkingMemoryRepository(sessions_path)
pending_memory: dict[str, list[PendingMemorySuggestion]] = {}
pending_memory_repository = PendingMemoryRepository(sessions_path)
session_memory_access = SessionMemoryAccess(
    lambda: working_memory,
    lambda: pending_memory_repository,
)
invariants_repository = InvariantsRepository(
    invariants_path,
    legacy_sessions_root=sessions_path,
)
user_profiles = JsonUserProfilesRepository(data_root / "user_profiles.json")
expenses = ExpensesRepository(
    Path(os.getenv("COPIA_EXPENSES_PATH", data_root / "files/finances.xlsx"))
)
mcp_connections = McpConnectionsRepository(
    Path(os.getenv("COPIA_MCP_CONNECTIONS_PATH", data_root / "mcp_connections.json"))
)
session_lifecycle_lock = threading.RLock()
task_state_machine = TaskStateMachine()
task_workers: dict[str, asyncio.Task[None]] = {}
task_workers_lock = threading.RLock()
scheduled_runs = ScheduledRunsRepository(
    Path(os.getenv("COPIA_SCHEDULED_RUNS_PATH", data_root / "scheduled-runs"))
)
scheduled_runner = ScheduledRunner(
    Path(os.getenv("COPIA_SCHEDULES_PATH", data_root / "schedules.json")),
    Path(os.getenv("COPIA_SCHEDULER_STATE_PATH", data_root / "scheduler-state.json")),
    scheduled_runs,
    {"expense_summary": lambda job, start, end: _expense_summary_job(job, start, end)},
)


mcp_turns: dict[str, McpTurnRuntime] = {}
mcp_turns_lock = threading.RLock()
mcp_turn_workers: dict[str, asyncio.Task[None]] = {}
mcp_composition = McpServiceComposition.from_service(sys.modules[__name__])
mcp_turn_state = mcp_composition.turn_state


task_mcp_approvals: dict[str, _TaskMcpApprovalRuntime] = {}
task_mcp_approvals_lock = threading.RLock()


session_message_locks: dict[str, _SessionLockState] = {}
MAX_APPROVED_MEMORY_MUTATIONS = 1024
approved_memory_cache = ApprovedMemoryMutationCache[LongTermMemoryMutationResponse](
    MAX_APPROVED_MEMORY_MUTATIONS
)
approved_memory_mutations = approved_memory_cache.entries


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduled_runner.start()
    try:
        yield
    finally:
        scheduled_runner.shutdown()


app = FastAPI(title="Copia API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    if request.url.path == "/expenses":
        return expense_validation_error_response(error)
    return await request_validation_exception_handler(request, error)


def provider_error_detail(
    error: ProviderError, *, redact_request: bool = False
) -> dict[str, object]:
    return {
        "message": "Provider request failed",
        "provider_trace": {
            "status_code": error.status_code,
            "request_body": sanitize_value(error.request_body),
            "response_body": sanitize_value(error.response_body),
        },
    }


_session_message_response = make_session_message_response
_agent_log_body = agent_log_body
_agent_log_exchange_response = agent_log_exchange_response


_safe_trace = safe_trace
_safe_summarization_events = safe_summarization_events
_safe_facts_events = safe_facts_events
_safe_memory_events = safe_memory_events
_session_failure_trace = session_failure_trace


TASK_REPORT_SECTIONS = task_text.TASK_REPORT_SECTIONS
TASK_REPORT_MAX_ATTEMPTS = task_text.TASK_REPORT_MAX_ATTEMPTS


task_composition = TaskServiceComposition.from_service(sys.modules[__name__])
task_state_access = task_composition.state_access
task_mcp_lifecycle = task_composition.mcp_lifecycle
task_workflow = task_composition.workflow
_task_system_messages = task_composition.system_messages
_task_checkpoint = task_composition.checkpoint
_session_task = task_composition.session_task
_task_call_start = task_composition.call_start
_task_call_finish = task_composition.call_finish
_request_task_mcp_approval = task_mcp_lifecycle.request_approval
_recover_orphaned_task = task_composition.recover_orphaned_task
_task_plan_schema = task_prompt.plan_schema
_task_validation_schema = task_prompt.validation_schema
_task_plan_payload = task_text._task_plan_payload
_task_execution_payload = task_text._task_execution_payload
_task_validation_payload = task_text._task_validation_payload
_finalize_task_validation = task_text._finalize_task_validation
_task_report_payload = task_text._task_report_payload
_valid_task_report = task_text._valid_task_report
_task_complete_call = task_workflow.complete_call
_run_task = task_workflow.run_task
_run_task_planning = task_workflow.run_planning
_run_task_execution = task_workflow.run_execution
_run_task_validation = task_workflow.run_validation
_run_task_report = task_workflow.run_report
_start_task_worker = task_workflow.start_worker


app.include_router(create_expenses_router(lambda: expenses))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


_discover_connection = mcp_composition.discover_connection
_connection_is_used = mcp_composition.connection_is_used


app.include_router(
    create_mcp_router(
        lambda: mcp_connections,
        lambda: discover_mcp_tools,
        lambda: _discover_connection,
        _connection_is_used,
    )
)


def _agent_route_runtime() -> AgentRouteRuntime:
    return AgentRouteRuntime(
        factory=factory,
        router=router,
        invariants=invariants_repository,
        profile_memory=profile_memory,
        agents=agents,
        threadpool=run_in_threadpool,
        make_agent=Agent,
        context_window_for=context_window_for,
        provider_error_detail=provider_error_detail,
        memory_storage_error=_memory_storage_error,
    )


agent_routes = AgentRoutes(_agent_route_runtime)
app.include_router(agent_routes.profiles_router())
profiles = agent_routes.profiles


app.include_router(
    create_profile_memory_router(
        lambda: profile_memory, lambda: factory.profiles(), lambda: run_in_threadpool
    )
)


session_message_errors = session_composition.message_errors()
_session_initialization_error = session_message_errors.initialization_error
turn_profile_loader = session_composition.turn_profile_loader()
_load_user_profile_for_turn = turn_profile_loader.load


def _provider_route_runtime() -> ProviderRouteRuntime:
    return ProviderRouteRuntime(
        router=router,
        invariants=invariants_repository,
        threadpool=run_in_threadpool,
        provider_error_detail=provider_error_detail,
        memory_storage_error=_memory_storage_error,
    )


provider_routes = ProviderRoutes(_provider_route_runtime)
app.include_router(provider_routes.router())
capabilities = provider_routes.capabilities
models = provider_routes.models
completion = provider_routes.completion


app.include_router(agent_routes.create_message_router())
create_agent = agent_routes.create_agent
send_message = agent_routes.send_message


task_recovery = task_composition.recovery
_recover_orphaned_session_tasks = task_recovery.recover_session_tasks


session_collection_routes = session_composition.collection_routes()
app.include_router(session_collection_routes.list_router())
app.include_router(create_user_profiles_router(lambda: user_profiles, lambda: sessions))
app.include_router(session_collection_routes.detail_router())

list_sessions = session_collection_routes.list_sessions
create_session = session_collection_routes.create_session
get_session = session_collection_routes.get_session


task_routes = TaskRoutes(task_composition.api_runtime)
app.include_router(task_routes.router())
update_session_task_mode = task_routes.update_session_task_mode
start_task = task_routes.start_task
get_task = task_routes.get_task
approve_task_plan = task_routes.approve_task_plan
request_task_plan_changes = task_routes.request_task_plan_changes
pause_task = task_routes.pause_task
resume_task = task_routes.resume_task
retry_task = task_routes.retry_task


session_access = session_composition.access()
_get_session_locked = session_access.get_session_locked
_get_session = session_access.get_session
_recover_interrupted_mcp_turn = session_access.recover_interrupted_mcp_turn
_session_message_lock = session_access.session_message_lock
_release_session_message_lock = session_access.release_session_message_lock
_session_mutation_lock = session_access.session_mutation_lock


session_settings_routes = session_composition.settings_routes()
app.include_router(session_settings_routes.facts_router())
get_session_facts = session_settings_routes.get_session_facts


app.include_router(create_invariants_router(lambda: invariants_repository, _get_session))


app.include_router(session_settings_routes.settings_router())
update_session_context_management = session_settings_routes.update_session_context_management
update_session_user_profile = session_settings_routes.update_session_user_profile
update_session_long_term_memory = session_settings_routes.update_session_long_term_memory
_update_session_long_term_memory = session_settings_routes._update_session_long_term_memory
fork_session = session_settings_routes.fork_session


session_message_routes = session_composition.message_routes()
app.include_router(session_message_routes.send_router())
send_session_message = session_message_routes.send_session_message
_send_session_message_locked = session_message_routes._send_session_message_locked


_turn_response = mcp_composition.turn_response
_emit_turn = mcp_composition.emit_turn
_persist_mcp_turn_state = mcp_composition.persist_turn_state
mcp_tool_resolver = mcp_composition.tool_resolver
_resolved_mcp_tools = mcp_composition.resolved_tools
_turn_approval = mcp_composition.turn_approval
mcp_tool_executor = mcp_composition.tool_executor
_execute_resolved_tool = mcp_composition.execute_resolved_tool


_expense_period_label = expense_summary_prompt.expense_period_label
_expense_report_timezone = expense_summary_prompt.expense_report_timezone
expense_summary_job = scheduled_summary_composition.job
_expense_summary_job = expense_summary_job.run


mcp_turn_worker = mcp_composition.turn_worker
_run_mcp_turn = mcp_turn_worker.run
mcp_turn_routes = mcp_composition.turn_routes
app.include_router(mcp_turn_routes.router())
start_mcp_turn = mcp_turn_routes.start_mcp_turn
_require_mcp_turn = mcp_turn_routes.require_turn
get_mcp_turn = mcp_turn_routes.get_mcp_turn
stream_mcp_turn_events = mcp_turn_routes.stream_mcp_turn_events
decide_mcp_approval = mcp_turn_routes.decide_mcp_approval


agent_log_routes = AgentLogRoutes(
    lambda: _get_session,
    lambda: agent_log_store,
    lambda: run_in_threadpool,
)
app.include_router(agent_log_routes.router())
get_agent_log = agent_log_routes.get_agent_log


app.include_router(
    create_scheduled_jobs_router(
        lambda: scheduled_runner,
        lambda: scheduled_runs,
        lambda: agent_log_store,
        _agent_log_response,
    )
)


app.include_router(session_message_routes.retry_router())
retry_session_summarization = session_message_routes.retry_session_summarization


session_deletion_routes = session_composition.deletion_routes()
app.include_router(session_deletion_routes.router())
delete_session = session_deletion_routes.delete_session


working_memory_routes = session_memory_composition.working_routes()
pending_memory_routes = session_memory_composition.pending_routes()
app.include_router(working_memory_routes.router())
app.include_router(pending_memory_routes.router())

list_working_memory = working_memory_routes.list_working_memory
update_working_memory = working_memory_routes.update_working_memory
_update_working_memory = working_memory_routes._update_working_memory
delete_working_memory = working_memory_routes.delete_working_memory
_delete_working_memory = working_memory_routes._delete_working_memory
clear_working_memory = working_memory_routes.clear_working_memory
_clear_working_memory = working_memory_routes._clear_working_memory
undo_working_memory = working_memory_routes.undo_working_memory
_undo_working_memory = working_memory_routes._undo_working_memory
list_pending_memory = pending_memory_routes.list_pending_memory
approve_memory = pending_memory_routes.approve_memory
_approve_memory = pending_memory_routes._approve_memory
reject_memory = pending_memory_routes.reject_memory
_reject_memory = pending_memory_routes._reject_memory


app.include_router(agent_routes.delete_router())
delete_agent = agent_routes.delete_agent


session_title_generator = session_composition.title_generator()
generate_session_title = session_title_generator.generate


session_agent_execution = session_composition.agent_execution()
_save_agent_state = session_agent_execution.save_agent_state
_ask_agent = session_agent_execution.ask_agent
_retry_agent = session_agent_execution.retry_agent


def _finish_agent_log(
    agent_log_id: str,
    *,
    provider: ProviderName | None = None,
    model: str | None = None,
    usage: dict[str, int] | None = None,
    status: str,
    error: str | None = None,
) -> None:
    agent_log_store.finish_turn(
        agent_log_id,
        provider=provider,
        model=model,
        usage=usage,
        status=status,
        error=error,
    )


session_long_term_memory_access = session_composition.long_term_memory_access()
_long_term_memory_for_session = session_long_term_memory_access.for_session


def run() -> None:
    import uvicorn

    uvicorn.run("copia.service:app", host="127.0.0.1", port=8000, reload=False)

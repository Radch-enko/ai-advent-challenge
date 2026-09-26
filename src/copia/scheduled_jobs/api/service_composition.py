from __future__ import annotations

from types import ModuleType
from typing import Self

from copia.agents.data.profiles_repository import ProfilesRepository
from copia.scheduled_jobs.api.models.scheduled_summary_service_bindings import (
    ScheduledSummaryServiceBindings,
)
from copia.scheduled_jobs.application.expense_summary_job import ExpenseSummaryJob
from copia.scheduled_jobs.application.expense_summary_runtime import ExpenseSummaryRuntime
from copia.security.domain.services.credential_sanitizer import sanitize_error


class ScheduledSummaryServiceComposition:
    @classmethod
    def from_service(cls, service: ModuleType) -> Self:
        return cls(
            ScheduledSummaryServiceBindings(
                Agent=lambda: service.Agent,
                _execute_resolved_tool=lambda: service._execute_resolved_tool,
                _finish_agent_log=lambda: service._finish_agent_log,
                _resolved_mcp_tools=lambda: service._resolved_mcp_tools,
                agent_log_store=lambda: service.agent_log_store,
                profiles_path=lambda: service.profiles_path,
                router=lambda: service.router,
            )
        )

    def __init__(self, bindings: ScheduledSummaryServiceBindings) -> None:
        self._bindings = bindings
        self.job = ExpenseSummaryJob(self.runtime)

    def runtime(self) -> ExpenseSummaryRuntime:
        service = self._bindings
        return ExpenseSummaryRuntime(
            get_profile=lambda name: ProfilesRepository(service.profiles_path()).load().get(name),
            resolve_tools=service._resolved_mcp_tools(),
            execute_tool=service._execute_resolved_tool(),
            router=service.router(),
            agent_logs=service.agent_log_store(),
            make_agent=service.Agent(),
            finish_log=service._finish_agent_log(),
            sanitize_error=sanitize_error,
        )

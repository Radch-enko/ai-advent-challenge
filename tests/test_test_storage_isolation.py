import os
from pathlib import Path

from copia.api import service
from copia.data.mcp_connections_repository import McpConnectionsRepository
from copia.data.user_profiles_repository import JsonUserProfilesRepository


def test_service_storage_uses_temporary_data_root() -> None:
    root = Path(os.environ["COPIA_DATA_ROOT"]).resolve()
    paths = (
        service.sessions._root,
        service.working_memory._root,
        service.pending_memory_repository._root,
        service.profile_memory._root,
        service.invariants_repository._path,
        service.user_profiles._path,
        service.expenses._path,
        service.mcp_connections._path,
        service.scheduled_runs.root,
        service.scheduled_runner.config_path,
        service.scheduled_runner.state_path,
        service.agent_log_store._repository._root,
    )

    assert root.is_dir()
    assert all(path.resolve().is_relative_to(root) for path in paths)


def test_pytest_temporary_files_use_the_same_root(tmp_path: Path) -> None:
    assert tmp_path.resolve().is_relative_to(Path(os.environ["COPIA_DATA_ROOT"]).resolve())


def test_default_repository_paths_use_temporary_data_root() -> None:
    root = Path(os.environ["COPIA_DATA_ROOT"]).resolve()

    assert JsonUserProfilesRepository()._path.resolve() == root / "user_profiles.json"
    assert McpConnectionsRepository()._path.resolve() == root / "mcp_connections.json"

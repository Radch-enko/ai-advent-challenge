import os
import sys
import tempfile
from pathlib import Path

import pytest

_test_data = tempfile.TemporaryDirectory(prefix="copia-test-data-")

for _name in (
    "COPIA_PROFILES_PATH",
    "COPIA_SESSIONS_PATH",
    "COPIA_INVARIANTS_PATH",
    "COPIA_MEMORY_PATH",
    "COPIA_USER_PROFILES_PATH",
    "COPIA_MCP_CONNECTIONS_PATH",
    "COPIA_SCHEDULED_RUNS_PATH",
    "COPIA_SCHEDULES_PATH",
    "COPIA_SCHEDULER_STATE_PATH",
    "COPIA_EXPENSES_PATH",
):
    os.environ.pop(_name, None)

os.environ["COPIA_DATA_ROOT"] = _test_data.name
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
sys.dont_write_bytecode = True


def pytest_configure(config: pytest.Config) -> None:
    config.option.basetemp = str(Path(_test_data.name) / "pytest-tmp")


def pytest_unconfigure() -> None:
    _test_data.cleanup()

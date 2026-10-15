from pathlib import Path

import pytest

from code_assistance.config import default_config_path


def test_default_config_file_is_anchored_to_code_assistance_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("CODE_ASSISTANCE_CONFIG", "/tmp/outside-config.toml")

    assert default_config_path() == project_root / "config.toml"

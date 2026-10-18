from code_assistance.config import load_config


def test_openai_request_timeout_defaults_to_one_minute(tmp_path) -> None:
    config = load_config(tmp_path / "missing-config.toml")

    assert config.request_timeout_seconds == 60

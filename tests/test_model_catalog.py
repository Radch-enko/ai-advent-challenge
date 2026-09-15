from copia.data.model_catalog import context_window_for
from copia.domain.models.config import ProviderName


def test_returns_context_window_for_known_model() -> None:
    assert context_window_for(ProviderName.OPENAI, "gpt-5.4-mini") == 400_000


def test_returns_context_windows_for_main_openai_model_families() -> None:
    assert context_window_for(ProviderName.OPENAI, "gpt-6-astra") == 1_050_000
    assert context_window_for(ProviderName.OPENAI, "gpt-5.6") == 1_050_000
    assert context_window_for(ProviderName.OPENAI, "o3") == 200_000
    assert context_window_for(ProviderName.OPENAI, "gpt-4.1") == 1_047_576
    assert context_window_for(ProviderName.OPENAI, "gpt-4o") == 128_000
    assert context_window_for(ProviderName.OPENAI, "gpt-3.5-turbo") == 16_385


def test_returns_none_for_unknown_model() -> None:
    assert context_window_for(ProviderName.OPENAI, "unknown-model") is None

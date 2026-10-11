from pathlib import Path

from copia.agents.data.profiles_repository import ProfilesRepository
from copia.providers.domain.models.provider_name import ProviderName


def test_ollama_researcher_uses_weather_mcp_tools_when_forecast_is_requested() -> None:
    profiles_path = Path(__file__).resolve().parents[1] / "profiles.json"
    profile = ProfilesRepository(profiles_path).load()["researcher_ollama"]
    access = {item.connection_id: set(item.enabled_tools) for item in profile.mcp_access}

    assert profile.provider is ProviderName.OLLAMA
    assert access["open_meteo"] == {"openmeteo_get_forecast"}
    assert "geocode" in access["mapmap"]
    assert "обязательно вызывай MCP-инструмент openmeteo_get_forecast" in profile.system_prompt
    assert "MCP-инструмент геокодирования geocode" in profile.system_prompt

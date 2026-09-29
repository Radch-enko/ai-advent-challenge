from unittest.mock import Mock

from copia.providers.application.llm_router import LLMRouter
from copia.providers.domain.models.provider_name import ProviderName


def test_router_closes_each_provider() -> None:
    provider = Mock()

    LLMRouter({ProviderName.OPENAI: provider}).close()

    provider.close.assert_called_once_with()

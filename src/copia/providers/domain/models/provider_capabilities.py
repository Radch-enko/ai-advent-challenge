from __future__ import annotations

from pydantic import BaseModel

from copia.providers.domain.models.provider_name import ProviderName


class ProviderCapabilities(BaseModel):
    provider: ProviderName
    supported_parameters: list[str]
    supports_structured_output: bool

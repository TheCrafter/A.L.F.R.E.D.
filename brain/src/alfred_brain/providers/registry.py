from __future__ import annotations

import logging

from ..config import Settings
from .base import ReasoningProvider
from .scripted import ScriptedProvider

log = logging.getLogger(__name__)


def build_provider(settings: Settings) -> ReasoningProvider:
    name = settings.provider
    if name == "scripted":
        return ScriptedProvider()
    if name == "gemini":
        if not settings.gemini_api_key:
            log.warning("GEMINI_API_KEY not set; falling back to scripted provider.")
            return ScriptedProvider()
        from .gemini import GeminiProvider
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    log.warning("Provider %r not implemented in Phase 1; using scripted.", name)
    return ScriptedProvider()

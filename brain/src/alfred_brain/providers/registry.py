from __future__ import annotations

import logging

from ..config import Settings
from .base import ReasoningProvider
from .scripted import ScriptedProvider

log = logging.getLogger(__name__)

# Curated, switchable model catalog per provider (for the UI model picker).
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


def available_models(settings: Settings) -> list[dict[str, str]]:
    """Models the running brain can switch to, given which keys are configured."""
    out: list[dict[str, str]] = [{"provider": "scripted", "model": "scripted"}]
    if settings.gemini_api_key:
        out += [{"provider": "gemini", "model": m} for m in GEMINI_MODELS]
    if settings.groq_api_key:
        out += [{"provider": "groq", "model": m} for m in GROQ_MODELS]
    return out


def build_explicit(settings: Settings, provider: str, model: str) -> ReasoningProvider:
    """Build a specific provider+model, raising if its key is missing or unknown.

    Unlike build_provider (startup, forgiving), this never silently falls back —
    an explicit runtime switch must fail loudly so the UI can report it.
    """
    if provider == "scripted":
        return ScriptedProvider()
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        from .gemini import GeminiProvider
        return GeminiProvider(settings.gemini_api_key, model)
    if provider == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set")
        from .groq import GroqProvider
        return GroqProvider(settings.groq_api_key, model)
    raise ValueError(f"unknown provider {provider!r}")


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
    if name == "groq":
        if not settings.groq_api_key:
            log.warning("GROQ_API_KEY not set; falling back to scripted provider.")
            return ScriptedProvider()
        from .groq import GroqProvider
        return GroqProvider(settings.groq_api_key, settings.groq_model)
    log.warning("Provider %r not implemented; using scripted.", name)
    return ScriptedProvider()

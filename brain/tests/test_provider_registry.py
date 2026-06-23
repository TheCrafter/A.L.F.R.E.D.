import os

import pytest

from alfred_brain.config import Settings
from alfred_brain.providers.gemini import GeminiProvider
from alfred_brain.providers.registry import build_provider
from alfred_brain.providers.scripted import ScriptedProvider


def test_scripted_selected():
    p = build_provider(Settings(provider="scripted", _env_file=None))
    assert isinstance(p, ScriptedProvider)


def test_gemini_without_key_falls_back_to_scripted():
    p = build_provider(Settings(provider="gemini", gemini_api_key=None, _env_file=None))
    assert isinstance(p, ScriptedProvider)


def test_gemini_with_key_builds_gemini():
    p = build_provider(Settings(provider="gemini", gemini_api_key="x", _env_file=None))
    assert isinstance(p, GeminiProvider)


def test_groq_without_key_falls_back_to_scripted():
    p = build_provider(Settings(provider="groq", groq_api_key=None, _env_file=None))
    assert isinstance(p, ScriptedProvider)


def test_groq_with_key_builds_groq():
    from alfred_brain.providers.groq import GroqProvider
    p = build_provider(Settings(provider="groq", groq_api_key="x", _env_file=None))
    assert isinstance(p, GroqProvider)


def test_unknown_provider_falls_back():
    p = build_provider(Settings(provider="totally-unknown", _env_file=None))
    assert isinstance(p, ScriptedProvider)


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="needs a live Gemini key")
async def test_gemini_live_smoke():
    p = GeminiProvider(os.environ["GEMINI_API_KEY"], os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    from alfred_brain.providers.base import TurnMessage
    events = [ev async for ev in p.run_turn([TurnMessage(role="user", content="Say hello in five words.")], [], "Be brief.")]
    assert events  # produced at least one event

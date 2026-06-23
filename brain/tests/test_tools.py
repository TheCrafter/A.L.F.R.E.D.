import pytest

from alfred_brain.providers.base import ToolSpec
from alfred_brain.tools.echo import EchoTool
from alfred_brain.tools.registry import ToolRegistry
from alfred_protocol import RiskTier


async def test_echo_returns_input():
    assert await EchoTool().run({"text": "ping"}) == "ping"


def test_echo_is_safe():
    assert EchoTool().risk == RiskTier.safe


def test_registry_register_get_has_names():
    reg = ToolRegistry()
    reg.register(EchoTool())
    assert reg.has("echo")
    assert reg.names() == ["echo"]
    assert reg.get("echo").name == "echo"


def test_registry_specs_are_toolspecs_without_risk():
    reg = ToolRegistry()
    reg.register(EchoTool())
    specs = reg.specs()
    assert isinstance(specs[0], ToolSpec)
    assert specs[0].name == "echo"
    assert specs[0].parameters["required"] == ["text"]


def test_registry_get_missing_raises():
    with pytest.raises(KeyError):
        ToolRegistry().get("nope")

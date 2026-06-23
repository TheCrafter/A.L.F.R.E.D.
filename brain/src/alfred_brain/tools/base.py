from typing import Protocol, runtime_checkable

from alfred_protocol import RiskTier


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    risk: RiskTier
    parameters: dict  # JSON schema describing args for the model

    async def run(self, args: dict) -> str:
        ...

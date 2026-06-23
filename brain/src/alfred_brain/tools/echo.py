from alfred_protocol import RiskTier


class EchoTool:
    name = "echo"
    description = "Echo the given text back verbatim."
    risk = RiskTier.safe
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text to echo."}},
        "required": ["text"],
    }

    async def run(self, args: dict) -> str:
        return str(args.get("text", ""))

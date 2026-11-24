"""The steps of an agent's work, as the dashboard shows them."""

import json

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage


def steps(message: AnyMessage) -> list[tuple[str, str]]:
    """Turn one message from an agent into steps, each a kind and its content."""
    if isinstance(message, ToolMessage):
        if message.name == "read_section" and message.status == "success":
            return [("read", message.text)]
        return [("tool_result", f"{message.name}: {message.text}")]
    found: list[tuple[str, str]] = []
    if message.text:
        found.append(("message", message.text))
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            args = ", ".join(f"{k}={json.dumps(v)}" for k, v in call["args"].items())
            found.append(("tool_call", f"{call['name']}({args})"))
    return found

"""The UnderCover Agent."""

import json
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agent import tools

load_dotenv(override=True)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or GPT-6 Luna by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def steps_of(message: BaseMessage) -> list[tuple[str, str]]:
    """Turn one of the agent's messages into the steps the dashboard shows."""
    if isinstance(message, ToolMessage):
        return [("tool_result", f"{message.name}: {message.text}")]
    steps: list[tuple[str, str]] = [("message", message.text)] if message.text else []
    if isinstance(message, AIMessage):
        for tool_call in message.tool_calls:
            args = ", ".join(
                f"{name}={json.dumps(value)}"
                for name, value in tool_call["args"].items()
            )
            steps.append(("tool_call", f"{tool_call['name']}({args})"))
    return steps


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one claim, record each step with the backend and return the final reply."""
    with tools.backend() as client:
        client.post(f"/api/claims/{claim_id}/start").raise_for_status()
        instructions = client.get("/api/instructions").raise_for_status().json()
        agent = create_agent(
            llm or model(),
            tools=tools.TOOLS,
            system_prompt=instructions["instructions"],
        )
        reply = ""
        for update in agent.stream(
            {"messages": [{"role": "user", "content": f"Decide claim {claim_id}."}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="updates",
        ):
            for node in update.values():
                for message in node["messages"]:
                    for kind, text in steps_of(message):
                        client.post(
                            f"/api/claims/{claim_id}/steps",
                            json={"kind": kind, "text": text},
                        ).raise_for_status()
                    if isinstance(message, AIMessage):
                        reply = message.text
    return reply

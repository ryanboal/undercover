from itertools import count

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

ids = count()


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies, raises scripted errors and keeps
    the prompts it was sent."""

    prompts: list[list[BaseMessage]] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(messages)
        reply = next(self.messages)
        if isinstance(reply, Exception):
            raise reply
        message = reply if isinstance(reply, BaseMessage) else AIMessage(reply)
        return ChatResult(generations=[ChatGeneration(message=message)])


def stub(*replies):
    return StubModel(messages=iter(replies))


def call(name, text="", **args):
    return AIMessage(
        content=text,
        tool_calls=[{"name": name, "args": args, "id": f"call-{next(ids)}"}],
    )


def decide(decision, payout, section="Section 3, Trip Delay"):
    return call(
        "record_decision",
        decision=decision,
        payout=payout,
        section=section,
        reason="The delay was covered.",
    )


def claim_script(decision="refer", payout: float = 0, *extra):
    """A claim agent that reads the claim, decides, does anything extra and replies."""
    return [
        call("get_claim"),
        decide(decision, payout),
        *extra,
        AIMessage(content=f"Decision: {decision}."),
    ]

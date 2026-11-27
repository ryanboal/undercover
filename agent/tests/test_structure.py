"""The agent's structure, from docs/CODE_STANDARDS.md."""

import ast
import re
from pathlib import Path

import pytest

from agent.tools import CLAIM_TOOLS, QUEUE_TOOLS

AGENT = Path(__file__).parent.parent
INSTRUCTIONS = AGENT.parent / "backend" / "instructions"
LAYERS = ["api", "context", "rules", "tools", "steps", "harness", "__main__"]
MODULES = [path.stem for path in AGENT.glob("*.py") if path.stem != "__init__"]


def source(module):
    return (AGENT / f"{module}.py").read_text(encoding="utf-8")


def imports(module):
    """The agent modules a module imports."""
    found = set()
    for node in ast.walk(ast.parse(source(module))):
        if isinstance(node, ast.ImportFrom) and node.module == "agent":
            found |= {name.name for name in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            found |= {parts[1]} if parts[0] == "agent" else set()
    return found


def test_every_module_has_a_layer():
    assert sorted(MODULES) == sorted(LAYERS)


@pytest.mark.parametrize("module", LAYERS)
def test_a_module_only_imports_from_earlier_layers(module):
    assert imports(module) <= set(LAYERS[: LAYERS.index(module)])


@pytest.mark.parametrize("module", [m for m in LAYERS if m != "api"])
def test_only_the_api_module_calls_the_backend(module):
    assert not re.search(r"httpx|requests|urllib|localhost|[\"']/", source(module))


@pytest.mark.parametrize("module", [m for m in LAYERS if m != "tools"])
def test_tools_are_only_in_the_tools_module(module):
    assert "@tool" not in source(module)


@pytest.mark.parametrize("module", [m for m in LAYERS if m != "harness"])
def test_agents_are_only_built_in_the_harness(module):
    assert "create_agent" not in source(module)


@pytest.mark.parametrize("module", LAYERS)
def test_functions_are_short(module):
    for node in ast.walk(ast.parse(source(module))):
        if isinstance(node, ast.FunctionDef):
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            assert length <= 40, f"{module}.{node.name} has {length} lines"


@pytest.mark.parametrize("name", ["queue", "claim"])
def test_instructions_give_goals_not_steps(name):
    text = (INSTRUCTIONS / f"{name}.md").read_text(encoding="utf-8")
    assert "## Your goal" in text
    assert not re.search(r"^\s*\d+[.)] ", text, re.MULTILINE), "numbered steps"
    assert len(text.split()) <= 500


def test_tools_never_return_a_bare_list():
    """An empty list reaches the model as an empty reply, so it asks again."""
    for t in CLAIM_TOOLS + QUEUE_TOOLS:
        returns = t.func.__annotations__["return"]  # type: ignore[attr-defined]
        assert getattr(returns, "__origin__", returns) is not list, t.name

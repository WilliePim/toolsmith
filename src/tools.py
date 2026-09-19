"""The two tools the agent starts with: a calculator and today's date.

Inputs:  a tool name and its arguments, as the model sent them
Outputs: FIXED (name -> function), SCHEMAS (what the model sees), call()

These run inside the agent's own process, because we wrote them. Their input
does not come from us, though, so calc() still refuses anything that is not
arithmetic, and any arithmetic that would take the process down with it.
"""

from __future__ import annotations

import ast
import operator
from datetime import date
from typing import Any, Callable

MAX_EXPRESSION_CHARS = 500
MAX_POWER_BITS = 100_000        # 9**9**9 would need ~10**8 digits; refuse it


def _power(base: float, exponent: float) -> float:
    """** with a size check, so an exponent tower is refused instead of hanging."""
    if isinstance(base, int) and isinstance(exponent, int) and exponent > 0 \
            and max(base.bit_length(), 1) * exponent > MAX_POWER_BITS:
        raise ValueError("the result would be too large")
    return operator.pow(base, exponent)


_OPERATORS: dict[type, Callable] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: _power,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float:
    """Evaluate one arithmetic node, refusing anything that is not arithmetic."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"not arithmetic: {ast.dump(node)[:60]}")


def calc(expression: str) -> str:
    """Evaluate one arithmetic expression."""
    if len(expression) > MAX_EXPRESSION_CHARS:
        return f"error: the expression is longer than {MAX_EXPRESSION_CHARS} characters"
    try:
        value = _eval_node(ast.parse(expression, mode="eval").body)
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return f"{value:.10g}" if isinstance(value, float) else str(value)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError,
            OverflowError, RecursionError) as exc:
        return f"error: could not evaluate {expression!r} ({exc})"


def today() -> str:
    """Today's date, as an ISO string."""
    return date.today().isoformat()


FIXED: dict[str, Callable[..., str]] = {"calc": calc, "today": today}

# What the model sees. A neutral {name, description, parameters} shape: each
# provider adapter wraps it the way its API expects.
SCHEMAS: list[dict[str, Any]] = [
    {"name": "calc",
     "description": "Evaluate one arithmetic expression, such as '36 - 221 % 36'.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "required": ["expression"],
                    "properties": {"expression": {
                        "type": "string",
                        "description": "An expression using + - * / // % ** and parentheses."}}}},
    {"name": "today",
     "description": "Today's date as an ISO string.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "required": [], "properties": {}}},
]


def call(name: str, args: dict) -> str:
    """Run one fixed tool. Never raises: a failure is text the model can read."""
    fn = FIXED.get(name)
    if fn is None:
        return f"ERROR: there is no tool called {name!r}."
    try:
        return str(fn(**args))
    except TypeError as exc:
        return f"ERROR: wrong arguments for {name}: {exc}"
    except Exception as exc:  # noqa: BLE001 - hand it back as text
        return f"ERROR: {type(exc).__name__}: {exc}"


if __name__ == "__main__":
    import re
    import time

    assert [s["name"] for s in SCHEMAS] == list(FIXED), "every tool needs a schema"
    assert calc("(36 - 221 % 36) % 36") == "31"
    assert calc("2 ** 0.5") == "1.414213562"
    assert calc("7 / 2") == "3.5" and calc("6 / 2") == "3"
    assert calc("1 / 0").startswith("error:")
    assert calc('__import__("os")').startswith("error:"), "a call is not arithmetic"
    assert calc("x + 1").startswith("error:"), "a name is not arithmetic"
    started = time.perf_counter()
    assert "too large" in calc("9 ** 9 ** 9")
    assert time.perf_counter() - started < 0.1, "the size check must refuse at once"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", today())
    assert call("nope", {}).startswith("ERROR: there is no tool")
    assert call("calc", {"x": "1"}).startswith("ERROR: wrong arguments")
    assert call("today", {}) == today()

    print(f"fixed tools: {', '.join(FIXED)}")
    print(f"  calc('(36 - 221 % 36) % 36') -> {calc('(36 - 221 % 36) % 36')}")
    print(f"  calc('9 ** 9 ** 9') -> {calc('9 ** 9 ** 9')}")
    print("OK - tools")

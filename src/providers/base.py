"""The shapes every provider speaks, so the agent never has to know which one it has.

Inputs:  nothing
Outputs: ToolCall, ToolResult, Completion, ProviderError, duration()
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool call the model asked for, with its arguments already parsed."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """What running one ToolCall produced, as text for the model to read."""

    call: ToolCall
    text: str
    is_error: bool = False


@dataclass(frozen=True, slots=True)
class Completion:
    """One model response, or one named way of not getting one."""

    text: str = ""
    finish_reason: str = "stop"
    tool_calls: tuple[ToolCall, ...] = ()
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str = ""
    raw: Any = None     # the provider's own assistant turn, echoed back unchanged

    @property
    def ok(self) -> bool:
        """A turn that is nothing but tool calls has no text and is still fine."""
        return not self.error and bool(self.text or self.tool_calls)


class ProviderError(Exception):
    """A failed model call, classified so llm.complete() knows what to do next.

    kind  "rate"       a per-minute limit: wait for the server's hint, then retry
          "busy"       overloaded service or network failure: back off, then retry
          "malformed"  a botched tool call: retry at once, a new sample may differ
          "daily"      a daily quota is spent: retrying is pointless for hours
          "fatal"      anything else: bad request, bad key, a refusal
    """

    def __init__(self, kind: str, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_after = retry_after


_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
_DURATION = re.compile(r"([\d.]+)\s*(ms|s|m|h)")   # "ms" before "m", or 650ms is 650 minutes


def duration(value: str | float | None) -> float:
    """Seconds in a server's wait hint: '7.66s', '1m30s', '650ms', or a bare '12'."""
    if value is None:
        return 0.0
    text = str(value).strip()
    try:
        return float(text)          # a bare number of seconds, as retry-after sends it
    except ValueError:
        return sum(float(amount) * _UNITS[unit] for amount, unit in _DURATION.findall(text))

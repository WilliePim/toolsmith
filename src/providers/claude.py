"""The Claude adapter, on Anthropic's own SDK.

Inputs:  the neutral shapes in providers/base.py
Outputs: generate(), and the message builders that llm.py re-exports

Three differences from the PDF's Groq code, all forced by the model:
  - no temperature: Claude Opus 5 rejects the parameter, so a retry is simply a
    fresh sample, and adaptive thinking already varies it;
  - the assistant turn goes back with every content block unchanged, thinking
    blocks included, or the next request is refused;
  - all tool results of one turn go back in ONE user message.
"""

from __future__ import annotations

from typing import Any, Sequence

import anthropic

from src import config
from src.providers.base import Completion, ProviderError, ToolCall, ToolResult, duration

NAME = "claude"
SPACING_S = config.CLAUDE_REQUEST_SPACING_S
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client: anthropic.AsyncAnthropic | None = None


def client() -> anthropic.AsyncAnthropic:
    """The shared client, with SDK retries off so every failure is visible here."""
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=config.require_api_key(NAME),
                                           max_retries=0, timeout=config.MODEL_TIMEOUT_S)
    return _client


def tool_param(tool: dict) -> dict[str, Any]:
    """A neutral tool as Claude wants it. strict: arguments always match the schema."""
    return {"name": tool["name"], "description": tool["description"],
            "input_schema": tool["parameters"], "strict": True}


def request(system: str, messages: Sequence[Any], tools: Sequence[dict]) -> dict[str, Any]:
    """The keyword arguments for one Messages API call."""
    kwargs: dict[str, Any] = {
        "model": config.CLAUDE_MODEL,
        "max_tokens": config.CLAUDE_MAX_TOKENS,
        "system": system,
        "messages": list(messages),
        "tools": [tool_param(tool) for tool in tools],
        "output_config": {"effort": config.CLAUDE_EFFORT},
        # No "thinking" key: Opus 5 thinks adaptively by default.
    }
    if config.CLAUDE_FALLBACKS:
        # If a safety classifier declines the request, the API re-runs it on a
        # fallback model inside the same call instead of just stopping.
        kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
    return kwargs


def _describe(exc: Exception) -> str:
    if isinstance(exc, anthropic.APIStatusError):
        return f"{exc.status_code} {exc.message}"
    return f"{type(exc).__name__}: {exc}"


def parse(message: Any) -> Completion:
    """One Message as a Completion, or a ProviderError naming what went wrong."""
    if message.stop_reason == "refusal":
        category = getattr(message.stop_details, "category", None)
        raise ProviderError("fatal", "the model declined to continue (refusal"
                                     + (f", {category})" if category else ")"))
    blocks = list(message.content)
    text = "".join(block.text for block in blocks if block.type == "text").strip()
    calls = tuple(ToolCall(id=block.id, name=block.name, args=dict(block.input))
                  for block in blocks if block.type == "tool_use")
    if message.stop_reason == "max_tokens" and calls:
        raise ProviderError("malformed", "a tool call was cut off by max_tokens")
    usage = message.usage
    prompt_tokens = ((usage.input_tokens or 0) + (usage.cache_read_input_tokens or 0)
                     + (usage.cache_creation_input_tokens or 0))
    return Completion(text=text, finish_reason=message.stop_reason or "end_turn",
                      tool_calls=calls, prompt_tokens=prompt_tokens,
                      completion_tokens=usage.output_tokens or 0,
                      raw=[block.model_dump(mode="json", exclude_none=True) for block in blocks])


async def generate(system: str, messages: Sequence[Any], tools: Sequence[dict],
                   attempt: int) -> Completion:
    """One Messages API call. Raises ProviderError; llm.complete() decides what next."""
    kwargs = request(system, messages, tools)
    api = client().beta.messages if "betas" in kwargs else client().messages
    try:
        raw = await api.with_raw_response.create(**kwargs)
        message = await raw.parse()         # anthropic 1.x: parse() is awaited
    except anthropic.RateLimitError as exc:
        hint = duration(exc.response.headers.get("retry-after"))
        raise ProviderError("rate", _describe(exc), retry_after=hint or None) from exc
    except (anthropic.OverloadedError, anthropic.InternalServerError,
            anthropic.APIConnectionError) as exc:
        raise ProviderError("busy", _describe(exc)) from exc
    except anthropic.APIStatusError as exc:
        raise ProviderError("fatal", _describe(exc)) from exc
    return parse(message)


# --- Message builders --------------------------------------------------------------

def user_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def assistant_message(completion: Completion) -> dict[str, Any]:
    """Every content block exactly as it came back, thinking blocks included."""
    content = completion.raw if completion.raw is not None else \
        [{"type": "text", "text": completion.text}]
    return {"role": "assistant", "content": content}


def tool_results_message(results: Sequence[ToolResult], note: str = "") -> list[dict[str, Any]]:
    """All results of one turn in ONE user message; a split teaches Claude to stop
    making parallel calls."""
    content: list[dict[str, Any]] = [
        {"type": "tool_result", "tool_use_id": result.call.id, "content": result.text,
         **({"is_error": True} if result.is_error else {})}
        for result in results]
    if note:
        content.append({"type": "text", "text": note})
    return [{"role": "user", "content": content}]

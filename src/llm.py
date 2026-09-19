"""One door to the model: Gemini or Claude, the same shapes either way.

Inputs:  a system prompt, a message list, tools as {name, description, parameters}
Outputs: complete() -> Completion, and the message builders the agent appends with

complete() never raises. A rate limit, a botched tool call, a spent daily quota
and a dead model all come back as a Completion with a named reason, because a
caller that has to wrap every call in try/except ends up swallowing the
interesting cases.
"""

from __future__ import annotations

import asyncio
import random
from types import ModuleType
from typing import Any, Sequence

from src import config
from src.providers import claude, gemini
from src.providers.base import Completion, ProviderError, ToolCall, ToolResult, duration

__all__ = ["Completion", "ToolCall", "ToolResult", "complete", "provider",
           "user_message", "assistant_message", "tool_results_message"]

_ADAPTERS: dict[str, ModuleType] = {"gemini": gemini, "claude": claude}


def provider() -> ModuleType:
    """The adapter for config.PROVIDER, read at call time so --provider can switch it."""
    return _ADAPTERS[config.require_provider()]


def user_message(text: str) -> Any:
    return provider().user_message(text)


def assistant_message(completion: Completion) -> Any:
    return provider().assistant_message(completion)


def tool_results_message(results: Sequence[ToolResult], note: str = "") -> list[Any]:
    return provider().tool_results_message(results, note)


def _backoff(hint: float | None, attempt: int) -> float:
    """How long to wait before a retry, with jitter so retries do not resync.

    Without a hint the fallback climbs in fives, not twos: a per-minute bucket can
    need most of a minute to refill, and a ladder of 2, 4, 6 seconds gives up
    exactly when waiting would have worked.
    """
    if hint:
        return min(hint + 1.0, 65.0) + random.uniform(0.0, 1.5)
    return 5.0 * (attempt + 1) + random.uniform(0.0, 1.5)


async def complete(system: str, messages: Sequence[Any], tools: Sequence[dict]) -> Completion:
    """Call the model once. Returns a Completion for every outcome, good or bad."""
    adapter = provider()
    error = ""
    for attempt in range(config.MAX_RETRIES + 1):
        last = attempt == config.MAX_RETRIES
        try:
            result = await adapter.generate(system, messages, tools, attempt)
        except ProviderError as exc:
            if exc.kind == "daily":
                # A daily limit will not clear for hours, whatever its retry hint says.
                return Completion(finish_reason="out of quota", error=exc.message)
            if exc.kind in ("rate", "busy", "malformed") and not last:
                error = exc.message
                # A 429 is about the clock, so wait. A malformed call is about the
                # sample, so draw again at once.
                if exc.kind != "malformed":
                    await asyncio.sleep(_backoff(exc.retry_after, attempt))
                continue
            return Completion(finish_reason="error", error=exc.message)
        except Exception as exc:  # noqa: BLE001 - every failure is a result
            return Completion(finish_reason="error", error=f"{type(exc).__name__}: {exc}")

        if not result.text and not result.tool_calls:
            # A degenerate sample: thinking, then nothing. Not an answer and not an
            # error anyone can act on, so it gets a fresh draw like a malformed one.
            error = "the model returned an empty message"
            if not last:
                continue
            return Completion(finish_reason="empty", error=error,
                              prompt_tokens=result.prompt_tokens,
                              completion_tokens=result.completion_tokens)
        await asyncio.sleep(adapter.SPACING_S)
        return result
    return Completion(finish_reason="error", error=error or "retries exhausted")


# --- Self-check --------------------------------------------------------------------

def _offline_checks() -> None:
    """Everything that can be proven without a network call."""
    from anthropic.types.beta import BetaMessage
    from google.genai import errors as gerrors
    from google.genai import types as gtypes

    assert duration("7.66s") == 7.66 and duration("1m30s") == 90.0
    assert abs(duration("650ms") - 0.65) < 1e-9, "ms must be read before m"
    assert duration("12") == 12.0 and duration(None) == 0.0

    # Gemini: a per-minute 429 waits for its hint; a per-day 429 stops the run.
    def gemini_429(quota_id: str) -> gerrors.APIError:
        return gerrors.APIError(429, {"error": {
            "code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota",
            "details": [
                {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                 "violations": [{"quotaId": quota_id}]},
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "23s"}]}})
    minute = gemini.classify(gemini_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))
    day = gemini.classify(gemini_429("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    assert (minute.kind, minute.retry_after) == ("rate", 23.0), minute.kind
    assert day.kind == "daily", day.kind

    # Gemini: the request config builds for both thinking styles, and hands calls back.
    tools = [{"name": "calc", "description": "d",
              "parameters": {"type": "object", "properties": {"x": {"type": "string"}}}}]
    for model in ("gemini-3.6-flash", "gemini-2.5-flash"):
        saved, config.GEMINI_MODEL = config.GEMINI_MODEL, model
        try:
            built = gemini.request_config("system", tools)
        finally:
            config.GEMINI_MODEL = saved
        assert built.automatic_function_calling.disable is True
        assert (built.thinking_config.thinking_level is not None) == model.startswith("gemini-3")

    # Gemini: thought parts are not answer text; calls keep their ids; malformed is named.
    response = gtypes.GenerateContentResponse.model_validate({
        "candidates": [{"finish_reason": "STOP", "content": {"role": "model", "parts": [
            {"text": "planning...", "thought": True, "thought_signature": "c2lnbmF0dXJl"},
            {"function_call": {"id": "fc-1", "name": "calc", "args": {"expression": "1+1"}}},
            {"function_call": {"id": "fc-2", "name": "today", "args": {}}}]}}],
        "usage_metadata": {"prompt_token_count": 50, "candidates_token_count": 9,
                           "thoughts_token_count": 30}})
    parsed = gemini.parse(response)
    assert parsed.text == "" and [c.id for c in parsed.tool_calls] == ["fc-1", "fc-2"]
    assert parsed.ok and parsed.completion_tokens == 39
    assert gemini.assistant_message(parsed) is response.candidates[0].content, \
        "the model's own Content must go back unchanged (thought signatures)"
    reply = gemini.tool_results_message([ToolResult(c, "2") for c in parsed.tool_calls])
    assert len(reply) == 1 and len(reply[0].parts) == 2 and reply[0].parts[0].function_response.id == "fc-1"
    malformed = gtypes.GenerateContentResponse.model_validate(
        {"candidates": [{"finish_reason": "MALFORMED_FUNCTION_CALL"}]})
    try:
        gemini.parse(malformed)
        raise AssertionError("a malformed call must raise")
    except ProviderError as exc:
        assert exc.kind == "malformed"

    # Claude: no temperature, strict tools, effort, fallbacks; thinking blocks survive.
    kwargs = claude.request("system", [claude.user_message("hi")],
                            [{"name": "calc", "description": "d", "parameters": {"type": "object"}}])
    assert "temperature" not in kwargs and kwargs["tools"][0]["strict"] is True
    assert kwargs["output_config"] == {"effort": config.CLAUDE_EFFORT}
    message = BetaMessage.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "model": config.CLAUDE_MODEL,
        "stop_reason": "tool_use", "stop_sequence": None,
        "usage": {"input_tokens": 40, "output_tokens": 12},
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig-abc"},
            {"type": "tool_use", "id": "tu_1", "name": "calc", "input": {"expression": "2*3"}},
            {"type": "tool_use", "id": "tu_2", "name": "today", "input": {}}]})
    parsed = claude.parse(message)
    turn = claude.assistant_message(parsed)
    assert turn["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-abc"}
    reply = claude.tool_results_message([ToolResult(c, "6") for c in parsed.tool_calls], note="n")
    assert len(reply) == 1 and [b["type"] for b in reply[0]["content"]] == \
        ["tool_result", "tool_result", "text"], "one user message for every result"


async def _live_check(name: str) -> None:
    """One real call that should come back as a tool call: echo_number(n=4021)."""
    import time

    config.PROVIDER = name
    echo = {"name": "echo_number", "description": "Echo a number back.",
            "parameters": {"type": "object", "additionalProperties": False,
                           "required": ["n"], "properties": {"n": {"type": "integer"}}}}
    started = time.perf_counter()
    result = await complete("You are a test harness. Always answer by calling a tool.",
                            [user_message("Call echo_number with n = 4021.")], [echo])
    elapsed = time.perf_counter() - started
    if not result.ok:
        raise SystemExit(f"{name}: {result.finish_reason}: {result.error}")
    call = result.tool_calls[0]
    assert call.name == "echo_number" and int(call.args["n"]) == 4021, call
    print(f"{name}: tool call -> {call.args} in {elapsed:.1f}s, "
          f"{result.completion_tokens} completion tokens")


if __name__ == "__main__":
    import os

    _offline_checks()
    print("offline: duration parsing, 429 classification, message shapes - OK")
    for name, key in (("gemini", "GEMINI_API_KEY"), ("claude", "ANTHROPIC_API_KEY")):
        if os.getenv(key, "").strip():
            asyncio.run(_live_check(name))
        else:
            print(f"{name}: live call skipped - {key} not set")
    print("OK - llm")

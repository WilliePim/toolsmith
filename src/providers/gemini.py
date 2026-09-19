"""The Gemini adapter, on Google's own google-genai SDK.

Inputs:  the neutral shapes in providers/base.py
Outputs: generate(), and the message builders that llm.py re-exports

The model's own Content goes back into the conversation unchanged. Gemini's
thinking models attach thought signatures to their parts, and a rebuilt copy of
the turn would drop them.
"""

from __future__ import annotations

from typing import Any, Sequence

import httpx
from google import genai
from google.genai import errors, types

from src import config
from src.providers.base import Completion, ProviderError, ToolCall, ToolResult, duration

NAME = "gemini"
SPACING_S = config.GEMINI_REQUEST_SPACING_S

# Gemini's names for "the model emitted a tool call nobody could use".
_MALFORMED = {"MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL", "TOO_MANY_TOOL_CALLS"}
_BLOCKED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}

_client: genai.Client | None = None


def client() -> genai.Client:
    """The shared client, with SDK retries off so every failure is visible here."""
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=config.require_api_key(NAME),
            http_options=types.HttpOptions(
                timeout=int(config.MODEL_TIMEOUT_S * 1000),      # milliseconds
                retry_options=types.HttpRetryOptions(attempts=1)))
    return _client


def _thinking() -> types.ThinkingConfig:
    """Gemini 3 takes a thinking level; Gemini 2.x only takes a token budget."""
    if config.GEMINI_MODEL.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_budget=1024)
    return types.ThinkingConfig(
        thinking_level=types.ThinkingLevel[config.GEMINI_THINKING_LEVEL.upper()])


def request_config(system: str, tools: Sequence[dict]) -> types.GenerateContentConfig:
    """Everything but the conversation itself, for one generate_content call."""
    declarations = [types.FunctionDeclaration(name=tool["name"],
                                              description=tool["description"],
                                              parameters_json_schema=tool["parameters"])
                    for tool in tools]
    return types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=declarations)] if declarations else None,
        # We run the tools ourselves: the SDK must hand calls back, not execute them.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        thinking_config=_thinking(),
        max_output_tokens=config.GEMINI_MAX_OUTPUT_TOKENS,
        temperature=config.GEMINI_TEMPERATURE)


def classify(exc: errors.APIError) -> ProviderError:
    """Turn an API error into a named reason, reading Google's structured details."""
    body = exc.details if isinstance(exc.details, dict) else {}
    body = body.get("error", body)
    details = body.get("details", []) if isinstance(body, dict) else []
    quota_ids = [violation.get("quotaId", "")
                 for detail in details if isinstance(detail, dict)
                 for violation in detail.get("violations", []) if isinstance(violation, dict)]
    retry_delay = next((detail.get("retryDelay") for detail in details
                        if isinstance(detail, dict)
                        and str(detail.get("@type", "")).endswith("RetryInfo")), None)
    message = f"{exc.code} {exc.status}: {exc.message}"

    if exc.code == 429:
        if any("PerDay" in quota_id for quota_id in quota_ids):
            # A daily 429 says "retry in 23s" and means hours. Say so plainly.
            return ProviderError(
                "daily", f"the free tier's daily quota for {config.GEMINI_MODEL} is spent. "
                         f"It resets at midnight Pacific time; another model has its own "
                         f"quota (set GEMINI_MODEL in .env).")
        return ProviderError("rate", message, retry_after=duration(retry_delay) or None)
    if exc.code in (500, 502, 503, 504):
        return ProviderError("busy", message)
    return ProviderError("fatal", message)


def parse(response: types.GenerateContentResponse) -> Completion:
    """One response as a Completion, or a ProviderError naming what went wrong."""
    usage = response.usage_metadata
    prompt_tokens = (usage.prompt_token_count or 0) if usage else 0
    output_tokens = ((usage.candidates_token_count or 0)
                     + (usage.thoughts_token_count or 0)) if usage else 0

    if not response.candidates:
        feedback = getattr(response, "prompt_feedback", None)
        reason = getattr(feedback, "block_reason", None)
        raise ProviderError("fatal", f"the prompt was blocked ({reason})" if reason
                            else "the response had no candidates")
    candidate = response.candidates[0]
    finish = candidate.finish_reason.name if candidate.finish_reason else "STOP"
    if finish in _MALFORMED:
        raise ProviderError("malformed", f"Gemini reported {finish}")

    parts = (candidate.content.parts if candidate.content else None) or []
    text = "".join(part.text for part in parts if part.text and not part.thought).strip()
    calls = tuple(ToolCall(id=part.function_call.id or "",
                           name=part.function_call.name or "",
                           args=dict(part.function_call.args or {}))
                  for part in parts if part.function_call)
    if finish in _BLOCKED and not (text or calls):
        raise ProviderError("fatal", f"Gemini stopped the response ({finish})")
    return Completion(text=text, finish_reason=finish.lower(), tool_calls=calls,
                      prompt_tokens=prompt_tokens, completion_tokens=output_tokens,
                      raw=candidate.content)


async def generate(system: str, messages: Sequence[Any], tools: Sequence[dict],
                   attempt: int) -> Completion:
    """One generate_content call. Raises ProviderError; llm.complete() decides what next.

    `attempt` is unused here: at the model's default temperature every retry is
    already a different sample.
    """
    try:
        response = await client().aio.models.generate_content(
            model=config.GEMINI_MODEL, contents=list(messages),
            config=request_config(system, tools))
    except errors.APIError as exc:
        raise classify(exc) from exc
    except httpx.TransportError as exc:
        raise ProviderError("busy", f"network: {type(exc).__name__}: {exc}") from exc
    return parse(response)


# --- Message builders --------------------------------------------------------------

def user_message(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])


def assistant_message(completion: Completion) -> types.Content:
    """The model's own Content, unchanged: a rebuilt copy would lose thought signatures."""
    if completion.raw is not None:
        return completion.raw
    return types.Content(role="model", parts=[types.Part(text=completion.text)])


def tool_results_message(results: Sequence[ToolResult], note: str = "") -> list[types.Content]:
    """Every result of one turn in one Content, matched to its call by id when given."""
    parts = [types.Part(function_response=types.FunctionResponse(
                 id=result.call.id or None, name=result.call.name,
                 response={"error": result.text} if result.is_error else {"output": result.text}))
             for result in results]
    if note:
        parts.append(types.Part(text=note))
    return [types.Content(role="user", parts=parts)]

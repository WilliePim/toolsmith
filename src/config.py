"""Every knob the agent has, in one place.

Inputs:  environment variables, read from .env
Outputs: constants, paths, TASK_SETS, ensure_dirs(), require_api_key()
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
GENERATED_DIR = ROOT_DIR / "generated"

# One task file per set, picked with --set on the command line. A new set is
# a new file and one line here; existing files never change.
TASK_SETS: dict[str, Path] = {
    "core": DATA_DIR / "tasks.json",
    "finance": DATA_DIR / "tasks_finance.json",
}
DEFAULT_TASK_SET = "core"

# Keys live in .env, not in the shell, so load them before anything reads one.
# A variable already set in the shell wins over the file.
load_dotenv(ROOT_DIR / ".env")

for _stream in (sys.stdout, sys.stderr):
    try:  # Windows consoles default to cp1252, and a tool can return anything
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _env(name: str, default: str) -> str:
    """An environment variable, treating an empty value (NAME=) as unset."""
    return os.getenv(name, "").strip() or default


# --- The model -------------------------------------------------------------
# PROVIDER is read at call time, so main.py can override it with --provider.
PROVIDERS = ("gemini", "claude")
PROVIDER = _env("PROVIDER", "gemini").lower()

GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_THINKING_LEVEL = "low"
GEMINI_MAX_OUTPUT_TOKENS = 8192     # thinking tokens count against this too
GEMINI_REQUEST_SPACING_S = 4.0      # stays under a free-tier requests/minute cap

CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-opus-5")
CLAUDE_EFFORT = "low"               # the PDF's reasoning_effort, Claude's way
CLAUDE_MAX_TOKENS = 16000           # thinking counts too; no streaming needed
CLAUDE_REQUEST_SPACING_S = 0.0

# --- The agent's budget ----------------------------------------------------
# MAX_ROUNDS is ten, not six, and the arithmetic is why: three rejected tools,
# the round that registers one, the round that calls it and the round that
# answers are already six. A tight budget cuts off exactly the run that worked
# hardest to get there.
MAX_ROUNDS = 10
MAX_REPAIR_ATTEMPTS = 3             # write_tool calls allowed: first try + 3
MAX_RESULT_CHARS = 1500             # a tool result longer than this is cut
MAX_RETRIES = 4                     # per model call, for 429s and bad samples

# --- The sandbox -----------------------------------------------------------
SANDBOX_TIMEOUT_S = 10.0
SANDBOX_MAX_OUTPUT = 256 * 1024     # bytes of stdout before the child is killed
SANDBOX_POLL_S = 0.02
MAX_SOURCE_CHARS = 8000

# What a generated tool may import. Default-deny: a module is here because a
# tool plausibly needs it, not because it looks harmless. Deliberately absent,
# and worth naming: os, sys, subprocess, socket, pathlib, importlib, builtins -
# and `operator`, the near-miss, because operator.attrgetter("__class__") is a
# string-built attribute access with no getattr call anywhere in it.
ALLOWED_IMPORTS: frozenset[str] = frozenset({
    "math", "datetime", "re", "decimal", "json", "itertools",
    "functools", "collections", "string", "calendar", "typing",
})

_API_KEYS = {
    "gemini": ("GEMINI_API_KEY", "https://aistudio.google.com/apikey"),
    "claude": ("ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"),
}


def model_name(provider: str | None = None) -> str:
    """The model the given (or configured) provider will call."""
    provider = provider or PROVIDER
    return GEMINI_MODEL if provider == "gemini" else CLAUDE_MODEL


def ensure_dirs() -> None:
    """Create the directories the agent writes into."""
    for path in (DATA_DIR, GENERATED_DIR):
        path.mkdir(parents=True, exist_ok=True)


def require_provider(provider: str | None = None) -> str:
    """The provider name, validated, or a clean exit that lists the options."""
    provider = (provider or PROVIDER).lower()
    if provider not in PROVIDERS:
        raise SystemExit(f"Unknown provider {provider!r}. Use one of: {', '.join(PROVIDERS)}.")
    return provider


def require_api_key(provider: str | None = None) -> str:
    """Fail loudly and early, with the URL that fixes it."""
    name, url = _API_KEYS[require_provider(provider)]
    key = os.getenv(name, "").strip()
    if not key:
        raise SystemExit(f"{name} is not set. Copy .env.example to .env "
                         f"and paste a key from {url}")
    return key


if __name__ == "__main__":
    provider = require_provider()
    key_name = _API_KEYS[provider][0]
    rows = {
        "provider": provider,
        "model": model_name(provider),
        "budget": f"{MAX_ROUNDS} rounds, {MAX_REPAIR_ATTEMPTS} repairs, "
                  f"{MAX_RETRIES} retries per call",
        "sandbox": f"{SANDBOX_TIMEOUT_S}s, {SANDBOX_MAX_OUTPUT:,} bytes, "
                   f"{MAX_SOURCE_CHARS:,} source chars",
        "imports": ", ".join(sorted(ALLOWED_IMPORTS)),
        "task sets": ", ".join(f"{name} ({'ok' if path.exists() else 'not built yet'})"
                               for name, path in TASK_SETS.items()),
        "api key": f"{key_name} {'set' if os.getenv(key_name, '').strip() else 'MISSING'}",
    }
    for label, value in rows.items():
        print(f"{label:<10} {value}")

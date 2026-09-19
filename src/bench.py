"""Run every task many times, in both conditions, and save one file per run.

Inputs:  --repeats N, optionally --set / --condition / --provider
Outputs: results/runs/<run_id>.json, one per run, plus the toolbox each
         repetition built in results/toolboxes/

    uv run python -m src.bench --repeats 10

Three rules this runner exists to enforce:

  * a repetition is a *fresh* toolbox. Otherwise repetition 2 starts with the
    tools repetition 1 wrote, and "the first task writes, the second reuses"
    stops being what is measured;
  * only provider failures (429, 5xx, network) are retried. Anything the agent
    itself did - a wrong answer, a refused tool, running out of rounds - is a
    result and is recorded as it happened;
  * every run is skippable. Re-running the command picks up exactly where the
    last one stopped, so a daily quota can be waited out overnight.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from src import config, prompts
from src.agent import Agent
from src.registry import Registry
from src.tasks import TaskSet, load_set

RESULTS_DIR = config.ROOT_DIR / "results"
RUNS_DIR = RESULTS_DIR / "runs"
TOOLBOX_DIR = RESULTS_DIR / "toolboxes"
PROMPT_DIR = RESULTS_DIR / "prompts"

CONDITIONS = ("tools", "baseline")
API_RETRY_WAITS = (15.0, 45.0, 120.0)      # provider failures only, growing

console = Console()


def code_commit() -> str:
    """The commit the runs were produced from, so a result can be traced to code."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.ROOT_DIR,
                             capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=config.ROOT_DIR,
                               capture_output=True, text=True, timeout=10)
        return (out.stdout.strip() or "unknown") + ("+dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):       # pragma: no cover
        return "unknown"


def prompt_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def save_prompts() -> None:
    """Write both system prompts to the repo, so the README's diff has a source."""
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    for name, allow in (("system_with_tools.txt", True), ("system_baseline.txt", False)):
        (PROMPT_DIR / name).write_text(prompts.system_prompt(allow), encoding="utf-8",
                                       newline="\n")


def run_id(task_set: str, condition: str, task_id: str, repetition: int) -> str:
    return f"{task_set}__{condition}__{task_id}__r{repetition:02d}"


def run_path(rid: str) -> Path:
    return RUNS_DIR / f"{rid}.json"


def _is_daily_quota(note: str) -> bool:
    return "daily quota" in note.lower() or "out of tokens" in note.lower()


class DailyQuotaReached(RuntimeError):
    """Raised to stop the whole bench cleanly; the next run resumes from here."""


async def one_run(task, task_set: TaskSet, registry: Registry | None, condition: str,
                  repetition: int, meta: dict[str, Any]) -> dict[str, Any]:
    """Solve one task once, retrying only provider failures."""
    rid = run_id(task.task_set, condition, task.id, repetition)
    allow_tools = condition == "tools"
    api_retries = 0
    wasted_prompt = wasted_completion = 0

    for attempt in range(len(API_RETRY_WAITS) + 1):
        started = time.perf_counter()
        agent = Agent(task_set.families[task.family], registry or Registry(),
                      task_set.tool_returns[task.family], console, allow_tools)
        result = await agent.solve(task)
        elapsed = time.perf_counter() - started

        if result.api_error:
            if _is_daily_quota(result.note):
                raise DailyQuotaReached(result.note)
            wasted_prompt += result.prompt_tokens
            wasted_completion += result.completion_tokens
            if attempt < len(API_RETRY_WAITS):
                wait = API_RETRY_WAITS[attempt]
                api_retries += 1
                console.print(f"  [yellow]provider error, retrying in {wait:.0f}s[/]: "
                              f"{result.note[:80]}")
                await asyncio.sleep(wait)
                continue
            # Out of retries: record it as a provider failure, not an agent result.
            console.print(f"  [red]giving up after {api_retries} provider retries[/]")

        record = {
            "run_id": rid,
            "task_set": task.task_set, "task": task.id, "family": task.family,
            "condition": condition, "repetition": repetition,
            "status": result.status, "answer": result.answer, "expected": result.expected,
            "correct": result.correct,
            "rounds": result.rounds,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "tools_written": result.tools_written, "tools_used": result.tools_used,
            "refusals": result.refusals, "write_attempts": result.write_attempts,
            "repaired": result.repaired,
            "note": result.note,
            "trace": result.trace,
            "api_retries": api_retries,
            "api_error": result.api_error,
            "tokens_lost_to_api_errors": {"prompt": wasted_prompt,
                                          "completion": wasted_completion},
            "duration_s": round(elapsed, 2),
            "meta": meta,
        }
        return record
    raise AssertionError("unreachable")


async def run_repetition(task_set: TaskSet, condition: str, repetition: int,
                         meta: dict[str, Any], force: bool, only_task: str = "") -> int:
    """One pass over a set's tasks, in order, sharing one toolbox. Returns runs done."""
    registry: Registry | None = None
    original = config.GENERATED_DIR
    done = 0

    if condition == "tools":
        # A toolbox per repetition, kept on disk so a resumed run finds the tool
        # the earlier task in this same repetition wrote.
        box = TOOLBOX_DIR / f"{task_set.name}__r{repetition:02d}"
        box.mkdir(parents=True, exist_ok=True)
        config.GENERATED_DIR = box
        registry = Registry()
        registry.load_all()

    try:
        for task in task_set.tasks:
            if only_task and task.id != only_task:
                continue
            rid = run_id(task.task_set, condition, task.id, repetition)
            path = run_path(rid)
            if path.exists() and not force:
                console.print(f"[dim]skip {rid} (already done)[/]")
                continue
            console.rule(f"[bold]{rid}[/]")
            record = await one_run(task, task_set, registry, condition, repetition, meta)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8", newline="\n")
            done += 1
    finally:
        config.GENERATED_DIR = original
    return done


async def main_async(args) -> int:
    save_prompts()
    sets = [args.set] if args.set else list(config.TASK_SETS)
    conditions = [args.condition] if args.condition else list(CONDITIONS)
    meta = {
        "model": config.model_name(),
        "provider": config.PROVIDER,
        # Left at the model's own default on purpose: that variability is what
        # repeated runs are here to measure.
        "temperature": "provider default (unset)",
        "thinking": config.GEMINI_THINKING_LEVEL if config.PROVIDER == "gemini"
                    else config.CLAUDE_EFFORT,
        "commit": code_commit(),
        "prompt_sha": {c: prompt_digest(prompts.system_prompt(c == "tools"))
                       for c in CONDITIONS},
        "started": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    console.print(f"[bold]bench[/] model={meta['model']} commit={meta['commit']} "
                  f"repeats={args.repeats} conditions={', '.join(conditions)}")

    total = 0
    try:
        for repetition in range(1, args.repeats + 1):
            for name in sets:
                task_set = load_set(name)
                for condition in conditions:
                    total += await run_repetition(task_set, condition, repetition,
                                                  meta, args.force, args.task or "")
    except DailyQuotaReached as stop:
        console.print(f"\n[yellow]stopped: {stop}[/]")
        console.print("[yellow]The daily quota is spent. Re-run the same command "
                      "tomorrow: finished runs are skipped automatically.[/]")
        _progress(args)
        return 2

    console.print(f"\n[green]{total} new run(s) recorded[/]")
    _progress(args)
    return 0


def _progress(args) -> None:
    have = len(list(RUNS_DIR.glob("*.json"))) if RUNS_DIR.exists() else 0
    want = args.repeats * len(CONDITIONS) * sum(
        len(load_set(name).tasks) for name in config.TASK_SETS)
    console.print(f"progress: {have}/{want} runs on disk "
                  f"({RUNS_DIR.relative_to(config.ROOT_DIR)})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bench", description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=10,
                        help="repetitions per task per condition (default 10)")
    parser.add_argument("--set", choices=list(config.TASK_SETS),
                        help="only this task set")
    parser.add_argument("--condition", choices=CONDITIONS, help="only this condition")
    parser.add_argument("--task", help="only this task id (for a quick smoke test)")
    parser.add_argument("--provider", choices=list(config.PROVIDERS))
    parser.add_argument("--force", action="store_true",
                        help="redo runs that already have a result file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.provider:
        config.PROVIDER = args.provider
    config.require_provider()
    config.require_api_key()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

"""The command line: run tasks, inspect the toolbox, reset it, or red-team.

  uv run python -m src.main run gstin_1 gstin_2
  uv run python -m src.main run --all --set finance
  uv run python -m src.main tools
  uv run python -m src.main show gstin_check_char
  uv run python -m src.main reset
  uv run python -m src.main redteam
"""

from __future__ import annotations

import argparse
import asyncio

from rich.console import Console
from rich.table import Table

from src import config
from src.agent import Agent, RunResult
from src.registry import Registry
from src.tasks import TaskSet, load_set

console = Console()


def _apply_provider(provider: str | None) -> None:
    if provider:
        config.PROVIDER = provider.lower()
    config.require_provider()


async def _run(task_set: TaskSet, ids: list[str], registry: Registry) -> list[RunResult]:
    results: list[RunResult] = []
    for task_id in ids:
        task = task_set.get(task_id)
        if task is None:
            console.print(f"[red]no task {task_id!r} in set {task_set.name!r}[/]")
            continue
        console.rule(f"[bold]{task.id}[/]  ({task_set.labels[task.family]})")
        agent = Agent(task_set.families[task.family], registry,
                      task_set.tool_returns[task.family], console)
        results.append(await agent.solve(task))
    return results


def _results_table(results: list[RunResult]) -> Table:
    table = Table(title="Results")
    for column in ("task", "answer", "expected", "ok", "rounds", "in", "out", "wrote", "used"):
        table.add_column(column)
    for r in results:
        mark = {"solved": "[green]OK[/]", "wrong": "[red]X[/]"}.get(r.status, f"[yellow]{r.status}[/]")
        table.add_row(r.task_id, (r.answer or "-")[:24], r.expected[:24], mark,
                      str(r.rounds), f"{r.prompt_tokens:,}", f"{r.completion_tokens:,}",
                      ",".join(r.tools_written) or "-", str(len(r.tools_used)))
    return table


def cmd_run(args) -> int:
    _apply_provider(args.provider)
    task_set = load_set(args.set)
    ids = [t.id for t in task_set.tasks] if args.all else args.ids
    if not ids:
        console.print("[red]name at least one task id, or use --all[/]")
        return 2
    registry = Registry()
    registry.load_all(warn=lambda m: console.print(f"[yellow]{m}[/]"))
    config.require_api_key()        # fail early with the URL, before the first call

    results = asyncio.run(_run(task_set, ids, registry))
    console.print(_results_table(results))
    solved = sum(r.correct for r in results)
    tokens = sum(r.completion_tokens for r in results)
    console.print(f"\n{solved}/{len(results)} solved, {tokens:,} completion tokens, "
                  f"{len(registry.all())} tools in the box")
    return 0 if solved == len(results) and results else 1


def cmd_tools(args) -> int:
    registry = Registry()
    registry.load_all(warn=lambda m: console.print(f"[yellow]{m}[/]"))
    box = registry.all()
    if not box:
        console.print("no tools written yet")
        return 0
    table = Table(title=f"{len(box)} tools in generated/")
    for column in ("name", "set", "family", "params", "uses", "created"):
        table.add_column(column)
    for tool in box:
        table.add_row(tool.name, tool.task_set, tool.family,
                      ", ".join(tool.param_names), str(tool.uses), tool.created)
    console.print(table)
    return 0


def cmd_show(args) -> int:
    registry = Registry()
    registry.load_all()
    tool = registry.get(args.name)
    if tool is None:
        console.print(f"[red]no tool called {args.name!r}[/]")
        return 1
    from rich.syntax import Syntax
    console.print(f"[bold]{tool.name}[/] - {tool.description}")
    console.print(f"set {tool.task_set}, family {tool.family}, used {tool.uses} times")
    console.print(Syntax(tool.source, "python", theme="ansi_dark", line_numbers=True))
    return 0


def cmd_reset(args) -> int:
    removed = Registry().reset()
    console.print(f"removed {removed} file(s) from generated/")
    return 0


def cmd_redteam(args) -> int:
    from src import redteam
    return redteam.main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="toolsmith", description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="command", required=True)

    run = subs.add_parser("run", help="solve one or more tasks")
    run.add_argument("ids", nargs="*", help="task ids, e.g. gstin_1")
    run.add_argument("--all", action="store_true", help="run every task in the set")
    run.add_argument("--set", default=config.DEFAULT_TASK_SET, choices=list(config.TASK_SETS))
    run.add_argument("--provider", choices=list(config.PROVIDERS))
    run.set_defaults(func=cmd_run)

    tools_cmd = subs.add_parser("tools", help="list the tools the agent has written")
    tools_cmd.set_defaults(func=cmd_tools)

    show = subs.add_parser("show", help="print one tool's source")
    show.add_argument("name")
    show.set_defaults(func=cmd_show)

    reset = subs.add_parser("reset", help="delete every generated tool")
    reset.set_defaults(func=cmd_reset)

    redteam = subs.add_parser("redteam", help="prove both security layers (no API calls)")
    redteam.set_defaults(func=cmd_redteam)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

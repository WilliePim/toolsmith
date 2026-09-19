"""The loop, and the one line that makes the toolbox grow.

Inputs:  a Task, its Family, and a Registry
Outputs: solve() -> RunResult (the answer, whether it was right, and what it cost)

Each round the tools array is rebuilt: the two fixed tools, every tool the
registry now holds, and the two control tools. A tool the model wrote last round
is therefore callable this round - that rebuild is the whole feature. Every tool
call is routed to one of four handlers; a rejected tool comes back as text the
model can repair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from rich.console import Console

from src import config, llm, prompts, tools
from src.llm import ToolCall, ToolResult
from src.registry import Registry
from src.smith import Family, ToolSpec, forge
from src.tasks import Task


@dataclass(slots=True)
class RunResult:
    """One solved (or unsolved) task, and what it cost."""

    task_id: str
    answer: str | None = None
    expected: str = ""
    rounds: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tools_written: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    status: str = "unfinished"      # solved | wrong | unfinished | stopped
    note: str = ""

    @property
    def correct(self) -> bool:
        return self.status == "solved"


class Agent:
    """Runs one task to an answer, printing a live trace of every round."""

    def __init__(self, family: Family, registry: Registry, tool_returns: str,
                 console: Console | None = None):
        self.family = family
        self.registry = registry
        self.tool_returns = tool_returns
        self.console = console or Console()

    def _toolset(self, can_write: bool) -> list[dict[str, Any]]:
        """The one line: fixed tools + everything written so far + the controls."""
        return tools.SCHEMAS + self.registry.schemas() + prompts.meta_schemas(can_write)

    async def solve(self, task: Task) -> RunResult:
        result = RunResult(task_id=task.id, expected=task.answer)
        messages = [llm.user_message(prompts.task_prompt(task, self.family, self.tool_returns))]
        writes_left = config.MAX_REPAIR_ATTEMPTS + 1

        for round_no in range(1, config.MAX_ROUNDS + 1):
            result.rounds = round_no
            can_write = writes_left > 0
            completion = await llm.complete(prompts.SYSTEM, messages, self._toolset(can_write))
            result.prompt_tokens += completion.prompt_tokens
            result.completion_tokens += completion.completion_tokens

            if not completion.ok:
                self._log(round_no, f"[red]model error[/]: {completion.error}")
                result.status, result.note = "stopped", completion.error
                return result

            if completion.text:
                self._log(round_no, f"[dim]{completion.text[:200]}[/]")
            messages.append(llm.assistant_message(completion))

            if not completion.tool_calls:
                # No tool call and no submit: nudge once, then it counts as a round.
                messages.extend(llm.tool_results_message([], note=self._steer(round_no, writes_left)))
                continue

            answer, results, writes_left = self._handle(
                completion.tool_calls, task, result, writes_left)
            if answer is not None:
                return self._finish(result, answer)
            note = self._steer(round_no, writes_left)
            messages.extend(llm.tool_results_message(results, note=note))

        result.status, result.note = "unfinished", "ran out of rounds"
        self._log(config.MAX_ROUNDS, "[red]out of rounds[/]")
        return result

    def _handle(self, calls: Sequence[ToolCall], task: Task, result: RunResult,
                writes_left: int) -> tuple[str | None, list[ToolResult], int]:
        """Route each tool call. Returns (answer or None, results, writes_left)."""
        out: list[ToolResult] = []
        for call in calls:
            if call.name == "submit_answer":
                return str(call.args.get("answer", "")), out, writes_left
            if call.name == "write_tool":
                text, writes_left = self._write(call, task, result, writes_left)
                out.append(ToolResult(call, text, is_error="registered" not in text))
            elif call.name in self.registry:
                out.append(self._call_generated(call, result))
            elif call.name in tools.FIXED:
                out.append(ToolResult(call, tools.call(call.name, call.args)))
            else:
                out.append(ToolResult(call, f"ERROR: no tool called {call.name!r}.",
                                      is_error=True))
        return None, out, writes_left

    def _write(self, call: ToolCall, task: Task, result: RunResult,
               writes_left: int) -> tuple[str, int]:
        if writes_left <= 0:
            return prompts.REPAIRS_DONE, 0
        writes_left -= 1
        spec = ToolSpec(
            name=str(call.args.get("name", "")),
            description=str(call.args.get("description", "")),
            parameters={"type": "object", "additionalProperties": False,
                        "required": list(self.family.tool_params),
                        "properties": self.family.tool_params},
            source=str(call.args.get("source", "")),
            tests=tuple(call.args.get("tests", ())))
        forged = forge(spec, self.family, self.registry)
        verb = "[green]registered[/]" if forged.ok else f"[yellow]refused ({forged.stage})[/]"
        self._log(result.rounds, f"write_tool {spec.name!r}: {verb}")
        if forged.ok:
            result.tools_written.append(spec.name)
        return forged.message, writes_left

    def _call_generated(self, call: ToolCall, result: RunResult) -> ToolResult:
        run = self.registry.call(call.name, [call.args])
        self.registry.record_use(call.name)
        result.tools_used.append(call.name)
        first = run.results[0] if run.results else {"ok": False, "error": run.detail}
        if first.get("ok"):
            self._log(result.rounds, f"{call.name}({_short(call.args)}) -> {first['value']!r}")
            return ToolResult(call, _truncate(str(first["value"])))
        self._log(result.rounds, f"{call.name}({_short(call.args)}) -> [red]{first.get('error')}[/]")
        return ToolResult(call, f"ERROR: {first.get('error')}", is_error=True)

    def _finish(self, result: RunResult, answer: str) -> RunResult:
        result.answer = answer
        result.status = "solved" if answer == result.expected else "wrong"
        colour = "green" if result.correct else "red"
        self._log(result.rounds, f"submit_answer -> {answer!r} "
                                 f"[{colour}]{'correct' if result.correct else 'wrong'}[/]")
        return result

    def _steer(self, round_no: int, writes_left: int) -> str:
        if writes_left <= 0:
            return prompts.REPAIRS_DONE
        if config.MAX_ROUNDS - round_no <= 2:
            return prompts.ROUNDS_LOW
        return prompts.NUDGE

    def _log(self, round_no: int, message: str) -> None:
        self.console.print(f"  [dim]r{round_no}[/] {message}")


def _truncate(text: str) -> str:
    if len(text) <= config.MAX_RESULT_CHARS:
        return text
    return text[:config.MAX_RESULT_CHARS] + f"... [truncated at {config.MAX_RESULT_CHARS} chars]"


def _short(args: dict) -> str:
    text = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return text if len(text) <= 60 else text[:57] + "..."


async def solve(task: Task, family: Family, registry: Registry, tool_returns: str = "",
                console: Console | None = None) -> RunResult:
    """Convenience wrapper: build an Agent and solve one task."""
    return await Agent(family, registry, tool_returns, console).solve(task)


if __name__ == "__main__":
    # An offline smoke test: a scripted "model" drives the loop with no network,
    # so the routing, the repair budget and the rebuilt toolset are all exercised.
    import asyncio
    import tempfile
    from pathlib import Path

    from src.tasks import load_set

    ts = load_set("core")
    task = ts.get("gstin_1")
    family = ts.families["gstin"]

    good_source = (
        "def run(prefix):\n"
        "    base = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'\n"
        "    total = 0\n"
        "    for i, ch in enumerate(prefix):\n"
        "        p = base.index(ch) * (1 if i % 2 == 0 else 2)\n"
        "        total += p // 36 + p % 36\n"
        "    return base[(36 - total % 36) % 36]\n")

    class Script:
        """A fake provider: a fixed sequence of turns, no API involved."""

        def __init__(self, turns):
            self.turns = list(turns)
        SPACING_S = 0.0

        async def generate(self, system, messages, tool_calls, attempt):
            return self.turns.pop(0)
        def user_message(self, text): return {"role": "user", "content": text}
        def assistant_message(self, completion): return {"role": "assistant"}
        def tool_results_message(self, results, note=""): return [{"role": "tool"}]

    from src import llm as llm
    from src.llm import Completion

    turns = [
        Completion(tool_calls=(ToolCall("1", "write_tool", {
            "name": "gstin_check_char", "description": "GSTIN check char.",
            "source": good_source,
            "tests": [{"args": {"prefix": p}, "expect": e} for p, e in
                      (("16TEUYJ4263R1Z", "K"), ("07AABCS1429B1Z", "W"))]}),),
                   completion_tokens=200, prompt_tokens=800),
        Completion(tool_calls=tuple(
            ToolCall(str(i), "gstin_check_char", {"prefix": p})
            for i, p in enumerate(["16TEUYJ4263R1Z", "14ELRKY8914Q4Z",
                                   "03ZPVMA6122X3Z", "07RJXDS8075B1Z"])),
                   completion_tokens=60, prompt_tokens=900),
        Completion(tool_calls=(ToolCall("z", "submit_answer", {"answer": "KXMS"}),),
                   completion_tokens=10, prompt_tokens=950),
    ]

    original_dir, script = config.GENERATED_DIR, Script(turns)
    llm._ADAPTERS["gemini"] = script  # type: ignore[assignment]
    with tempfile.TemporaryDirectory() as tmp:
        config.GENERATED_DIR = Path(tmp)
        config.PROVIDER = "gemini"
        try:
            reg = Registry()
            res = asyncio.run(solve(task, family, reg, ts.tool_returns["gstin"]))
            assert res.correct and res.answer == "KXMS", res
            assert res.tools_written == ["gstin_check_char"]
            assert res.tools_used.count("gstin_check_char") == 4
            print(f"\nsolved {res.task_id}: {res.answer} in {res.rounds} rounds, "
                  f"wrote {res.tools_written}, used {len(res.tools_used)} calls")
            print("OK - agent")
        finally:
            config.GENERATED_DIR = original_dir

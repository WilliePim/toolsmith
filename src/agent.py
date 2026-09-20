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

import re
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
    refusals: dict[str, int] = field(default_factory=dict)   # stage -> count
    write_attempts: int = 0
    trace: list[str] = field(default_factory=list)   # what the live log showed

    @property
    def correct(self) -> bool:
        return self.status == "solved"

    @property
    def repaired(self) -> bool:
        """A tool was refused at least once and a later attempt still registered."""
        return bool(self.refusals) and bool(self.tools_written)

    @property
    def api_error(self) -> bool:
        """Stopped by the provider, not by the agent: not a result about the agent."""
        return self.status == "stopped"


class Agent:
    """Runs one task to an answer, printing a live trace of every round."""

    def __init__(self, family: Family, registry: Registry, tool_returns: str,
                 console: Console | None = None, allow_tools: bool = True):
        self.family = family
        self.registry = registry
        self.tool_returns = tool_returns
        self.console = console or Console()
        # The baseline condition: the agent may not write or call generated tools.
        self.allow_tools = allow_tools

    def _toolset(self, can_write: bool) -> list[dict[str, Any]]:
        """The one line: fixed tools + everything written so far + the controls."""
        if not self.allow_tools:
            return tools.SCHEMAS + prompts.meta_schemas(False)
        return tools.SCHEMAS + self.registry.schemas() + prompts.meta_schemas(can_write)

    async def solve(self, task: Task) -> RunResult:
        result = RunResult(task_id=task.id, expected=task.answer)
        system = prompts.system_prompt(self.allow_tools)
        messages = [llm.user_message(
            prompts.task_prompt(task, self.family, self.tool_returns, self.allow_tools))]
        writes_left = (config.MAX_REPAIR_ATTEMPTS + 1) if self.allow_tools else 0

        for round_no in range(1, config.MAX_ROUNDS + 1):
            result.rounds = round_no
            can_write = writes_left > 0
            completion = await llm.complete(system, messages, self._toolset(can_write))
            result.prompt_tokens += completion.prompt_tokens
            result.completion_tokens += completion.completion_tokens

            if not completion.ok:
                self._log(round_no, f"[red]model error[/]: {completion.error}", result)
                result.status, result.note = "stopped", completion.error
                return result

            if completion.text:
                self._log(round_no, f"[dim]{completion.text[:200]}[/]", result)
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
        self._log(config.MAX_ROUNDS, "[red]out of rounds[/]", result)
        return result

    def _handle(self, calls: Sequence[ToolCall], task: Task, result: RunResult,
                writes_left: int) -> tuple[str | None, list[ToolResult], int]:
        """Route each tool call. Returns (answer or None, results, writes_left).

        Calls to the same generated tool are collected and run in one sandbox
        process: the protocol already takes a batch of calls on stdin, and a
        round with six parallel calls should not pay for six interpreters.
        """
        out: list[ToolResult | None] = [None] * len(calls)
        batched: dict[str, list[int]] = {}

        for index, call in enumerate(calls):
            if call.name == "submit_answer":
                return str(call.args.get("answer", "")), _done(out), writes_left
            if call.name == "write_tool":
                text, writes_left = self._write(call, task, result, writes_left)
                out[index] = ToolResult(call, text, is_error="registered" not in text)
            elif call.name in self.registry:
                batched.setdefault(call.name, []).append(index)
            elif call.name in tools.FIXED:
                text = tools.call(call.name, call.args)
                self._log(result.rounds,
                          f"{call.name}({_short(call.args)}) -> {text[:60]!r}", result)
                out[index] = ToolResult(call, text)
            else:
                out[index] = ToolResult(call, f"ERROR: no tool called {call.name!r}.",
                                        is_error=True)

        for name, indexes in batched.items():
            group = [calls[i] for i in indexes]
            for index, tool_result in zip(indexes, self._call_generated(name, group, result)):
                out[index] = tool_result
        return None, _done(out), writes_left

    def _write(self, call: ToolCall, task: Task, result: RunResult,
               writes_left: int) -> tuple[str, int]:
        if writes_left <= 0:
            return prompts.REPAIRS_DONE, 0
        writes_left -= 1
        result.write_attempts += 1
        spec = ToolSpec(
            name=str(call.args.get("name", "")),
            description=str(call.args.get("description", "")),
            parameters={"type": "object", "additionalProperties": False,
                        "required": list(self.family.tool_params),
                        "properties": self.family.tool_params},
            source=str(call.args.get("source", "")),
            tests=tuple(call.args.get("tests", ())))
        forged = forge(spec, self.family, self.registry)
        if forged.ok:
            verb = "[green]registered[/]"
        else:
            # Show the reason, not just the stage: the model is told why, and so
            # should anyone watching the run.
            verb = f"[yellow]refused ({forged.stage})[/] {forged.message[:110]}"
        self._log(result.rounds, f"write_tool {spec.name!r}: {verb}", result)
        if forged.ok:
            result.tools_written.append(spec.name)
        else:
            result.refusals[forged.stage] = result.refusals.get(forged.stage, 0) + 1
        return forged.message, writes_left

    def _call_generated(self, name: str, calls: Sequence[ToolCall],
                        result: RunResult) -> list[ToolResult]:
        """Run one tool over every call it received this round, in a single sandbox."""
        run = self.registry.call(name, [call.args for call in calls])
        self.registry.record_use(name, len(calls))
        result.tools_used.extend([name] * len(calls))

        missing = {"ok": False, "error": run.detail or "no result"}
        out: list[ToolResult] = []
        for call, outcome in zip(calls, list(run.results) + [missing] * len(calls)):
            if outcome.get("ok"):
                self._log(result.rounds,
                          f"{name}({_short(call.args)}) -> {outcome['value']!r}", result)
                out.append(ToolResult(call, _truncate(str(outcome["value"]))))
            else:
                self._log(result.rounds,
                          f"{name}({_short(call.args)}) -> [red]{outcome.get('error')}[/]",
                          result)
                out.append(ToolResult(call, f"ERROR: {outcome.get('error')}", is_error=True))
        return out

    def _finish(self, result: RunResult, answer: str) -> RunResult:
        result.answer = answer
        result.status = "solved" if answer == result.expected else "wrong"
        colour = "green" if result.correct else "red"
        self._log(result.rounds, f"submit_answer -> {answer!r} "
                                 f"[{colour}]{'correct' if result.correct else 'wrong'}[/]", result)
        return result

    def _steer(self, round_no: int, writes_left: int) -> str:
        if writes_left <= 0:
            return prompts.REPAIRS_DONE
        if config.MAX_ROUNDS - round_no <= 2:
            return prompts.ROUNDS_LOW
        return prompts.NUDGE

    def _log(self, round_no: int, message: str, result: RunResult | None = None) -> None:
        self.console.print(f"  [dim]r{round_no}[/] {message}")
        if result is not None:
            # Keep the same line, without the colour markup, so a saved run can be
            # read back as the transcript a person actually watched.
            plain = re.sub(r"\[/?[a-z ]*\]", "", message)
            result.trace.append(f"r{round_no} {plain}")


def _done(slots: Sequence[ToolResult | None]) -> list[ToolResult]:
    """The results filled in so far, in the order the model asked for them."""
    return [slot for slot in slots if slot is not None]


def _truncate(text: str) -> str:
    if len(text) <= config.MAX_RESULT_CHARS:
        return text
    return text[:config.MAX_RESULT_CHARS] + f"... [truncated at {config.MAX_RESULT_CHARS} chars]"


def _short(args: dict) -> str:
    text = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return text if len(text) <= 60 else text[:57] + "..."


async def solve(task: Task, family: Family, registry: Registry, tool_returns: str = "",
                console: Console | None = None, allow_tools: bool = True) -> RunResult:
    """Convenience wrapper: build an Agent and solve one task."""
    return await Agent(family, registry, tool_returns, console, allow_tools).solve(task)


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

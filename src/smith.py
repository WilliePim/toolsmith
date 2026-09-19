"""Write, check, register: turn the model's tool spec into a registered tool.

Inputs:  a ToolSpec (name, description, parameters, source, tests) and the family
Outputs: a ForgeResult - registered, or refused with a message the model can act on

The checks run in order, cheapest and most-revealing first: name, parameters,
tests, the static guard, then one sandbox run covering the model's own tests and
every held-out batch. A failed own test is reported in full; a failed held-out
batch is reported only as a count and the family's hint, so the hidden inputs
never leak back to the model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src import config, guard, registry
from src.registry import Registry, Tool

MIN_TESTS = 2


@dataclass(frozen=True, slots=True)
class Family:
    """The part of a task family a forge needs: its interface and its held-out set."""

    name: str
    task_set: str
    tool_params: dict[str, Any]
    joiner: str
    holdout_hint: str
    holdout: tuple[dict, ...] = ()

    @property
    def param_names(self) -> frozenset[str]:
        return frozenset(self.tool_params)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """What the model sends to write_tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    source: str
    tests: tuple[dict, ...]      # each {"args": {...}, "expect": "..."}


@dataclass(frozen=True, slots=True)
class ForgeResult:
    """Registered, or not, with the exact text the agent hands back to the model."""

    ok: bool
    message: str
    tool: Tool | None = None
    stage: str = ""              # where it stopped: name|params|tests|guard|own_tests|holdout
    detail: dict = field(default_factory=dict)


def _expected_params(family: Family) -> str:
    return ", ".join(f"{name} ({spec.get('type', 'string')})"
                     for name, spec in family.tool_params.items())


def _check_spec(spec: ToolSpec, family: Family, reg: Registry) -> ForgeResult | None:
    """The four static checks, before anything runs. None means all four passed."""
    if not registry.valid_name(spec.name):
        return ForgeResult(False, f"'{spec.name}' is not a usable tool name. Use lowercase "
                           f"letters, digits and underscores, starting with a letter, and "
                           f"not a reserved name.", stage="name")
    if spec.name in reg:
        return ForgeResult(False, f"a tool called '{spec.name}' already exists; call it "
                           f"instead of writing it again, or choose another name.", stage="name")

    properties = spec.parameters.get("properties") if isinstance(spec.parameters, dict) else None
    if not isinstance(properties, dict) or set(properties) != family.param_names:
        return ForgeResult(False, f"this tool must take exactly these parameters: "
                           f"{_expected_params(family)}. Its parameters were "
                           f"{sorted(properties or [])}.", stage="params")

    if len(spec.tests) < MIN_TESTS:
        return ForgeResult(False, f"include at least {MIN_TESTS} tests, each with the "
                           f"arguments and the expected result, worked out from the "
                           f"task's example.", stage="tests")
    for test in spec.tests:
        if set((test.get("args") or {})) != family.param_names:
            return ForgeResult(False, f"each test's args must set exactly "
                               f"{sorted(family.param_names)}; one test had "
                               f"{sorted(test.get('args') or [])}.", stage="tests")

    problem = guard.check(spec.source, family.param_names)
    if problem is not None:
        return ForgeResult(False, f"the tool was refused before running - {problem}. Fix "
                           f"the source and keep it to one run() function with the allowed "
                           f"imports and no input or output.", stage="guard")
    return None


def _own_tests_message(spec: ToolSpec, values: list[Any]) -> str | None:
    """The first own test whose result is wrong, phrased with got and expected."""
    for test, value in zip(spec.tests, values):
        expect = str(test.get("expect"))
        got = "no result" if value is None else str(value)
        if got != expect:
            return (f"your own test failed: run({json.dumps(test.get('args'))}) returned "
                    f"{got!r}, but your test expected {expect!r}. Either the code or the "
                    f"expected value is wrong - rework it from the task's example.")
    return None


def forge(spec: ToolSpec, family: Family, reg: Registry) -> ForgeResult:
    """Run the whole gauntlet once. Registers the tool, or refuses it with a reason."""
    static = _check_spec(spec, family, reg)
    if static is not None:
        return static

    # One sandbox run for the model's tests and every held-out call, in order, so a
    # single process start covers them all.
    own_calls = [test["args"] for test in spec.tests]
    holdout_calls = [call for batch in family.holdout for call in batch["calls"]]
    run = _run(spec.source, own_calls + holdout_calls)
    if run.status != "ok" and not run.results:
        return ForgeResult(False, f"the tool did not run: {run.status} ({run.detail}). "
                           f"Check for an infinite loop or too much output.", stage="run")

    values = run.values()
    own_values = values[:len(own_calls)]
    own_problem = _own_tests_message(spec, own_values)
    if own_problem is not None:
        return ForgeResult(False, own_problem, stage="own_tests")

    # Held-out batches: report only how many failed, plus the hint. Never the inputs,
    # the expected values, or an exception message that could echo an input back.
    holdout_values = values[len(own_calls):]
    failed = _failed_holdout(family, holdout_values)
    if failed:
        return ForgeResult(False, f"the tool passed your tests but failed {failed} of "
                           f"{len(family.holdout)} hidden checks. Hint: {family.holdout_hint}. "
                           f"Reread the rule and handle that case.", stage="holdout",
                           detail={"failed_batches": failed})

    tool = reg.save(Tool(name=spec.name, description=spec.description,
                         parameters=spec.parameters, source=spec.source,
                         family=family.name, task_set=family.task_set,
                         tests=spec.tests, joiner=family.joiner, created=registry.now_iso()))
    return ForgeResult(True, f"registered '{spec.name}'. It is now available as a tool.",
                       tool=tool, stage="registered")


def _run(source: str, calls):
    from src import sandbox
    return sandbox.run_calls(source, calls)


def _failed_holdout(family: Family, values: list[Any]) -> int:
    """How many held-out batches did not join to their expected string."""
    failed = 0
    index = 0
    for batch in family.holdout:
        size = len(batch["calls"])
        chunk = values[index:index + size]
        index += size
        if any(v is None for v in chunk) or \
                family.joiner.join(str(v) for v in chunk) != batch["expect"]:
            failed += 1
    return failed


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    # A GSTIN family with one held-out batch that contains a digit check character.
    from src.taskgen import gstin_check
    edge = "29AAGCB7383J1Z"                       # its check char is a digit
    assert gstin_check(edge).isdigit()
    plain = "16TEUYJ4263R1Z"
    family = Family(name="gstin", task_set="core",
                    tool_params={"prefix": {"type": "string"}}, joiner="",
                    holdout_hint="some have a check character that is a digit, not a letter",
                    holdout=({"calls": [{"prefix": plain}, {"prefix": edge}],
                              "expect": gstin_check(plain) + gstin_check(edge)},))

    correct = (
        "def run(prefix):\n"
        "    base = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'\n"
        "    total = 0\n"
        "    for i, ch in enumerate(prefix):\n"
        "        p = base.index(ch) * (1 if i % 2 == 0 else 2)\n"
        "        total += p // 36 + p % 36\n"
        "    return base[(36 - total % 36) % 36]\n")
    # A subtly wrong tool: it forgets that a value below 10 is already a digit and
    # maps it through the letter table anyway. It matches on letter answers.
    wrong = correct.replace("return base[(36 - total % 36) % 36]",
                            "v = (36 - total % 36) % 36\n"
                            "    return chr(ord('A') + v - 10)")

    original = config.GENERATED_DIR
    with tempfile.TemporaryDirectory() as tmp:
        config.GENERATED_DIR = Path(tmp)
        try:
            reg = Registry()
            good_tests = ({"args": {"prefix": plain}, "expect": gstin_check(plain)},
                          {"args": {"prefix": "07AABCS1429B1Z"},
                           "expect": gstin_check("07AABCS1429B1Z")})
            params = {"type": "object", "additionalProperties": False,
                      "required": ["prefix"], "properties": {"prefix": {"type": "string"}}}

            good = forge(ToolSpec("gstin_check_char", "GSTIN check char.", params,
                                  correct, good_tests), family, reg)
            assert good.ok and "gstin_check_char" in reg, good.message

            # The wrong tool's own tests use letter answers, so they pass; the hidden
            # digit case fails, and the model gets only a count and the hint.
            bad = forge(ToolSpec("gstin_bad", "GSTIN check char.", params,
                                 wrong, good_tests), family, reg)
            assert not bad.ok and bad.stage == "holdout", bad.stage
            assert edge not in bad.message and gstin_check(edge) not in bad.message, \
                "a held-out input or answer leaked into the message"
            assert "1 of 1" in bad.message and family.holdout_hint in bad.message

            wrong_params = forge(ToolSpec("gstin_wp", "d",
                                          {"type": "object", "properties": {"code": {"type": "string"}}},
                                          correct, good_tests), family, reg)
            assert not wrong_params.ok and wrong_params.stage == "params"
            assert "prefix" in wrong_params.message

            blocked = forge(ToolSpec("gstin_io", "d", params,
                                     "import os\ndef run(prefix):\n    return os.getcwd()",
                                     good_tests), family, reg)
            assert not blocked.ok and blocked.stage == "guard"

            print(f"correct -> {good.message}")
            print(f"wrong   -> {bad.message}")
            print(f"params  -> {wrong_params.message}")
            print("OK - smith")
        finally:
            config.GENERATED_DIR = original

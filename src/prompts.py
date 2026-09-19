"""What the agent tells the model: the system prompt, the two control tools, and
the messages that steer a run.

Inputs:  a Task and its Family (for the interface line)
Outputs: SYSTEM, meta_schemas(), task_prompt(), and the short steering notes
"""

from __future__ import annotations

from typing import Any

from src import config
from src.smith import Family
from src.tasks import Task

SYSTEM = """\
You are toolsmith, an agent that solves each task by the cheapest reliable means.

You have a calculator and today's date to start with. When a task applies one \
rule across many inputs, do not work it out by hand: write a tool with write_tool, \
then call it. A written tool is exact and reusable, and a later task of the same \
kind can just call it.

When you write a tool, follow this contract exactly:
- Define one function, run(...), taking exactly the parameters the task states, \
and returning a string.
- Use only the Python standard library, and only these modules: {imports}. Do not \
read files, write files, use the network, or print anything you need - return it.
- Work out each test's expected result from the worked example in the task, by \
hand, before you write the code. If you cannot, you do not yet understand the rule.
- Give at least two tests. The tool is also checked against inputs you cannot see, \
so make run() follow the rule in general, not just for your tests.

If a tool is refused, read the reason and repair it: a refusal is a step, not the \
end. When you have the final answer, call submit_answer with exactly the format \
the task asks for. Do not call submit_answer until you are sure.
""".format(imports=", ".join(sorted(config.ALLOWED_IMPORTS)))


def interface_line(family: Family, tool_returns: str) -> str:
    """The one line that tells the model the exact run() signature for this family."""
    params = ", ".join(f"{name} ({spec.get('type', 'string')}): {spec.get('description', '')}"
                       for name, spec in family.tool_params.items())
    returns = f" It must return {tool_returns}." if tool_returns else ""
    return (f"\n\nA tool for this task must be run({', '.join(family.tool_params)}), "
            f"called once per input. Its parameters are: {params}.{returns}")


def task_prompt(task: Task, family: Family, tool_returns: str) -> str:
    """The task's own prompt, plus the interface line the tool must match."""
    return task.prompt + interface_line(family, tool_returns)


def meta_schemas(can_write: bool) -> list[dict[str, Any]]:
    """write_tool (only while repairs remain) and submit_answer."""
    schemas: list[dict[str, Any]] = []
    if can_write:
        schemas.append({
            "name": "write_tool",
            "description": "Write a Python tool, have it checked and, if it passes, "
                           "registered so you can call it. It runs against your tests "
                           "and against hidden inputs before it is accepted.",
            "parameters": {
                "type": "object", "additionalProperties": False,
                "required": ["name", "description", "source", "tests"],
                "properties": {
                    "name": {"type": "string",
                             "description": "lowercase, e.g. gstin_check_char"},
                    "description": {"type": "string",
                                    "description": "one line: what the tool returns"},
                    "source": {"type": "string",
                               "description": "Python defining run(...); allowed stdlib only"},
                    "tests": {"type": "array", "minItems": 2,
                              "description": "each: the arguments and the expected string",
                              "items": {
                                  "type": "object", "additionalProperties": False,
                                  "required": ["args", "expect"],
                                  "properties": {
                                      "args": {"type": "object",
                                               "description": "the run() arguments"},
                                      "expect": {"type": "string",
                                                 "description": "the expected return value"}}}}}}})
    schemas.append({
        "name": "submit_answer",
        "description": "Submit the final answer, in exactly the format the task asks for. "
                       "This ends the task.",
        "parameters": {"type": "object", "additionalProperties": False,
                       "required": ["answer"],
                       "properties": {"answer": {"type": "string"}}}})
    return schemas


# Short steering notes appended to a tool-results message when the run needs a nudge.
NUDGE = ("Decide your next step: call a tool you have, write one if a rule repeats, "
         "or submit_answer if you already have the answer.")
ROUNDS_LOW = ("You are running low on rounds. If you have a working tool, call it and "
              "submit the answer now.")
REPAIRS_DONE = ("You have used all your tool-writing attempts. Solve the task with the "
                "tools you already have, then call submit_answer.")


if __name__ == "__main__":
    from src.tasks import load_set

    ts = load_set("core")
    task = ts.get("gstin_1")
    family = ts.families["gstin"]

    assert "gstin" not in SYSTEM.lower(), "the system prompt must be task-agnostic"
    for module in ("math", "datetime", "calendar"):
        assert module in SYSTEM, f"{module} should be listed as allowed"

    prompt = task_prompt(task, family, ts.tool_returns["gstin"])
    assert task.prompt in prompt and "run(prefix)" in prompt
    assert "one-character string" in prompt, "the tool_returns hint should be present"

    full = meta_schemas(can_write=True)
    assert [s["name"] for s in full] == ["write_tool", "submit_answer"]
    assert full[0]["parameters"]["properties"]["tests"]["minItems"] == 2
    limited = meta_schemas(can_write=False)
    assert [s["name"] for s in limited] == ["submit_answer"]

    print("system prompt:", len(SYSTEM), "chars, task-agnostic")
    print("interface line:", interface_line(family, ts.tool_returns["gstin"]).strip())
    print("meta tools (can_write): ", [s["name"] for s in full])
    print("OK - prompts")

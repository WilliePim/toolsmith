"""Load a task set from disk and expose it as typed objects.

Inputs:  a set name ("core", "finance") -> config.TASK_SETS[name]
Outputs: load_set() -> Task objects and a Family lookup for the smith

The agent works from these, so it never parses the JSON itself. Held-out inputs
live on the Family and reach only the sandbox, never a prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src import config
from src.smith import Family


@dataclass(frozen=True, slots=True)
class Task:
    """One task the agent solves: the prompt the model sees, and the answer key."""

    id: str
    family: str
    task_set: str
    prompt: str
    answer: str
    calls: tuple[dict, ...]     # the same inputs in machine form, for grading only


@dataclass(frozen=True, slots=True)
class TaskSet:
    name: str
    tasks: tuple[Task, ...]
    families: dict[str, Family]
    labels: dict[str, str]      # family name -> human label
    tool_returns: dict[str, str]

    def get(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)


def load_set(name: str) -> TaskSet:
    """Read one task file into typed objects, or exit cleanly if it is missing."""
    path = config.TASK_SETS.get(name)
    if path is None:
        raise SystemExit(f"Unknown task set {name!r}. Choose from: "
                         f"{', '.join(config.TASK_SETS)}.")
    if not path.exists():
        raise SystemExit(f"{path.relative_to(config.ROOT_DIR)} does not exist yet. "
                         f"Build it: uv run python -m src.taskgen"
                         + ("_finance" if name == "finance" else ""))
    doc = json.loads(path.read_text(encoding="utf-8"))

    tasks: list[Task] = []
    families: dict[str, Family] = {}
    labels: dict[str, str] = {}
    tool_returns: dict[str, str] = {}
    for fam in doc["families"]:
        families[fam["family"]] = Family(
            name=fam["family"], task_set=name, tool_params=fam["tool_params"],
            joiner=fam["joiner"], holdout_hint=fam["holdout_hint"],
            holdout=tuple(fam["holdout"]))
        labels[fam["family"]] = fam.get("label", fam["family"])
        tool_returns[fam["family"]] = fam.get("tool_returns", "")
        for task in fam["tasks"]:
            tasks.append(Task(id=task["id"], family=fam["family"], task_set=name,
                              prompt=task["prompt"], answer=task["answer"],
                              calls=tuple(task["calls"])))
    return TaskSet(name=name, tasks=tuple(tasks), families=families,
                   labels=labels, tool_returns=tool_returns)


def load_all_sets() -> dict[str, TaskSet]:
    """Every set that exists on disk, for commands that span sets."""
    return {name: load_set(name) for name, path in config.TASK_SETS.items() if path.exists()}


if __name__ == "__main__":
    ts = load_set("core")
    assert {t.id for t in ts.tasks} == {"gstin_1", "gstin_2", "isoweek_1", "isoweek_2"}
    assert set(ts.families) == {"gstin", "isoweek"}
    gstin_1 = ts.get("gstin_1")
    assert gstin_1.answer == "KXMS" and gstin_1.family == "gstin"
    assert len(ts.families["gstin"].holdout) == 3
    for task_set in load_all_sets().values():
        ids = [t.id for t in task_set.tasks]
        assert len(ids) == len(set(ids)), f"{task_set.name}: duplicate task id"
    print(f"core: {len(ts.tasks)} tasks, families {', '.join(ts.families)}")
    for task in ts.tasks:
        print(f"  {task.id:<10} {task.family:<8} answer={task.answer}")
    print("OK - tasks")

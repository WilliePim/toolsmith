"""Build data/tasks.json, the core task set, from reference implementations.

Inputs:  a fixed seed; gstin_1 reuses the PDF's own four prefixes
Outputs: data/tasks.json, or with --check a byte comparison against it

Every answer is computed, never typed in. gstin_check() and iso_label() are the
answer key: the agent never sees this code, only the prompts built from it.
"""

from __future__ import annotations

import argparse
import json
import random
import string
from datetime import date, timedelta
from typing import Any, Callable

from src import config

SEED = 20260918
BASE36 = string.digits + string.ascii_uppercase
BATCH_SIZE = 4           # inputs per visible task and per held-out batch
HOLDOUT_BATCHES = 3
EDGES_PER_BATCH = 2      # edge-case inputs in every held-out batch


# --- The answer key ------------------------------------------------------------

def gstin_check(prefix: str) -> str:
    """The standard GSTIN check character for a 14-character prefix."""
    total = 0
    for index, char in enumerate(prefix):
        product = BASE36.index(char) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36       # fold the digits back mod 36
    return BASE36[(36 - total % 36) % 36]


def iso_label(day: date) -> str:
    """The ISO week label YYYY-Www-D, whose year is the ISO week-numbering year."""
    year, week, weekday = day.isocalendar()
    return f"{year}-W{week:02d}-{weekday}"


# --- The edge cases, which only held-out batches may contain --------------------

def gstin_is_edge(prefix: str) -> bool:
    """A check character that is a digit rather than a letter."""
    return gstin_check(prefix).isdigit()


def isoweek_is_edge(day: date) -> bool:
    """A date whose ISO week belongs to the neighbouring year."""
    return day.isocalendar().year != day.year


def _near_new_year(day: date, margin: int = 10) -> bool:
    """Within `margin` days of 1 January, on either side."""
    return (day - date(day.year, 1, 1)).days < margin or \
           (date(day.year, 12, 31) - day).days < margin


# --- Contracts: byte-identical in every task of a family ------------------------

GSTIN_EXAMPLE = ["22AAAAA0000A1Z", "07AABCS1429B1Z"]
GSTIN_1 = ["16TEUYJ4263R1Z", "14ELRKY8914Q4Z", "03ZPVMA6122X3Z", "07RJXDS8075B1Z"]
ISO_EXAMPLE = [date(2025, 3, 17), date(2024, 7, 4)]

GSTIN_CONTRACT = (
    "A GSTIN is 15 characters long. The last one is a check character derived from "
    "the first 14 by the standard GSTIN checksum: each character is read as a base-36 "
    "digit (0-9 then A-Z), weighted alternately by 1 and 2 starting with 1 at the "
    "first character, and the digits of each weighted product are folded back modulo "
    "36. You are given several prefixes and must return every check character, in the "
    "order the prefixes are given, with nothing between them. As a worked example, "
    f"{', '.join(GSTIN_EXAMPLE)} give \"{''.join(map(gstin_check, GSTIN_EXAMPLE))}\"."
)

ISO_CONTRACT = (
    "An ISO week label has the form YYYY-Www-D: the ISO week-numbering year, the "
    "letter W, the two-digit ISO week number, and the ISO weekday number, 1 for Monday "
    "to 7 for Sunday. ISO weeks start on Monday, week 1 is the week that holds the "
    "year's first Thursday, and the year in the label is the year its week belongs to. "
    "You are given several dates and must return every label, in the order the dates "
    "are given, separated by commas with no spaces. As a worked example, "
    f"{', '.join(map(str, ISO_EXAMPLE))} give \"{','.join(map(iso_label, ISO_EXAMPLE))}\"."
)


def _gstin_prompt(prefixes: list[str]) -> str:
    return (f"{GSTIN_CONTRACT}\n\nWhat are the check characters for these GSTIN "
            f"prefixes: {', '.join(prefixes)}?\n\nAnswer with the check characters "
            f"in order, joined into one string with nothing between them.")


def _iso_prompt(days: list[date]) -> str:
    return (f"{ISO_CONTRACT}\n\nWhat are the ISO week labels for these dates: "
            f"{', '.join(map(str, days))}?\n\nAnswer with the labels in order, "
            f"separated by commas with no spaces.")


# --- Inputs ----------------------------------------------------------------------

def _random_gstin_prefix(rng: random.Random) -> str:
    """A plausible prefix: state code, PAN (5 letters, 4 digits, 1 letter), entity, Z."""
    return (f"{rng.randint(1, 37):02d}"
            + "".join(rng.choices(string.ascii_uppercase, k=5))
            + "".join(rng.choices(string.digits, k=4))
            + rng.choice(string.ascii_uppercase)
            + rng.choice("123456789") + "Z")


def _random_plain_date(rng: random.Random) -> date:
    """A date in 2015-2030 that is nowhere near a year boundary."""
    while True:
        day = date(2015, 1, 1) + timedelta(days=rng.randrange(16 * 365))
        if not _near_new_year(day):
            return day


def _random_edge_date(rng: random.Random) -> date:
    """A date from the last or first days of a year whose ISO week crosses it."""
    while True:
        year = rng.randint(2015, 2030)
        day = rng.choice([date(year, 12, d) for d in (29, 30, 31)]
                         + [date(year, 1, d) for d in (1, 2, 3)])
        if isoweek_is_edge(day):
            return day


def _batch(rng: random.Random, seen: set, plain: Callable, edge: Callable,
           edges: int) -> list:
    """BATCH_SIZE fresh inputs, `edges` of them edge cases, in a shuffled order."""
    picked: list = []
    for maker, wanted in ((edge, edges), (plain, BATCH_SIZE - edges)):
        taken = 0
        while taken < wanted:
            item = maker(rng)
            if item not in seen:
                seen.add(item)
                picked.append(item)
                taken += 1
    rng.shuffle(picked)
    return picked


def _gstin_plain(rng: random.Random) -> str:
    while True:
        prefix = _random_gstin_prefix(rng)
        if not gstin_is_edge(prefix):
            return prefix


def _gstin_edge(rng: random.Random) -> str:
    while True:
        prefix = _random_gstin_prefix(rng)
        if gstin_is_edge(prefix):
            return prefix


# --- Assembly --------------------------------------------------------------------

def _family(name: str, label: str, contract: str, returns: str, tool_params: dict,
            tool_returns: str, joiner: str, hint: str, tasks: list, holdout: list) -> dict:
    return {"family": name, "label": label, "contract": contract, "returns": returns,
            "tool_params": tool_params, "tool_returns": tool_returns, "joiner": joiner,
            "holdout_hint": hint, "tasks": tasks, "holdout": holdout}


def build() -> dict[str, Any]:
    """The whole core set, deterministic for a given SEED."""
    rng = random.Random(SEED)

    seen: set = set(GSTIN_EXAMPLE) | set(GSTIN_1)
    gstin_2 = _batch(rng, seen, _gstin_plain, _gstin_edge, edges=0)
    gstin_hold = [_batch(rng, seen, _gstin_plain, _gstin_edge, EDGES_PER_BATCH)
                  for _ in range(HOLDOUT_BATCHES)]

    seen = set(ISO_EXAMPLE)
    iso_1 = _batch(rng, seen, _random_plain_date, _random_edge_date, edges=0)
    iso_2 = _batch(rng, seen, _random_plain_date, _random_edge_date, edges=0)
    iso_hold = [_batch(rng, seen, _random_plain_date, _random_edge_date, EDGES_PER_BATCH)
                for _ in range(HOLDOUT_BATCHES)]

    def gstin_task(task_id: str, prefixes: list[str]) -> dict:
        return {"id": task_id, "prompt": _gstin_prompt(prefixes),
                "calls": [{"prefix": p} for p in prefixes],
                "answer": "".join(map(gstin_check, prefixes))}

    def iso_task(task_id: str, days: list[date]) -> dict:
        return {"id": task_id, "prompt": _iso_prompt(days),
                "calls": [{"date": str(d)} for d in days],
                "answer": ",".join(map(iso_label, days))}

    return {
        "set": "core",
        "generated_by": "src/taskgen.py",
        "families": [
            _family("gstin", "GSTIN check character", GSTIN_CONTRACT,
                    "the check characters in order, joined into one string with "
                    "nothing between them",
                    {"prefix": {"type": "string",
                                "description": "the first 14 characters of a GSTIN"}},
                    "the check character for that prefix, as a one-character string",
                    "", "some of them have a check character that is a digit rather "
                    "than a letter",
                    [gstin_task("gstin_1", GSTIN_1), gstin_task("gstin_2", gstin_2)],
                    [{"calls": [{"prefix": p} for p in batch],
                      "expect": "".join(map(gstin_check, batch))} for batch in gstin_hold]),
            _family("isoweek", "ISO week label", ISO_CONTRACT,
                    "the labels in order, separated by commas with no spaces",
                    {"date": {"type": "string", "description": "a date as YYYY-MM-DD"}},
                    "the ISO week label for that date, such as 2025-W12-1",
                    ",", "some of them fall within a few days of a year boundary",
                    [iso_task("isoweek_1", iso_1), iso_task("isoweek_2", iso_2)],
                    [{"calls": [{"date": str(d)} for d in batch],
                      "expect": ",".join(map(iso_label, batch))} for batch in iso_hold]),
        ],
    }


# --- Checks ----------------------------------------------------------------------

_REFERENCE = {
    "gstin": (lambda call: gstin_check(call["prefix"]),
              lambda call: gstin_is_edge(call["prefix"])),
    "isoweek": (lambda call: iso_label(date.fromisoformat(call["date"])),
                lambda call: isoweek_is_edge(date.fromisoformat(call["date"]))),
}


def validate(doc: dict[str, Any]) -> None:
    """Assert every property the task set promises. Raises AssertionError."""
    assert ''.join(map(gstin_check, GSTIN_EXAMPLE)) == "CW", "PDF worked example"
    assert ''.join(map(gstin_check, GSTIN_1)) == "KXMS", "PDF gstin_1 answer"
    for fam in doc["families"]:
        answer_of, is_edge = _REFERENCE[fam["family"]]
        inputs = [c for t in fam["tasks"] for c in t["calls"]] + \
                 [c for b in fam["holdout"] for c in b["calls"]]
        assert len({json.dumps(c, sort_keys=True) for c in inputs}) == len(inputs), \
            f"{fam['family']}: an input appears twice"
        for task in fam["tasks"]:
            assert task["prompt"].startswith(fam["contract"] + "\n\n"), task["id"]
            assert not any(map(is_edge, task["calls"])), f"{task['id']}: edge case visible"
            assert task["answer"] == fam["joiner"].join(map(answer_of, task["calls"])), \
                f"{task['id']}: answer does not match the answer key"
        for index, batch in enumerate(fam["holdout"], 1):
            edges = sum(map(is_edge, batch["calls"]))
            assert edges >= EDGES_PER_BATCH, f"{fam['family']} batch {index}: {edges} edges"
            assert batch["expect"] == fam["joiner"].join(map(answer_of, batch["calls"])), \
                f"{fam['family']} batch {index}: expect does not match the answer key"


def render(doc: dict[str, Any]) -> str:
    """The exact bytes written to disk, so --check can compare them."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="compare with the committed file instead of writing it")
    args = parser.parse_args()

    doc = build()
    validate(doc)
    text = render(doc)
    path = config.TASK_SETS["core"]

    if args.check:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current != text:
            print(f"DIFFERENT - {path.relative_to(config.ROOT_DIR)} is not what "
                  f"taskgen builds. Run: uv run python -m src.taskgen")
            return 1
        print(f"OK - {path.relative_to(config.ROOT_DIR)} matches the generator")
        return 0

    config.ensure_dirs()
    path.write_text(text, encoding="utf-8", newline="\n")
    for fam in doc["families"]:
        print(f"{fam['family']}")
        for task in fam["tasks"]:
            print(f"  {task['id']:<10} {task['answer']}")
        for index, batch in enumerate(fam["holdout"], 1):
            _, is_edge = _REFERENCE[fam["family"]]
            edges = sum(map(is_edge, batch["calls"]))
            print(f"  held-out {index} {batch['expect']}  ({edges} edge cases)")
    print(f"OK - taskgen wrote {path.relative_to(config.ROOT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

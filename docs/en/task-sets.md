# Task sets

*[Italiano](../it/task-sets.md) · English*

The task families are the **test course**, not the product. The product is the machinery — the loop, the guard, the sandbox, the registry. Each family is shaped like a cone on a driving course, placed to trigger one part of that machinery.

For a family to earn its place, its task must:

| The task must… | so that we can test… |
|---|---|
| be badly served by `calc`/`today` | that the agent decides to **write a tool** |
| state its rule + a worked example | that the model can write the tool **and its own tests** |
| have one exact answer | **automatic grading** (correct / wrong) |
| hide an edge case in held-out inputs only | that the **held-out check** catches a tool that passes its own tests but is wrong |
| come in pairs (`_1`, `_2`) | **reuse**: the second task calls the saved tool |

## The two sets

`core` (`data/tasks.json`) is faithful to the tutorial. `finance` (`data/tasks_finance.json`) is a second set, chosen with `--set finance`, that shows the same machinery handling different rules.

### `core` — GSTIN and ISO week

- **GSTIN check character** is an *arithmetic* trap: a base-36 checksum over 14 characters. The hidden edge case is a check character that comes out as a **digit**, not a letter — a tool that always maps through the letter table passes its visible letter-answer tests and fails there.
- **ISO week label** is a *conceptual* trap. The naive `f"{d.year}-W{week}"` passes every visible task but fails on a date like 2024-12-30, whose ISO week is `2025-W01-1` because that week belongs to 2025. The held-out check catches it; the model gets only the hint and repairs the tool with `isocalendar()`. That write → reject → repair cycle is the project's key moment.

### `finance` — ISIN and trading sessions

- **ISIN check digit**: each letter becomes two digits, so a letter in the body shifts the Luhn doubling for everything to its left. The visible codes have digits only; the hidden ones put letters in both even and odd body positions, so a position-counting bug cannot pass by luck. Answers are cross-checked against `python-stdnum`.
- **Trading session**: the nth session after a date, given the market's holiday list **as a parameter**. Every visible Stockholm input lands on a US holiday that is a normal Stockholm session, so a tool using the NYSE list gets all six wrong. One hidden batch feeds the Stockholm list *during the NYSE task*, so a tool that ignores its `closures` argument is refused at registration. Answers are cross-checked against `exchange-calendars`.

The full confirmed lists are in [design.md](design.md), Appendix A.

## The task-file schema

```json
{ "set": "core",
  "generated_by": "src/taskgen.py",
  "families": [{
    "family": "gstin",
    "label": "GSTIN check character",
    "contract": "the rule + a worked example, byte-identical in every task",
    "returns": "how the whole task's answer is joined",
    "tool_params": {"prefix": {"type": "string", "description": "..."}},
    "tool_returns": "what one run() call returns",
    "joiner": "",
    "holdout_hint": "some have a check character that is a digit ...",
    "tasks":   [{"id": "gstin_1", "prompt": "...", "calls": [{"prefix": "16TEUYJ4263R1Z"}], "answer": "KXMS"}],
    "holdout": [{"calls": [{"prefix": "..."}], "expect": "..."}]
  }]
}
```

- **`contract`** is byte-identical across a family's tasks — that is what makes a tool reusable. If the wording drifted between task one and task two, a "reuse" count would be measuring prompt drift, not a toolbox.
- **`tool_params`** declares the exact `run()` signature the smith enforces. It is why the held-out check can call a tool with hidden inputs, and it forces the sessions tool to *receive* its holiday list instead of hard-coding it.
- **`calls`** are the inputs in machine form. They are never shown to the model — the model reads the prompt. They drive grading and the held-out check.
- **`holdout`** batches never leave the machine. A failure is reported only as a count plus `holdout_hint`.

## Adding a set

A new set is a new file plus one line in `config.TASK_SETS`. The core file never changes. This keeps three things clean:

1. Heavy generator-only dependencies (the finance set pulls in pandas via `exchange-calendars`) live in a separate `taskgen` dependency group and never reach the agent.
2. A reader sees one file and one generator per set.
3. Family ids must be unique across sets; the loader checks it.

To add one:

1. Write `src/taskgen_<name>.py` that builds the file from reference code — never hand-typed answers. Cross-check against an external library where one exists.
2. Add `"<name>": DATA_DIR / "tasks_<name>.json"` to `config.TASK_SETS`.
3. Generate it, commit the JSON, and run `--set <name>`.

Both generators support `--check` (compare the committed file byte-for-byte against a fresh build), so a task file can never silently drift from the code that produced it.

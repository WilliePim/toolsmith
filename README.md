# toolsmith

*[Italiano](README.it.md) · English*

An agent that starts with two tools — a calculator and today's date — and **writes a third when it meets a task the first two cannot do**. The tool it writes is an ordinary Python file on disk; the next task of the same kind calls it instead of writing it again, and in a measured run that cost **1/9 of the tokens**.

This is not "generate some code and run it". A tool the model writes goes through four gates before it can be called:

1. a **static guard** reads the source and either refuses it with a reason or lets it through;
2. a **sandbox** runs it in a locked-down subprocess, against the model's own tests *and* against inputs it has never seen;
3. a **registry** saves a tool that passes as `generated/<name>.py`;
4. the saved tool joins the model's tool list **the very next round**, mid-conversation.

The project is a from-scratch build based on the tutorial *"Build an Agent That Writes Its Own Tools"*, whose later half was behind a paywall. The missing modules were designed from the architecture diagram and the stated constraints, then proven with an adversarial red-team suite. The tutorial's Groq dependency is replaced by a provider-neutral layer with **Gemini** and **Claude** adapters.

## What it looks like

```
$ uv run python -m src.main run gstin_1
────────────────── gstin_1  (GSTIN check character) ──────────────────
  r2 write_tool 'gstin_check_char': registered
  r3 gstin_check_char(prefix='16TEUYJ4263R1Z') -> 'K'
  r3 gstin_check_char(prefix='14ELRKY8914Q4Z') -> 'X'
  r3 gstin_check_char(prefix='03ZPVMA6122X3Z') -> 'M'
  r3 gstin_check_char(prefix='07RJXDS8075B1Z') -> 'S'
  r4 submit_answer -> 'KXMS' correct
```

## A measured run

All eight tasks, `gemini-3.8-flash`, one pass, no repairs needed. The `_2` task of
each family writes nothing — it calls the tool the `_1` task left behind.

| task | answer | ok | rounds | tokens in | tokens out | wrote | calls |
|---|---|---|---|---|---|---|---|
| gstin_1 | KXMS | OK | 4 | 8,559 | **1,734** | `gstin_check_char` | 4 |
| gstin_2 | HXOW | OK | 3 | 3,569 | **197** | – (reused) | 6 |
| isoweek_1 | 2027-W31-6,… | OK | 3 | 4,031 | 352 | `iso_week_label` | 4 |
| isoweek_2 | 2019-W19-2,… | OK | 3 | 4,048 | 644 | – (reused) | 5 |
| isin_1 | 071522 | OK | 3 | 5,459 | 859 | `isin_check_digit` | 6 |
| isin_2 | 051817 | OK | 8 | 13,765 | 1,029 | – (reused) | 7 |
| sessions_1 | 2025-02-12,… | OK | 3 | 6,795 | 1,654 | `nth_trading_session` | 6 |
| sessions_2 | 2025-02-20,… | OK | 3 | 6,797 | 1,214 | – (reused) | 6 |

Two things in that table are the whole point:

- **Reuse pays: 1/9 of the tokens.** `gstin_2` answered with **197** output tokens
  against `gstin_1`'s **1,734**, because the tool already existed. Same family, same
  rule, same correct answer — the only difference is that the second task had a tool
  to call.
- **Reuse is real, not a copy.** `sessions_2` runs on Nasdaq Stockholm, but calls the
  tool written for *NYSE*, passing Stockholm's holiday list as an argument. A tool
  that had hard-coded the US holidays would have got all six dates wrong; the
  held-out check refuses that tool at registration.

The tool it wrote for that family, unedited:

```python
import datetime

def run(start: str, n: int, closures: list) -> str:
    cur = datetime.date.fromisoformat(start)
    holidays = set(closures)
    count = 0
    while count < n:
        cur += datetime.timedelta(days=1)
        if cur.weekday() < 5 and cur.isoformat() not in holidays:
            count += 1
    return cur.isoformat()
```

## Quickstart

You need [Python 3.12+](https://www.python.org/) and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                              # install the locked dependencies
cp .env.example .env                 # then paste a free Gemini key into .env
```

A free Gemini API key comes from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (no credit card). Paste it into `.env` as `GEMINI_API_KEY=...`. To use Claude instead, set `PROVIDER=claude` and `ANTHROPIC_API_KEY=...` (billed per use, from [console.anthropic.com](https://console.anthropic.com); a Claude.ai subscription is not API access).

```bash
uv run python -m src.main redteam            # prove both security layers — no API key needed
uv run python -m src.main run gstin_1        # solve one task
uv run python -m src.main run --all          # the whole core set
uv run python -m src.main run --all --set finance
uv run python -m src.main tools              # list the tools the agent has written
uv run python -m src.main show gstin_check_char
uv run python -m src.main reset              # empty the toolbox
```

Add `--provider claude` to any `run` to switch model for that command.

## The tasks

Two task **sets**, each with two **families**, each family with two tasks so the second reuses the first's tool. The families are chosen to force each part of the machinery; see [docs/en/task-sets.md](docs/en/task-sets.md).

| Set | Family | The rule | The hidden edge case |
|---|---|---|---|
| `core` | GSTIN check character | a base-36 checksum over 14 characters | a check character that is a digit, not a letter |
| `core` | ISO week label | `YYYY-Www-D` from a date | a date whose ISO week belongs to the neighbouring year |
| `finance` | ISIN check digit | letters → digits, then Luhn | letters in the body shift the Luhn doubling |
| `finance` | trading session | the nth session after a date | a market holiday inside the range |

Every task file is generated from reference code (`src/taskgen.py`, `src/taskgen_finance.py`); the finance answers are cross-checked against `python-stdnum` and `exchange-calendars`.

## How it is built

Each module has a `__main__` self-check you can run on its own (`uv run python -m src.<module>`). The security layers are proven with no API calls:

```bash
uv run python -m src.redteam     # 36 attacks contained, 7 benign tools pass
```

Read more:

- [docs/en/build-journal.md](docs/en/build-journal.md) — every step, why it was built that way, and the mistakes made along the road (the best place to start).
- [docs/en/architecture.md](docs/en/architecture.md) — the loop, the four gates, the two security layers, as diagrams.
- [docs/en/security.md](docs/en/security.md) — the guard, the sandbox, what each can and cannot see, and the known limits.
- [docs/en/task-sets.md](docs/en/task-sets.md) — why these families, the task-file schema, how to add a set.
- [docs/en/design.md](docs/en/design.md) — the design decisions behind the build.

## Layout

```
src/
  config.py             every setting in one place
  taskgen.py            builds data/tasks.json (core set)
  taskgen_finance.py    builds data/tasks_finance.json (finance set)
  tools.py              the two starting tools (calc, today)
  llm.py                one door to the model
  providers/            gemini.py, claude.py, and the neutral shapes in base.py
  protocol.py           the sandbox preamble, footer and result parsing
  sandbox.py            runs a tool in a locked-down subprocess
  guard.py              the static AST layer
  registry.py           the toolbox that grows, as files
  smith.py              write, check, register
  tasks.py, prompts.py  typed tasks, and what the model is told
  agent.py              the round loop and the one line
  attacks.py, redteam.py  the adversarial proof
  main.py               the command line
```

## Safety note

The sandbox denies OS, filesystem and network access via a Python audit hook, and runs each tool in an isolated subprocess with a scrubbed environment (no API keys), a timeout and an output cap. On POSIX it also sets hard CPU and memory limits; on Windows, memory is bounded only by the timeout. It is a strong barrier for a demo, not a claim of perfect isolation — do not point this at untrusted input on a machine you cannot afford to lose. See [docs/en/security.md](docs/en/security.md).

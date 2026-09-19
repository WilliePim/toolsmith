# toolsmith

*[Italiano](README.it.md) · English*

An agent that starts with two tools — a calculator and today's date — and **writes a third when it meets a task the first two cannot do**. The tool it writes is an ordinary Python file on disk; the next task of the same kind calls it instead of writing it again.

This is not "generate some code and run it". A tool the model writes goes through four gates before it can be called:

1. a **static guard** reads the source and either refuses it with a reason or lets it through;
2. a **sandbox** runs it in a locked-down subprocess, against the model's own tests *and* against inputs it has never seen;
3. a **registry** saves a tool that passes as `generated/<name>.py`;
4. the saved tool joins the model's tool list **the very next round**, mid-conversation.

The project is a from-scratch build based on the tutorial *"Build an Agent That Writes Its Own Tools"*, whose later half was behind a paywall. The missing modules were designed from the architecture diagram and the stated constraints, then proven with an adversarial red-team suite. The tutorial's Groq dependency is replaced by a provider-neutral layer with **Gemini** and **Claude** adapters.

## What it looks like

```
$ uv run python -m src.main run gstin_1
──────────────────────────── gstin_1  (GSTIN check character) ────────────────────────────
  r1 write_tool 'gstin_check_char': registered
  r2 gstin_check_char(prefix='16TEUYJ4263R1Z') -> 'K'
  r2 gstin_check_char(prefix='14ELRKY8914Q4Z') -> 'X'
  r2 gstin_check_char(prefix='03ZPVMA6122X3Z') -> 'M'
  r2 gstin_check_char(prefix='07RJXDS8075B1Z') -> 'S'
  r3 submit_answer -> 'KXMS' correct
```

Run `gstin_2` next and it calls the tool it already has, for a fraction of the tokens.

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

# Build journal

*[Italiano](../it/build-journal.md) · English*

This is the story of how toolsmith was built, one step at a time: what each step did, **why** it was done that way, and the mistakes made along the road. It is written for someone learning how an agent like this is put together, not just what the final code contains. Each step ends with the command that proves it works.

Read it top to bottom, or jump to a module you are looking at in `src/`.

---

## Before any code: reading the problem

The project follows a tutorial, *"Build an Agent That Writes Its Own Tools"*. Only its first half was readable; the rest was behind a paywall. So the first decision was **not to try to recover the hidden text** — instead, design the missing modules from what the first half fixes: the architecture diagram, the table of contents, and the constraints stated in prose.

Three things were settled before writing a line:

- **The checksum had to be verified, not trusted.** The tutorial's GSTIN example claims two answers: `CW` (a worked example) and `KXMS` (the first task). A ten-line script reproduced both, which pinned down the exact algorithm. The tutorial's *sample* hidden input (`29AAGCB7383J1Z → ISUQ`) turned out to be illustrative only — the real check character is `4`. Lesson: **a specification's examples can be wrong; a reference implementation you can run is the real answer key.** Every task file in this project is generated from reference code, never typed by hand.
- **No Groq.** The tutorial talks to Groq. This build is provider-neutral, with a Gemini adapter (the default) and a Claude adapter. That choice rippled through the whole model layer.
- **The visible code had security gaps worth fixing.** Reading the tutorial's guard and sandbox carefully turned up several holes — `except BaseException` swallowing the sandbox's own signal, a path check fooled by `..` and Windows casing, format-string attribute traversal, module pivots like `typing.sys`. These became the hardening work in steps 6–8.

There was also a round of plain-language questions worth capturing, because they are the mental model the whole project rests on:

- **A "tool" has two halves.** A JSON *description* (what the model reads) and Python *code* (what our program runs). The model only ever emits JSON asking for a tool by name; it never runs anything.
- **It is a loop, not recursion.** The model is stateless. Every round, *our* program resends the whole conversation, the model replies with tool calls, we run them and append the results, and the next round begins.
- **The task families are the test course, not the product.** GSTIN and ISO week (and later ISIN and trading sessions) are cones on a driving course: each is shaped to trigger one part of the machinery.

---

## Step 0 — Git

**What.** A `.gitignore` (`.env`, `.venv/`, `__pycache__/`, `generated/*.py|json`, and the tutorial PDF), an initial commit on `master`, then `git switch -c develop` for all the work.

**Why.** A branch needs a commit to grow from, and the repo had none. `.gitignore` came first because this project *writes files by itself* and holds an API key in `.env` — the two things you least want committed by accident.

**Verify.** Before committing, `git status` showed only `.gitignore`; the PDF, previously an untracked file, had disappeared from the list — proof the ignore rule worked. Git on Windows prints a harmless "LF will be replaced by CRLF" warning about line endings, addressed next.

---

## Step 1 — Scaffold

**What.** `uv init --bare` (just a `pyproject.toml`, no example file to delete), Python pinned to 3.13 locally but `requires-python >= 3.12` so a portfolio reader on 3.12 can run it. Four runtime dependencies: `anthropic`, `google-genai`, `python-dotenv`, `rich`. Folders `src/`, `data/`, `generated/`, `docs/en`, `docs/it`. A `.env.example` (committed) documenting every setting, and a real `.env` (ignored) for the key.

**Why.** `uv.lock` records exact versions, so anyone who clones gets an identical install. `generated/` gets a `.gitkeep` so the folder exists in a fresh clone even though its contents are ignored — an empty folder is invisible to git.

A small but important habit started here: **`.gitattributes` with `* text=auto eol=lf`.** It normalises line endings to LF in the repository whatever the OS, so the repo looks the same everywhere and Git stops warning on Windows.

**Verify.** `uv run` imported all four packages; Python 3.13.15; `git check-ignore .env` confirmed the key file is ignored.

---

## Step 2 — `config.py`, every knob in one place

**What.** One module holds paths, the `TASK_SETS` registry (a set name → its file), provider settings, the agent's budget, the sandbox limits, and the import allowlist. `require_api_key()` fails early with the URL where you get a key.

**Why one file.** When a number needs changing, there is one place to look. This is the tutorial's idea, kept.

**Decisions worth naming.**

- `PROVIDER` is read at call time (a module attribute), so the CLI's `--provider` flag can override it later.
- The Gemini default model, `gemini-3.6-flash`, was **not** chosen from memory. Grepping the *installed* `google-genai` package showed its own API examples use that ID. It is confirmed against the live account in step 5.
- The Groq-only knobs (tokens-per-minute, a reservation arithmetic) were dropped. `MAX_ROUNDS = 10` was kept, and the tutorial's reasoning with it: three rejected tools, the round that registers one, the round that calls it, the round that answers — that is already six, and a single-input tool called once per item adds more.
- A tutorial claim was **corrected**: a comment there says `uv run` on Windows does not inherit the shell environment. The real reason to use `python-dotenv` is simply that keys belong in a file, not the shell. (Verified: a shell `PROVIDER=claude` does beat `.env`, because `load_dotenv` does not override existing variables.)

**Verify.** The self-check prints a settings table; `PROVIDER=claude` switches the model; `PROVIDER=groq` exits 1 with "Unknown provider". A useful discovery: running `python -m src.config` from the repo root already puts the current directory on the import path, so the tutorial's `PYTHONPATH=.` prefix is unnecessary here.

---

## Step 3 — `taskgen.py`, the core task set from a reference

**What.** Reference implementations `gstin_check()` and `iso_label()` are the answer key. From them the generator builds two families (GSTIN, ISO week), each with a byte-identical contract, a worked example, two visible tasks, three held-out batches, and a hint. The first task reuses the tutorial's exact inputs (answer `KXMS`); the rest is seeded, so the file is reproducible.

**Why generated.** Because the tutorial's own hidden-input sample was wrong. A generator with a reference implementation cannot disagree with itself, and `--check` compares the committed file byte-for-byte against a fresh build.

**A worthwhile contrast for later.** The GSTIN contract, kept verbatim from the tutorial, says "the standard GSTIN checksum" and never actually states the final `(36 - s % 36) % 36` step — it leans on the model's own knowledge plus the worked example. The finance contracts (step 14) are deliberately self-contained. Both styles are valid; the difference is worth understanding.

**The lesson of this step is about testing the test.** The generator has a `validate()` that asserts every promised property (worked examples, identical contracts, answers matching the key, no edge case visible, at least two edges per hidden batch). To trust it, I broke the document on purpose four ways. The first attempt "caught" all four — but two were caught by the *wrong* check (a reused input tripped an "input appears twice" assertion before the intended one), and one assertion had no message at all. **A check that fires for the wrong reason is not a passing test.** The fix: fresh inputs for each mutation, a message on every assertion, and an assert that the *right* message fired.

**Pitfalls hit.** Editing a Python string through a shell heredoc wrote a literal `\n` into the source and broke it — multi-line edits belong in a real editor, not `sed`. And running a script stored in the system temp folder failed with `ModuleNotFoundError: src`, because Python puts the *script's* folder on the path, not the working directory; piping via stdin (`python - < file`) or `python -m` from the repo root fixes it.

**Verify.** `python -m src.taskgen` asserts `CW` and `KXMS`, writes the file, and a second run is byte-identical.

---

## Step 4 — `tools.py`, the two starting tools

**What.** `calc` (a restricted-AST arithmetic evaluator) and `today`. `call()` never raises — a failure is text the model can read and repair. Schemas use a neutral `{name, description, parameters}` shape each provider adapter wraps.

**The improvement over the tutorial** is one line of thinking: **"trusted code" is not "trusted input".** `calc` runs inside the agent's own process because we wrote it — but its *argument* comes from the model. `9 ** 9 ** 9` is an integer with about a hundred million digits; evaluating it would hang the agent for a long time. So `calc` caps the expression length and refuses an exponent tower before computing it. The sandbox (later) protects us from the model's *code*; our own tools still have to defend against the model's *arguments*.

**Verify.** `calc('(36 - 221 % 36) % 36') → 31`, the tower is refused in under a tenth of a second, wrong arguments come back as `ERROR: wrong arguments`.

---

## Step 5 — `llm.py` and the provider adapters

**What.** One door to the model. `providers/base.py` holds neutral shapes: `ToolCall` (arguments already parsed), `ToolResult`, `Completion` (whose `raw` field carries the provider's own assistant turn), and `ProviderError` with a `kind` — `rate`, `busy`, `malformed`, `daily`, or `fatal`. Each adapter's `generate()` raises `ProviderError`; `llm.complete()` owns the retry policy and **never raises** — a rate limit, a botched tool call, a spent daily quota all come back as a named `Completion`.

**The rule that shaped this step: never write SDK calls from memory.** Both packages had moved on, so I inspected the *installed* code — signatures, model fields, the error classes — before writing anything.

- `google-genai` 2.24.0: `client.aio.models.generate_content(model, contents, config)`; function declarations built from JSON schema; `thinking_level` for Gemini 3 but a token budget for Gemini 2.x; `FunctionCall` carries an `id`; the SDK only retries if you pass retry options (so I pass "one attempt" explicitly, keeping every failure visible); `HttpOptions.timeout` is in **milliseconds**.
- `anthropic` 1.7.0: `messages.create` has **no `temperature` parameter at all** on Opus 5; `with_raw_response` now needs `await raw.parse()`; typed errors include `OverloadedError` (529); `beta.messages.create` carries the `fallbacks` parameter.

**Why each adapter owns its message shapes.** Gemini's thinking models attach *thought signatures* to the parts of their reply, and Claude's *thinking blocks* must be echoed back unchanged; a rebuilt copy of the turn would drop them. So each adapter appends the model's own turn object verbatim. Claude also wants **all** tool results of one turn in a single user message — splitting them teaches it to stop making parallel calls.

**The temperature ladder disappears.** The tutorial retries a malformed generation at rising temperatures because at temperature 0 a retry redraws the *identical* sample. Claude Opus 5 has no temperature knob, and Gemini 3 is tuned for 1.0, so every retry is already a fresh draw. The retry policy stays; the temperature ladder is moot.

**A subtlety in rate limits.** Gemini's 429 error carries structured details. A `quotaId` containing `PerDay` means a *daily* limit — retrying is pointless for hours, so `complete()` stops with a plain message ("resets at midnight Pacific; another model has its own quota"). A per-minute limit instead waits for the server's own hint, parsed by a small `duration()` that reads `"7.66s"`, `"650ms"` (milliseconds tried before minutes, or `650ms` reads as 650 minutes) and a bare number of seconds.

**Verify.** The offline checks build real SDK objects and assert the shapes: Gemini thought parts excluded from the answer text, tool-call ids preserved, the Content returned by identity; Claude's request has no temperature, strict tools and an effort level, and a thinking block survives a round-trip. The one live check — forcing a tiny `echo_number(4021)` call — runs only when a key is present.

---

## Step 6 — `protocol.py`, turning source into a runnable script

**What.** A generated tool is just text. `build_script()` wraps it in a preamble that locks the interpreter down and a footer that reads calls from stdin (one JSON object per line) and prints one marked result per line. `parse_lines()` reads those results back.

**Three problems the design had to solve** — none of them visible in the tutorial's excerpt:

1. **Shadowable builtins.** The footer calls `print`, `type`, `str`. A tool that defines its own `print` would break it. So the footer imports `builtins` under a reserved name and calls `_TS_b.print`, `_TS_b.type`, and so on.
2. **Forgeable results.** A tool could simply *print* a line that looks like a result. So the marker carries a per-run random nonce; any line without it is "stray output" — kept, never parsed.
3. **Imports versus the audit hook.** The hook denies `os.listdir`. But importing a *package* for the first time lists its directory, which is a `listdir` — so the first `import json` after the hook is installed would crash. An experiment confirmed it: without preloading, `import json` after the hook took the whole process down. The fix is to **preload every allowed module before installing the hook** (a cached import fires no audit event).

**Hardening the file-open rule.** Paths are normalised (`abspath` + `normcase`) before the prefix check. An experiment showed why: `sys.path[-1] + "\..\..\..\..\Windows\win.ini"` starts with an allowed prefix *textually*, so without normalisation it would have been readable. An `os.open`-style call with write flags but no mode string is denied too.

**A self-test bug worth admitting.** I first tested the "printable ASCII marker" idea with a `\x1c` byte inside a value — but JSON forbids raw control characters, so `json.dumps` escapes it and the trap never sprang. The real trap is `U+2028`, which `json.dumps(ensure_ascii=False)` leaves raw and `str.splitlines()` splits on (but `split("\n")` does not). The test now proves `splitlines()` sees six lines where `split("\n")` sees five — which is exactly why the parser uses `split("\n")`.

**Verify.** The self-check compiles the whole script, confirms the hook comes before the tool and the imports after it, and exercises the stray/forged/missing cases of `parse_lines()`.

---

## Step 7 — `sandbox.py`, the runtime layer

**What.** `run_calls(source, calls)` writes the script to a fresh temp directory and runs it as `python -I -S -B -X utf8`, with stdin carrying the calls and a watchdog polling the clock and the output size.

**Why those flags.** `-I` isolates the interpreter (ignores environment variables, keeps the working directory off the path); `-S` drops site-packages so only the standard library is readable, reinforcing the import allowlist; `-B` stops `.pyc` writes that the write-deny would otherwise crash on; `-X utf8` because `-I` drops the encoding variable.

**The environment is scrubbed.** The child gets only `SYSTEMROOT` and a couple of harmless variables — **no API keys.** `SYSTEMROOT` stays because Windows needs it to initialise sockets and `os.urandom`.

**Verify.** A benign tool returns its values; a `while True` is killed by the watchdog; a print flood hits the output cap; and — with the guard skipped on purpose — `os.system`, reading `.env`, writing a file and opening a socket are all denied by the audit hook. That last part is the point: the two layers are independent, so the runtime holds even if the guard is bypassed.

---

## Step 8 — `guard.py`, the static layer

**What.** `check(source, params)` parses the source and returns the first violation as `"line N: reason"`, or `None`. It enforces structure (exactly one top-level `run()` with the declared parameters, only tame top-level statements, no async), the import allowlist, a set of forbidden builtins and attributes, a dunder allowlist, private attributes only on `self`, module pivots reached through aliases, format-string traversal, and any construct that could swallow the sandbox's `BaseException`.

**Why so strict, and why default-deny.** The guard sees names, not values. It cannot know a loop never ends — that is the sandbox's job. So it refuses on the *name* alone, and a construct nobody thought about is rejected, because a rejection costs one repair turn while a miss costs a wrong answer.

**A real hole, found here, not just a test bug.** `"{0.__class__}".format(x)` reaches an attribute at runtime with no `getattr` in sight. My first rule only flagged `.format` on a *non-literal* receiver, so a string literal slipped through. The fix parses the format template with `string.Formatter().parse()` and refuses any field that walks a `.` or `[`.

**A lesson about AST visitors.** For a chained attribute like `x.__class__.__bases__`, the *outer* attribute is visited first, so the message names `__bases__`, not `__class__`. Both are refused; the tests were relaxed to assert "not allowed" rather than the inner name.

**Verify.** Six benign samples pass (including `Counter.most_common`, a class using `self._n`, `try/except ValueError`) and 23 attacks are refused, each asserting the message names its reason. The full adversarial proof is the next step.

---

## Step 9 — `attacks.py` and `redteam.py`, proving both layers for free

**What.** A corpus of 27 guard attacks, 9 sandbox attacks, and 7 benign near-misses. `redteam.py` runs them all and exits non-zero if any attack gets through or any benign tool is refused. **No API calls** — this is the whole security story, proven for free, that every later step can lean on.

The sharp idea here: the sandbox attacks include the guard's own targets — `os.system`, writing a file, a socket, `os.listdir` — sent **straight to the sandbox with the guard skipped**, to prove the audit hook stands on its own.

**A bug in my own benign sample.** The "date" tool first used `__import__('datetime')` — which the guard rightly forbids. The fix *was* the intended lesson: name the parameter `date`, import the `datetime` *module* (not `from datetime import date`), so the parameter does not shadow what you need.

**Verify.** 36 attacks contained (27 by the guard, 9 by the sandbox), 7 benign tools pass, exit 0.

---

## Step 10 — `registry.py`, a toolbox that grows as files

**What.** Each tool is two files: `generated/<name>.py` (a header plus the source) and `<name>.json` (its schema, family, set, tests, and a sha256). `load_all()` re-runs the guard and the hash on every file and **skips a tampered or now-unsafe one**. `call()` always runs through the sandbox — the parent process never imports a generated tool.

**Why re-check our own files.** Defence in depth. A generated file on disk could be edited between runs; the hash catches that, and the guard runs again in case the rules tightened.

**Four bugs, all caught by the self-check** — which is exactly what a self-check is for:

1. `RESERVED_PREFIX` lives in `protocol`, not `config`.
2. The hash was computed over the source *without* the header, but reload read the file *with* it — so every tool looked tampered. Fix: hash the exact bytes on disk.
3. That created a double-header risk on re-save; fixed by stripping the header on load so the in-memory source is always pure.
4. A `slots=True` dataclass has no `__dict__`, so `record_use` uses `dataclasses.replace`.

**Verify.** Save a tool, reload it in a fresh registry, call it in the sandbox; tamper the `.py` and watch it get skipped with a hash warning. The test runs in a temp directory so the repo's `generated/` stays clean.

---

## Step 11 — `smith.py`, write, check, register

**What.** `forge(spec, family, reg)` runs the checks in order, cheapest and most-revealing first: name, parameters matching the family's interface exactly, at least two tests, the static guard, then **one sandbox run** covering the model's own tests and every held-out call.

**The privacy rule is the crux of the whole project.** A failed own test is reported in full — it is the model's own data. A failed held-out batch is reported **only as a count plus the family's hint**: no inputs, no expected values, and crucially no exception message, because an error like `invalid literal … 'R'` would echo a hidden input straight back. The test asserts the edge input and its answer are both absent from the refusal message.

**This is where the project's point lands.** A subtly wrong GSTIN tool — one that maps a check value below 10 through the letter table instead of leaving it a digit — passes its own letter-answer tests but fails the hidden digit case. It gets "failed 1 of 1 hidden checks" and the hint, and repairs itself. The correct tool registers.

**Verify.** The correct tool registers; the wrong one stops at the held-out stage with the hint and no leak; wrong parameters are named; `import os` stops at the guard stage.

---

## Step 12 — `tasks.py`, `prompts.py`, `agent.py`: the loop and the one line

**What.** `tasks.py` turns a task file into typed objects, keeping held-out inputs off the prompts. `prompts.py` holds the task-agnostic system prompt (the tool contract, and the instruction to work out test results from the worked example by hand), the interface line rendered from a family's `tool_params`, and the `write_tool`/`submit_answer` schemas. `agent.py` runs the loop.

**The one line.** Every round the toolset is rebuilt: `tools.SCHEMAS + registry.schemas() + meta_schemas(can_write)`. A tool written in round *N* is therefore callable in round *N+1* — that rebuild is the entire feature. Each tool call routes to one of four handlers (fixed tool, generated tool, `write_tool`, `submit_answer`); a refusal comes back as text the model can repair.

**The budget.** The first `write_tool` plus three repairs, then `write_tool` disappears from the toolset and the steering note escalates from a nudge, to a rounds-low warning, to "solve it with what you have".

**Verify without spending tokens.** A *scripted* fake provider, swapped into the adapter table, plays three turns (write, four parallel calls, submit) with no network. It solves `gstin_1 → KXMS`, writes one tool and makes four calls — proving the routing, the rebuild and the budget offline.

---

## Step 13 — `main.py`, the command line

**What.** `argparse` subcommands: `run` (with `--all`, `--set`, `--provider`), `tools`, `show`, `reset`, `redteam`. `run` loads the set and the registry, fails early with the key URL, solves each task with a live trace, and prints a results table.

**Verify.** `tools` shows the empty box, `reset` reports zero files, and `run` without a key prints the Gemini key URL and exits 1 — before any model call.

---

## Step 14 — `taskgen_finance.py`, a second set cross-checked against libraries

**What.** Two families — ISIN check digits and trading-session dates (NYSE and Nasdaq Stockholm, 2025) — chosen with `--set finance`. The generator computes every answer from the rule in the task text, then **cross-checks it against an external library**: ISIN digits against `python-stdnum`, session dates against `exchange-calendars`, with the text's holiday lists asserted equal to the library's and no interval touching a half day. The libraries live in a separate dependency group, so only the generator needs them — the committed JSON is pure data.

**Why a second set at all.** It shows the machinery is general: the same loop, guard, sandbox and registry handle a completely different pair of rules. The set is a separate file behind a flag, so the core set never changes and the heavy libraries never reach the agent.

**Library inspection first, again.** `stdnum.isin.calc_check_digit` reproduces the Luhn-on-expanded-digits rule; `exchange_calendars` bounds its range to the first session (so the query starts in December), exposes `early_closes` as a property, and confirmed every date in the plan — including the NYSE closure on 9 January 2025 (a national day of mourning) and the half-days that the tasks deliberately avoid.

**The trading-session design has a sharp edge.** The tool takes the holiday list as a *parameter*, and one held-out batch feeds the Stockholm list *during the NYSE task*. So a tool that ignores its `closures` argument fails at **registration**, not merely on the second task. The offline proof shows exactly that: a tool that sets `closed = set()` fails all three hidden batches.

**Verify.** The generator runs clean against both libraries and reproduces the planned answers; a fresh build is byte-identical to the committed file.

---

## The live run

Every module has a `__main__` self-check, and they all pass offline together with the red-team suite and both generators' byte checks. With a Gemini key in `.env`, the whole thing then ran for real on `gemini-3.8-flash`: **8 tasks out of 8 solved**, four tools written from scratch, and not a single repair needed.

The number that matters is the reuse:

| | rounds | output tokens | tools written |
|---|---|---|---|
| `gstin_1` | 4 | 1,734 | 1 |
| `gstin_2` | 3 | **197** | 0 — it called the one already there |

**1/9 of the tokens.** The second task never pays for reasoning about the rule, writing the code, or having it checked; it pays for the calls and the answer. The tutorial promised a fifth.

Two behaviours emerged that nobody asked for. Before trusting an existing tool, the model re-computed the contract's own worked example with it (`22AAAAA0000A1Z → C`, `07AABCS1429B1Z → W`) and only then used it on the real inputs. And `sessions_2` — running on Nasdaq Stockholm — reused the tool written during the *NYSE* task, passing Stockholm's holiday list as an argument, getting all six dates right. That is the design constraint paying off: a tool that had hard-coded the US holidays would have failed all six, and the held-out batch carrying the Stockholm list refuses such a tool at registration.

## A postscript: the run that corrected me

With a key in place, all eight tasks solved on the first pass with `gemini-3.8-flash`
and no repairs at all. Which left the most interesting path — write → rejected →
repair — proven only offline. So I ran `isoweek_1` again on a cheaper tier
(`gemini-3.5-flash-lite`) expecting it to stumble, both to show the repair loop live
and to back up a claim I had made confidently: that the Lite tier is a false economy,
because a rejected tool costs a whole extra round.

The first run obliged. The guard refused the tool, the model repaired it, and the task
finished correctly in 4 rounds and 535 output tokens against Flash's 3 rounds and 352.
Claim apparently confirmed.

Then I ran it a second time, and it passed first try in 3 rounds and **356** output
tokens — indistinguishable from Flash.

| run | rounds | output tokens |
|---|---|---|
| `gemini-3.8-flash` | 3 | 352 |
| `gemini-3.5-flash-lite`, first | 4 | 535 |
| `gemini-3.5-flash-lite`, second | 3 | 356 |

**The variance between two runs of the same model on the same task was larger than the
difference I had attributed to the model tier.** I had measured noise and narrated it
as signal. A single run of a stochastic system establishes nothing; a real comparison
needs the same task repeated five or ten times per model, reported as a distribution.

Two things came out of it worth keeping. The repair loop is now demonstrated live, not
just in the offline self-checks. And the run trace now prints *why* a tool was refused,
not just that it was — the model was always told the reason, and so should anyone
watching.

A smaller find from the same session: `gemini-2.5-flash-lite` is returned by the models
listing but answers a real request with a 404 telling new accounts to use something
newer. **Listed is not the same as available** — and the error path handled it exactly
as designed, stopping the run with a readable message instead of a traceback.

## What to build next

- A memory cap on Windows (a Job Object) to match the POSIX address-space limit.
- Batching parallel calls to one generated tool into a single sandbox process.
- More task families, to keep stress-testing the guard against real code the model writes.

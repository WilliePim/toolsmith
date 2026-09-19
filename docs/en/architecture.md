# Architecture

*[Italiano](../it/architecture.md) · English*

Five pictures. Start with the first — everything else is machinery in service of it.

## 0. What a "tool" is

A tool has two halves. The model only ever sees and writes **JSON**. The **Python** runs on your machine, inside this program.

```
 ┌────────────────────────────────────────┐   ┌──────────────────────────────────┐
 │ DESCRIPTION (JSON) - sent to the model │   │ CODE (Python) - runs on your PC  │
 │ {"name": "gstin_check_char",           │   │ def run(prefix):                 │
 │  "description": "GSTIN check char",    │   │     ...                          │
 │  "parameters": {"prefix": "string"}}   │   │     return "K"                   │
 └────────────────────────────────────────┘   └──────────────────────────────────┘
   the model reads this and answers with       the model never runs anything:
   a JSON *request*: name + arguments          our program runs it, then reports
```

It is a **loop, not recursion.** The model is stateless. Each round our program resends the whole conversation; the model replies with tool calls; we run them and append the results; the next round begins.

```
 round 1  we send:  [system, task]                 tools: calc, today, write_tool, submit_answer
          model:    write_tool({name: "gstin_check_char", source: "def run(prefix): ...", tests: [...]})
          we:       guard OK, sandbox OK, save .py + .json -> append "registered gstin_check_char"
 round 2  we send:  [system, task, call 1, result 1]   tools: ... + gstin_check_char  <- new
          model:    four calls: gstin_check_char({prefix: "16TEUYJ4263R1Z"}), ...
          we:       run the .py in the sandbox -> append "K", "X", "M", "S"
 round 3  model:    submit_answer({answer: "KXMS"})   ->  we grade it against the answer key
```

Where each half lives:

| Tool | Code half | Description half | Runs where |
|---|---|---|---|
| `calc`, `today` | `src/tools.py` | `src/tools.py` (`SCHEMAS`) | in-process (trusted) |
| `write_tool`, `submit_answer` | `agent.py` / `smith.py` | `src/prompts.py` | in-process |
| model-written | `generated/<name>.py` | `generated/<name>.json` | sandbox subprocess |

## 1. One task, end to end

```
 data/tasks*.json ── task prompt ─┐
                                  v
 ┌─────────────────────────────────────────────────────────────┐
 │ AGENT ROUND LOOP (max 10 rounds)                            │
 │  tools = calc, today                                        │
 │        + every tool saved in generated/   <- "the one line" │
 │        + write_tool, submit_answer          rebuilt EVERY   │
 │  reply = llm.complete(messages, tools)      round           │
 └──────────────────────────────┬──────────────────────────────┘
                                │ the model calls tools
     ┌────────────────┬─────────┴──────┬─────────────────┐
     v                v                v                 v
 calc / today   generated tool     write_tool      submit_answer
 in process     in the sandbox     smith.forge     (ends the task)
     └────────────────┴───────┬────────┘                 │
                              v                           v
              result text appended to messages      answer vs expected
              -> next round                          -> results table
```

## 2. What `write_tool` goes through (`smith.forge`)

```
 write_tool(name, description, source, tests)
        │
        ├─ 1. VALIDATE the spec ──✗──► "this tool must take: prefix (string)"
        ├─ 2. GUARD the source  ──✗──► "line 4: import of 'os' is not allowed"
        ├─ 3. SANDBOX runs it once: your tests + every held-out batch
        │        ──✗ own test ─────► "run({...}) returned 'X', expected 'W'"
        │        ──✗ held-out ─────► "failed 2 of 3 hidden checks" + hint
        │                            (no inputs, no values, only a count)
        └─ 4. REGISTRY saves it ───► generated/<name>.py + <name>.json
                                     -> joins the tools array next round

 ✗ = the message goes back to the model as a tool result: a repair attempt,
     not the end of the task (first try + 3 repairs per task).
```

## 3. Inside one sandbox run (`protocol.py` + `sandbox.py`)

```
 PARENT (agent process)                     CHILD: python -I -S -B -X utf8 tool.py
                                            (fresh temp dir, env with no API keys)
                                           ┌───────────────────────────────────────┐
 calls, one JSON object per line           │ PREAMBLE  audit hook, cannot be undone│
 {"prefix": "16TEUYJ4263R1Z"} ── stdin ──► │ SOURCE    the model's def run(...)    │
 {"prefix": "14ELRKY8914Q4Z"}              │ FOOTER    for each line: run(**args)  │
                                           └───────────────────┬───────────────────┘
 parse_lines()  ◄────────── stdout ─────────────────────────── ┘
   @@TOOLSMITH@@<nonce>{"ok": true, "value": "K"}   -> result
   debug: checking 16TEU...                          -> stray output, never parsed

 watchdog: every 20 ms, kill the child if it runs > 10 s or prints > 256 KB
 audit hook denies: OS/process/network calls, file writes, reads outside the stdlib
```

## 3b. Why it pays off: the reuse story

```
 run gstin_1   no tool fits -> write_tool -> checks pass -> call it -> submit "KXMS"
               the run pays for reasoning about the rule, writing the code,
               having it checked, and only then the calls

 run gstin_2   the tool is already in the tools array -> call it -> submit "HXOW"
               the run pays for the calls and the answer
```

How much that is worth varies per run and per family, so it is measured rather than
asserted: see the reuse table in the [README](../../README.md#reuse-what-the-second-task-of-a-family-costs),
which `src/report.py` regenerates from the repeated runs in `results/`.

## 4. The two security layers

| | Static guard (`guard.py`) | Runtime sandbox (`sandbox.py`) |
|---|---|---|
| When | before anything runs | while the code runs |
| Sees | **names** in the source | **values and time** |
| Blocks | `import os`, `eval`, `open`, `__class__`, bare `except`, `.format` tricks | OS/process/network, file writes, reads outside the stdlib, endless loops, output floods |
| Blind to | infinite loops, print floods | nothing it is hooked on |
| Cost of a block | one repair turn | one failed call |

`redteam.py` attacks each layer separately, including sending attacks straight to the sandbox with the guard skipped. See [security.md](security.md).

## The modules

```
config       every setting; the task-set registry
tasks        loads a task file into typed Task + Family objects
taskgen[_finance]  build the task files from reference code / libraries
tools        calc, today; the neutral SCHEMAS shape
llm + providers/   one door to Gemini or Claude; never raises
protocol     build_script() (preamble + source + footer), parse_lines()
sandbox      run_calls(): the locked-down subprocess and its watchdog
guard        check(): the static AST layer
registry     the .py + .json files, load/save/call/reset
smith        forge(): the four-gate write-check-register gauntlet
prompts      the system prompt, the interface line, the meta tools
agent        solve(): the round loop and the one line
attacks + redteam  the adversarial proof, no API calls
main         the command line
```

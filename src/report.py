"""Turn the saved runs into summary tables, and write them into the README.

Inputs:  results/runs/*.json (from bench.py), results/sandbox_*.json (from redteam.py)
Outputs: results/summary.json and the generated blocks inside README.md / README.it.md

    uv run python -m src.report

Every number a document shows comes from here. Nothing is typed by hand, so a
claim cannot drift away from the run that produced it: re-running the bench and
this script is the only way to change a figure.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src import config

RESULTS_DIR = config.ROOT_DIR / "results"
RUNS_DIR = RESULTS_DIR / "runs"
SUMMARY_PATH = RESULTS_DIR / "summary.json"

START = "<!-- GENERATED:{name}:START -->"
END = "<!-- GENERATED:{name}:END -->"


def load_runs() -> list[dict]:
    if not RUNS_DIR.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(RUNS_DIR.glob("*.json"))]


def cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens / 1e6 * config.GEMINI_PRICE_IN_PER_MTOK
            + completion_tokens / 1e6 * config.GEMINI_PRICE_OUT_PER_MTOK)


def _stats(values: Iterable[float]) -> dict[str, float]:
    data = [v for v in values]
    if not data:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    return {"mean": statistics.fmean(data), "min": min(data), "max": max(data),
            "n": len(data)}


def summarise(runs: list[dict]) -> dict[str, Any]:
    """Everything the documents quote, computed once."""
    # Provider failures are not results about the agent: excluded from accuracy,
    # counted separately so the cost of the exercise stays honest.
    usable = [r for r in runs if not r.get("api_error")]
    api_failed = [r for r in runs if r.get("api_error")]

    per_task: dict[str, dict] = {}
    for run in usable:
        key = f"{run['task']}|{run['condition']}"
        entry = per_task.setdefault(key, {
            "task": run["task"], "family": run["family"], "task_set": run["task_set"],
            "condition": run["condition"], "runs": 0, "solved": 0, "wrong": 0,
            "unfinished": 0, "refused_tools": 0, "repaired": 0, "write_attempts": 0,
            "prompt_tokens": [], "completion_tokens": [], "rounds": [],
            "refusal_stages": defaultdict(int)})
        entry["runs"] += 1
        entry["solved"] += run["correct"]
        entry["wrong"] += run["status"] == "wrong"
        entry["unfinished"] += run["status"] == "unfinished"
        entry["refused_tools"] += sum(run.get("refusals", {}).values())
        entry["repaired"] += bool(run.get("repaired"))
        entry["write_attempts"] += run.get("write_attempts", 0)
        entry["prompt_tokens"].append(run["prompt_tokens"])
        entry["completion_tokens"].append(run["completion_tokens"])
        entry["rounds"].append(run["rounds"])
        for stage, count in (run.get("refusals") or {}).items():
            entry["refusal_stages"][stage] += count

    tasks = []
    for entry in per_task.values():
        tasks.append({
            **{k: entry[k] for k in ("task", "family", "task_set", "condition", "runs",
                                     "solved", "wrong", "unfinished", "refused_tools",
                                     "repaired", "write_attempts")},
            "refusal_stages": dict(entry["refusal_stages"]),
            "prompt": _stats(entry["prompt_tokens"]),
            "completion": _stats(entry["completion_tokens"]),
            "rounds": _stats(entry["rounds"]),
            "cost_usd": cost_usd(sum(entry["prompt_tokens"]),
                                 sum(entry["completion_tokens"])),
        })
    tasks.sort(key=lambda t: (t["condition"], t["task_set"], t["task"]))

    # Reuse: within one repetition, the second task of a family against the first.
    reuse: dict[str, dict] = {}
    by_rep: dict[tuple, dict] = defaultdict(dict)
    for run in usable:
        if run["condition"] != "tools":
            continue
        by_rep[(run["family"], run["repetition"])][run["task"]] = run
    for (family, _rep), pair in by_rep.items():
        first = next((r for t, r in pair.items() if t.endswith("_1")), None)
        second = next((r for t, r in pair.items() if t.endswith("_2")), None)
        if not first or not second or first["completion_tokens"] == 0:
            continue
        slot = reuse.setdefault(family, {"ratios": [], "first": [], "second": [],
                                         "pairs": 0})
        slot["ratios"].append(second["completion_tokens"] / first["completion_tokens"])
        slot["first"].append(first["completion_tokens"])
        slot["second"].append(second["completion_tokens"])
        slot["pairs"] += 1
    reuse_summary = {
        family: {"pairs": slot["pairs"], "ratio": _stats(slot["ratios"]),
                 "first_completion": _stats(slot["first"]),
                 "second_completion": _stats(slot["second"])}
        for family, slot in reuse.items()}

    # Condition comparison.
    conditions = {}
    for name in ("tools", "baseline"):
        subset = [r for r in usable if r["condition"] == name]
        if not subset:
            continue
        conditions[name] = {
            "runs": len(subset),
            "solved": sum(r["correct"] for r in subset),
            "accuracy": sum(r["correct"] for r in subset) / len(subset),
            "prompt": _stats(r["prompt_tokens"] for r in subset),
            "completion": _stats(r["completion_tokens"] for r in subset),
            "rounds": _stats(r["rounds"] for r in subset),
            "cost_usd": cost_usd(sum(r["prompt_tokens"] for r in subset),
                                 sum(r["completion_tokens"] for r in subset)),
        }

    failures = [{"run_id": r["run_id"], "task": r["task"], "condition": r["condition"],
                 "status": r["status"], "answer": r["answer"], "expected": r["expected"],
                 "rounds": r["rounds"], "refusals": r.get("refusals", {}),
                 "note": r.get("note", "")}
                for r in usable if not r["correct"]]

    meta = usable[0]["meta"] if usable else {}
    return {
        "generated": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "meta": meta,
        "totals": {
            "runs": len(usable), "api_failed_runs": len(api_failed),
            "api_retries": sum(r.get("api_retries", 0) for r in runs),
            "prompt_tokens": sum(r["prompt_tokens"] for r in usable),
            "completion_tokens": sum(r["completion_tokens"] for r in usable),
            "cost_usd": cost_usd(sum(r["prompt_tokens"] for r in usable),
                                 sum(r["completion_tokens"] for r in usable)),
        },
        "tasks": tasks, "reuse": reuse_summary, "conditions": conditions,
        "failures": failures,
    }


# --- Markdown rendering -------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def table_per_task(summary: dict, italian: bool) -> str:
    head = ("| task | condition | runs | solved | tool refused | repaired | rounds (mean) "
            "| out tokens mean (min-max) |") if not italian else \
           ("| task | condizione | run | risolti | tool respinti | riparati | round (media) "
            "| token out media (min-max) |")
    lines = [head, "|---|---|---|---|---|---|---|---|"]
    for t in summary["tasks"]:
        c = t["completion"]
        lines.append(
            f"| {t['task']} | {t['condition']} | {t['runs']} | "
            f"{t['solved']}/{t['runs']} | {t['refused_tools']} | {t['repaired']} | "
            f"{t['rounds']['mean']:.1f} | "
            f"{c['mean']:,.0f} ({c['min']:,.0f}-{c['max']:,.0f}) |")
    return "\n".join(lines)


def table_reuse(summary: dict, italian: bool) -> str:
    head = ("| family | pairs | first task out tokens (mean) | second task (mean) "
            "| saving, mean | saving, range |") if not italian else \
           ("| famiglia | coppie | token out primo task (media) | secondo (media) "
            "| risparmio medio | intervallo |")
    lines = [head, "|---|---|---|---|---|---|"]
    for family, r in sorted(summary["reuse"].items()):
        ratio = r["ratio"]
        if not ratio["n"]:
            continue
        lines.append(
            f"| {family} | {r['pairs']} | {r['first_completion']['mean']:,.0f} | "
            f"{r['second_completion']['mean']:,.0f} | "
            f"1/{1 / ratio['mean']:.1f} | "
            f"1/{1 / ratio['max']:.1f} - 1/{1 / ratio['min']:.1f} |")
    return "\n".join(lines)


def table_conditions(summary: dict, italian: bool) -> str:
    head = ("| condition | runs | solved | accuracy | in tokens (mean) "
            "| out tokens (mean) | total cost (USD) |") if not italian else \
           ("| condizione | run | risolti | accuratezza | token in (media) "
            "| token out (media) | costo totale (USD) |")
    lines = [head, "|---|---|---|---|---|---|---|"]
    for name, c in summary["conditions"].items():
        lines.append(
            f"| {name} | {c['runs']} | {c['solved']} | {_pct(c['accuracy'])} | "
            f"{c['prompt']['mean']:,.0f} | {c['completion']['mean']:,.0f} | "
            f"${c['cost_usd']:.2f} |")
    return "\n".join(lines)


def table_failures(summary: dict, italian: bool) -> str:
    failures = summary["failures"]
    if not failures:
        return ("_No run failed._" if not italian else "_Nessuna esecuzione fallita._")
    head = ("| run | task | condition | what happened | answer given |" if not italian else
            "| run | task | condizione | cosa è successo | risposta data |")
    lines = [head, "|---|---|---|---|---|"]
    for f in failures:
        what = f["status"]
        if f["refusals"]:
            what += " (" + ", ".join(f"{k}x{v}" for k, v in f["refusals"].items()) + ")"
        answer = (f["answer"] or "-")[:28]
        lines.append(f"| `{f['run_id']}` | {f['task']} | {f['condition']} | {what} "
                     f"| `{answer}` |")
    return "\n".join(lines)


def table_sandbox(italian: bool) -> str:
    """One row per platform report found in results/."""
    rows = []
    for path in sorted(RESULTS_DIR.glob("sandbox_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        attacks = [r for r in data["records"] if r["kind"] == "attack"]
        contained = sum(r["contained"] for r in attacks)
        by_guard = sum(r["stopped_by"] == "guard" for r in attacks if r["contained"])
        by_sandbox = sum(r["stopped_by"] == "sandbox" for r in attacks if r["contained"])
        known = data.get("known_limits", [])
        rows.append((data["platform"]["os"], data["platform"]["memory_cap"], len(attacks),
                     contained, by_guard, by_sandbox, known, data.get("escaped", [])))
    if not rows:
        return "_Not run yet._" if not italian else "_Non ancora eseguito._"

    head = ("| platform | memory cap | attacks | contained | by the guard | by the sandbox "
            "| documented limits | undeclared escapes |") if not italian else \
           ("| piattaforma | tetto memoria | attacchi | contenuti | dalla guardia "
            "| dal sandbox | limiti dichiarati | fughe non dichiarate |")
    lines = [head, "|---|---|---|---|---|---|---|---|"]
    for os_name, cap, total, contained, guard, sbox, known, escaped in rows:
        lines.append(f"| {os_name} | {cap} | {total} | {contained}/{total} | {guard} "
                     f"| {sbox} | {', '.join(k['name'] for k in known) or '-'} "
                     f"| {', '.join(escaped) or 'none'} |")
    return "\n".join(lines)


def prompt_diff(italian: bool) -> str:
    """The exact lines the baseline condition drops, generated from the prompts."""
    import difflib

    from src import prompts

    with_tools = prompts.system_prompt(True).splitlines()
    baseline = prompts.system_prompt(False).splitlines()
    body = "\n".join(difflib.unified_diff(with_tools, baseline, "with tools", "baseline",
                                          lineterm="", n=1))
    note = ("Only the tool-writing lines are removed; the opening and the closing "
            "instruction are byte-identical in both conditions."
            if not italian else
            "Vengono tolte solo le righe sugli strumenti; l'apertura e l'istruzione "
            "finale sono identiche byte per byte nelle due condizioni.")
    return f"{note}\n\n```diff\n{body}\n```"


def header_line(summary: dict, italian: bool) -> str:
    meta, totals = summary["meta"], summary["totals"]
    if italian:
        return (f"Modello **{meta.get('model', '?')}**, temperatura "
                f"*{meta.get('temperature', '?')}*, commit `{meta.get('commit', '?')}`, "
                f"eseguito il {summary['generated'][:10]}. "
                f"{totals['runs']} esecuzioni, {totals['completion_tokens']:,} token in "
                f"uscita, costo totale ${totals['cost_usd']:.2f}. "
                f"Errori del provider rilanciati: {totals['api_retries']}.")
    return (f"Model **{meta.get('model', '?')}**, temperature "
            f"*{meta.get('temperature', '?')}*, commit `{meta.get('commit', '?')}`, "
            f"run on {summary['generated'][:10]}. "
            f"{totals['runs']} runs, {totals['completion_tokens']:,} output tokens, "
            f"${totals['cost_usd']:.2f} total. "
            f"Provider errors retried: {totals['api_retries']}.")


def inject(path: Path, name: str, body: str) -> bool:
    """Replace the block between the markers. Returns True if the file changed."""
    text = path.read_text(encoding="utf-8")
    start, end = START.format(name=name), END.format(name=name)
    if start not in text or end not in text:
        return False
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    new = f"{head}{start}\n{body}\n{end}{tail}"
    if new != text:
        path.write_text(new, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> int:
    runs = load_runs()
    summary = summarise(runs)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8", newline="\n")

    blocks = {
        "bench-header": (header_line(summary, False), header_line(summary, True)),
        "bench-tasks": (table_per_task(summary, False), table_per_task(summary, True)),
        "bench-reuse": (table_reuse(summary, False), table_reuse(summary, True)),
        "bench-conditions": (table_conditions(summary, False),
                             table_conditions(summary, True)),
        "bench-failures": (table_failures(summary, False), table_failures(summary, True)),
        "sandbox": (table_sandbox(False), table_sandbox(True)),
        "prompt-diff": (prompt_diff(False), prompt_diff(True)),
    }
    changed = []
    for name, (english, italian) in blocks.items():
        if inject(config.ROOT_DIR / "README.md", name, english):
            changed.append(f"README.md:{name}")
        if inject(config.ROOT_DIR / "README.it.md", name, italian):
            changed.append(f"README.it.md:{name}")

    print(f"{len(runs)} runs ({summary['totals']['runs']} usable, "
          f"{summary['totals']['api_failed_runs']} provider failures)")
    print(f"wrote {SUMMARY_PATH.relative_to(config.ROOT_DIR)}")
    print(f"updated blocks: {', '.join(changed) if changed else 'none (already current)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

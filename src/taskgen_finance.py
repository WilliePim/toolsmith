"""Build data/tasks_finance.json: ISIN check digits and trading sessions.

Inputs:  the confirmed lists below; python-stdnum and exchange-calendars (the
         `taskgen` dependency group) to cross-check every answer
Outputs: data/tasks_finance.json, or with --check a byte comparison against it

Run it with the group:  uv run --group taskgen python -m src.taskgen_finance

Two families in two tasks each, so a tool written for the first task is exactly
what the second needs. Every answer is computed from the rule written in the
task text, then verified against an external library, so the file never depends
on one belief alone.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from typing import Any

from src import config

# --- ISIN: the confirmed set (issuer in a comment; only the code is used) ----------

ISIN_EXAMPLE = "US0378331005"       # Apple, worked example -> check digit 5

ISIN_VISIBLE = {
    "isin_1": ["DE0007164600", "IT0003128367", "FR0000120271",   # SAP, Enel, TotalEnergies
               "US5949181045", "IT0000062072", "GB0009895292"],  # Microsoft, Generali, AstraZeneca
    "isin_2": ["CH0038863350", "NL0010273215", "JP3633400001",   # Nestlé, ASML, Toyota
               "IT0000072618", "DE0007236101", "US0231351067"],  # Intesa, Siemens, Amazon
}
ISIN_HOLDOUT = [
    ["US88160R1014", "GB0002374006", "US02079K3059",             # Tesla, Diageo, Alphabet
     "DE0005190003", "NL00150001Q9", "IT0003856405"],            # BMW, Stellantis, Leonardo
    ["US30303M1027", "IE00B4L5Y983", "FR0000121014",             # Meta, iShares World, LVMH
     "US67066G1040", "DE0008404005", "IT0005239360"],            # Nvidia, Allianz, UniCredit
    ["GB00BH4HKS39", "US92826C8394", "IT0003132476",             # Vodafone, Visa, Eni
     "US46625H1005", "FR0000131104", "CH0012032048"],            # JPMorgan, BNP Paribas, Roche
]

ISIN_CONTRACT = (
    "An ISIN is 12 characters: a two-letter country code, a nine-character body, and one "
    "check digit. To find the check digit, first turn the first 11 characters into digits: "
    "each letter becomes a two-digit number by its position in the alphabet (A=10, B=11, ... "
    "Z=35) and each digit stays as it is, giving one long string of digits. Then apply the "
    "Luhn rule to that string: reading from the rightmost digit to the left, double every "
    "second digit (the 1st, 3rd, 5th, ... counting from the right), and if a doubled value is "
    "more than 9 subtract 9 from it; sum all the resulting digits; the check digit is "
    "(10 - sum modulo 10) modulo 10. You are given the first 11 characters of several ISINs "
    "and must return each check digit. As a worked example, US037833100 gives \"5\"."
)
ISIN_HINT = "some codes contain letters after the two-letter country prefix"


def isin_check_digit(prefix: str) -> str:
    """The ISIN check digit for the first 11 characters. The generator's answer key."""
    digits = "".join(str(int(ch, 36)) for ch in prefix)      # A=10..Z=35, digits unchanged
    total = 0
    for index, ch in enumerate(reversed(digits)):
        value = int(ch) * (2 if index % 2 == 0 else 1)
        total += value - 9 if value > 9 else value
    return str((10 - total % 10) % 10)


# --- Sessions: the confirmed set ---------------------------------------------------

NYSE_2025 = ["2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
             "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
             "2025-12-25"]
STO_2025 = ["2025-01-01", "2025-01-06", "2025-04-18", "2025-04-21", "2025-05-01",
            "2025-05-29", "2025-06-06", "2025-06-20", "2025-12-24", "2025-12-25",
            "2025-12-26", "2025-12-31"]

SESSIONS_EXAMPLE = ("2025-03-07", 3)        # a Friday, no closures in range -> 2025-03-12

# (start, n) pairs. sessions_1 runs on NYSE, sessions_2 on Stockholm.
SESSIONS_VISIBLE = {
    "sessions_1": ("NYSE", NYSE_2025,
                   [("2025-02-03", 7), ("2025-05-02", 10), ("2025-08-13", 4),
                    ("2025-10-10", 12), ("2025-03-18", 6), ("2025-09-15", 8)]),
    "sessions_2": ("Nasdaq Stockholm", STO_2025,
                   [("2025-02-10", 8), ("2025-07-01", 5), ("2025-08-29", 3),
                    ("2025-11-24", 5), ("2025-01-13", 5), ("2025-05-22", 3)]),
}
# Held-out batches. H3 uses the Stockholm list during the NYSE task, so a tool that
# ignores its closures argument is refused at registration, not merely later.
SESSIONS_HOLDOUT = [
    ("NYSE", NYSE_2025, [("2025-04-15", 4), ("2025-06-02", 3), ("2025-01-16", 3),
                         ("2025-08-25", 5), ("2025-10-01", 4), ("2025-12-10", 6)]),
    ("NYSE", NYSE_2025, [("2025-05-22", 2), ("2025-06-17", 3), ("2025-07-07", 5),
                         ("2025-02-13", 2), ("2025-11-18", 5), ("2025-09-26", 4)]),
    ("Nasdaq Stockholm", STO_2025, [("2025-06-04", 2), ("2025-06-18", 2), ("2025-02-03", 5),
                                    ("2025-03-10", 7), ("2025-09-08", 4), ("2025-10-13", 6)]),
]
SESSIONS_HINT = "some ranges contain a closure day"


def nth_session(start: str, n: int, closures: list[str]) -> str:
    """The nth trading session strictly after `start`. The generator's answer key."""
    closed = set(closures)
    day = date.fromisoformat(start)
    seen = 0
    while seen < n:
        day += timedelta(days=1)
        if day.weekday() < 5 and day.isoformat() not in closed:
            seen += 1
    return day.isoformat()


def _sessions_contract(exchange: str, closures: list[str]) -> str:
    example = nth_session(SESSIONS_EXAMPLE[0], SESSIONS_EXAMPLE[1], [])
    return (
        f"A trading session is a weekday (Monday to Friday) that is not a market holiday. "
        f"Half-day sessions count as full sessions. You are given a start date and a number "
        f"n, and must return the date of the nth trading session strictly after the start "
        f"date, in YYYY-MM-DD form; the start date itself is never counted. The {exchange} "
        f"market holidays for 2025 are exactly these, and this list is the only one you may "
        f"use: {', '.join(closures)}. As a worked example, starting from "
        f"{SESSIONS_EXAMPLE[0]} with n = {SESSIONS_EXAMPLE[1]} gives \"{example}\" (that "
        f"week has no holiday)."
    )


# --- Assembly ----------------------------------------------------------------------

def _isin_prompt(prefixes: list[str]) -> str:
    return (f"{ISIN_CONTRACT}\n\nWhat are the check digits for these ISIN prefixes: "
            f"{', '.join(prefixes)}?\n\nAnswer with the check digits in order, joined into "
            f"one string with nothing between them.")


def _sessions_prompt(contract: str, pairs: list[tuple[str, int]]) -> str:
    listed = ", ".join(f"({start}, {n})" for start, n in pairs)
    return (f"{contract}\n\nFor each of these (start date, n) pairs give the nth trading "
            f"session after the start: {listed}.\n\nAnswer with the dates in order, "
            f"separated by commas with no spaces.")


def build() -> dict[str, Any]:
    """The whole finance set, from the confirmed lists above."""
    isin_tasks = [{"id": task_id, "prompt": _isin_prompt([c[:11] for c in codes]),
                   "calls": [{"prefix": c[:11]} for c in codes],
                   "answer": "".join(isin_check_digit(c[:11]) for c in codes)}
                  for task_id, codes in ISIN_VISIBLE.items()]
    isin_holdout = [{"calls": [{"prefix": c[:11]} for c in batch],
                     "expect": "".join(isin_check_digit(c[:11]) for c in batch)}
                    for batch in ISIN_HOLDOUT]

    session_tasks = []
    for task_id, (exchange, closures, pairs) in SESSIONS_VISIBLE.items():
        contract = _sessions_contract(exchange, closures)
        session_tasks.append({
            "id": task_id, "prompt": _sessions_prompt(contract, pairs),
            "calls": [{"start": s, "n": n, "closures": closures} for s, n in pairs],
            "answer": ",".join(nth_session(s, n, closures) for s, n in pairs)})
    session_holdout = [{"calls": [{"start": s, "n": n, "closures": closures} for s, n in pairs],
                        "expect": ",".join(nth_session(s, n, closures) for s, n in pairs)}
                       for _, closures, pairs in SESSIONS_HOLDOUT]

    return {
        "set": "finance",
        "generated_by": "src/taskgen_finance.py",
        "families": [
            {"family": "isin", "label": "ISIN check digit", "contract": ISIN_CONTRACT,
             "returns": "the check digits in order, joined into one string with nothing "
                        "between them",
             "tool_params": {"prefix": {"type": "string",
                                        "description": "the first 11 characters of an ISIN"}},
             "tool_returns": "the check digit for that prefix, as a one-character string",
             "joiner": "", "holdout_hint": ISIN_HINT,
             "tasks": isin_tasks, "holdout": isin_holdout},
            {"family": "sessions", "label": "trading session date",
             "contract": "see each task (the holiday list differs by exchange)",
             "returns": "the dates in order, separated by commas with no spaces",
             "tool_params": {
                 "start": {"type": "string", "description": "the start date, YYYY-MM-DD"},
                 "n": {"type": "integer", "description": "which session after the start"},
                 "closures": {"type": "array", "items": {"type": "string"},
                              "description": "the market holidays, each YYYY-MM-DD"}},
             "tool_returns": "the nth trading session date after the start, as YYYY-MM-DD",
             "joiner": ",", "holdout_hint": SESSIONS_HINT,
             "tasks": session_tasks, "holdout": session_holdout},
        ],
    }


# --- Cross-check against the libraries ---------------------------------------------

def _library_check() -> None:
    """Prove every answer against python-stdnum and exchange-calendars. Raises on any gap."""
    import stdnum.isin as isin
    import exchange_calendars as xc
    import pandas as pd

    for codes in list(ISIN_VISIBLE.values()) + ISIN_HOLDOUT + [[ISIN_EXAMPLE]]:
        for full in codes:
            assert isin.is_valid(full), f"{full} is not a valid ISIN"
            assert isin_check_digit(full[:11]) == full[11] == isin.calc_check_digit(full[:11]), \
                f"{full}: check digit disagrees with stdnum"

    early: dict[str, set[str]] = {}
    full_closed: dict[str, set[str]] = {}
    for exchange, code in (("NYSE", "XNYS"), ("Nasdaq Stockholm", "XSTO")):
        cal = xc.get_calendar(code, start="2024-12-01", end="2026-01-31")
        sessions = {s.date().isoformat() for s in cal.sessions if s.year == 2025}
        weekdays = [d.date().isoformat() for d in pd.bdate_range("2025-01-01", "2025-12-31")]
        full_closed[exchange] = {d for d in weekdays if d not in sessions}
        early[exchange] = {d.date().isoformat() for d in cal.early_closes if d.year == 2025}

    # The text list must equal the library's full holidays exactly.
    assert full_closed["NYSE"] == set(NYSE_2025), full_closed["NYSE"] ^ set(NYSE_2025)
    assert full_closed["Nasdaq Stockholm"] == set(STO_2025), \
        full_closed["Nasdaq Stockholm"] ^ set(STO_2025)

    # Every session answer must equal the library's own nth session, and no interval may
    # touch an early close (half day) so that each hidden input carries one edge only.
    for exchange, closures, pairs in list(SESSIONS_HOLDOUT) + \
            [(name, cl, pr) for name, cl, pr in SESSIONS_VISIBLE.values()]:
        cal = xc.get_calendar("XNYS" if exchange == "NYSE" else "XSTO",
                              start="2024-12-01", end="2026-01-31")
        for start, n in pairs:
            answer = nth_session(start, n, closures)
            got = _nth_via_library(cal, start, n)
            assert got == answer, f"{exchange} {start} n={n}: text {answer} vs library {got}"
            span = _range(start, answer)
            assert not (early[exchange] & span), f"{start}->{answer} touches a half day"


def _nth_via_library(cal, start: str, n: int) -> str:
    import pandas as pd

    session = cal.date_to_session(start, direction="next")
    steps = n if session.date().isoformat() == start else n - 1
    for _ in range(steps):
        session = cal.next_session(session)
    return session.date().isoformat()


def _range(start: str, end: str) -> set[str]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return {(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)}


def validate(doc: dict[str, Any]) -> None:
    """Structural checks that need no library, mirroring the core generator."""
    from src.tasks import Family  # noqa: F401 - shape only

    for fam in doc["families"]:
        inputs = [json.dumps(c, sort_keys=True)
                  for t in fam["tasks"] for c in t["calls"]]
        if fam["family"] == "isin":
            assert len(inputs) == len(set(inputs)), "isin: a visible input repeats"
        for batch in fam["holdout"]:
            assert batch["expect"], f"{fam['family']}: an empty held-out answer"


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="compare with the committed file instead of writing it")
    parser.add_argument("--skip-library", action="store_true",
                        help="skip the python-stdnum / exchange-calendars cross-check")
    args = parser.parse_args()

    doc = build()
    validate(doc)
    if not args.skip_library:
        _library_check()
        print("cross-check: every ISIN and every session date agrees with the libraries")
    text = render(doc)
    path = config.TASK_SETS["finance"]

    if args.check:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current != text:
            print(f"DIFFERENT - {path.name} is not what the generator builds")
            return 1
        print(f"OK - {path.name} matches the generator")
        return 0

    config.ensure_dirs()
    path.write_text(text, encoding="utf-8", newline="\n")
    for fam in doc["families"]:
        print(fam["family"])
        for task in fam["tasks"]:
            print(f"  {task['id']:<12} {task['answer']}")
    print(f"OK - wrote {path.relative_to(config.ROOT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

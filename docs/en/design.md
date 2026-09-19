# Design

*[Italiano](../it/design.md) · English*

The decisions behind the build, and the confirmed data for the finance set. For the step-by-step story see [build-journal.md](build-journal.md); for the diagrams see [architecture.md](architecture.md).

## The problem this solves

The tutorial *"Build an Agent That Writes Its Own Tools"* is readable for its first nine sections; the rest is behind a paywall. Rather than recover the hidden text, the missing modules (sandbox, guard, registry, smith, prompts, agent, red-team, CLI) were designed from what the visible half fixes — the architecture diagram, the table of contents, the stated constraints — and then proven with an adversarial suite. The intended outcome is a working, readable reference implementation an outsider can run and learn from.

## Decisions that shaped everything

**Provider-neutral, Gemini and Claude.** The tutorial's Groq dependency is replaced by `llm.py` plus one adapter per API. Gemini is the default (a free key) and is exercised live; the Claude adapter is written in full and verified offline. The split forced a clean seam: each adapter owns its message shapes, because Gemini's thought signatures and Claude's thinking blocks must both be echoed back unchanged.

**Answers are generated, never typed.** The tutorial's own sample hidden input was wrong, so every task file is built from reference code (`taskgen.py`, `taskgen_finance.py`), with `--check` guaranteeing the committed file matches. The finance answers are cross-checked against `python-stdnum` and `exchange-calendars`.

**Two independent security layers.** The static guard reads names; the sandbox watches values and time. Neither trusts the other, and the red-team proves each alone. Several hardening fixes go beyond the tutorial's visible code — see [security.md](security.md).

**The family interface (`tool_params`).** Each family declares the exact `run()` signature. This is what lets the held-out check call a tool with hidden inputs, and what forces the trading-session tool to receive its holiday list as a parameter rather than hard-coding it.

**One commit per verified step, on `develop`.** Every module ships with a `__main__` self-check, so each step is proven before the next begins.

## Build order

Foundation (`config`, `taskgen`, `tools`) → model layer (`llm`, adapters) → security (`protocol`, `sandbox`, `guard`, red-team, proven with no API cost) → agent (`registry`, `smith`, `prompts`, `agent`) → CLI and docs → the finance set.

## End-to-end verification

1. `uv run python -m src.redteam` — both security layers, no API calls.
2. Each module's `__main__` self-check.
3. Both task generators' `--check` byte comparison.
4. With a key in `.env`: `uv run python -m src.main run --all` and `--set finance`.

---

## Appendix A — the finance set (confirmed)

Every value below was computed from the rule in the task text and cross-checked against a library at generation time. Common rules: the rule and a worked example are in the text; there is one exact answer; the hidden edge case follows from the written rule; visible inputs carry no edge case; each hidden batch has at least two edge inputs of six; the year is 2025.

### Family `isin` — interface `prefix` (11 chars) → check digit; joiner `""`

Rule: an ISIN is a two-letter country code, a nine-character body and one check digit. Turn the first 11 characters into digits (A=10 … Z=35, digits unchanged), then Luhn from the right; the check digit is `(10 − sum mod 10) mod 10`. Worked example: `US037833100` → `5`. Hint: *some codes contain letters after the two-letter country prefix.* Body positions are counted 1–9 from the left.

| | Prefixes (issuer) | Letters in body | Answer |
|---|---|---|---|
| isin_1 | DE000716460 SAP · IT000312836 Enel · FR000012027 TotalEnergies · US594918104 Microsoft · IT000006207 Generali · GB000989529 AstraZeneca | none | `071522` |
| isin_2 | CH003886335 Nestlé · NL001027321 ASML · JP363340000 Toyota · IT000007261 Intesa · DE000723610 Siemens · US023135106 Amazon | none | `051817` |
| H1 | US88160R101 Tesla · GB000237400 Diageo · US02079K305 Alphabet · DE000519000 BMW · NL00150001Q Stellantis · IT000385640 Leonardo | R6, K6 even · Q9 odd | `469395` |
| H2 | US30303M102 Meta · IE00B4L5Y98 iShares World · FR000012101 LVMH · US67066G104 Nvidia · DE000840400 Allianz · IT000523936 UniCredit | M6, G6 even · B3, L5, Y7 odd | `734050` |
| H3 | GB00BH4HKS3 Vodafone · US92826C839 Visa · IT000313247 Eni · US46625H100 JPMorgan · FR000013110 BNP Paribas · CH001203204 Roche | C6, H6 even · Vodafone B3, K7 odd | `946548` |

### Family `sessions` — interface `start`, `n`, `closures` → one date; joiner `","`

Rule: a session is a weekday that is not a market holiday (half-days count as full sessions). The holiday list in the text is the only valid source. Return the nth session strictly after the start; the start is never counted. Worked example: `2025-03-07` (Fri), n=3 → `2025-03-12`. Hint: *some ranges contain a closure day.*

- **NYSE 2025 holidays (in the sessions_1 text):** 01-01, 01-09 (listed, untouched by any interval), 01-20, 02-17, 04-18, 05-26, 06-19, 07-04, 09-01, 11-27, 12-25.
- **Stockholm 2025 holidays (in the sessions_2 text):** 01-01, 01-06, 04-18, 04-21, 05-01, 05-29, 06-06, 06-20, 12-24, 12-25, 12-26, 12-31.
- **Half-days no interval crosses:** NYSE 07-03, 11-28, 12-24; Stockholm 04-17, 04-30, 05-28, 10-31 (confirmed from the library).

| | (start, n) pairs, 2025 | Holidays crossed | Answer |
|---|---|---|---|
| sessions_1 (NYSE) | (02-03,7) (05-02,10) (08-13,4) (10-10,12) (03-18,6) (09-15,8) | none | `2025-02-12,2025-05-16,2025-08-19,2025-10-28,2025-03-26,2025-09-25` |
| sessions_2 (Stockholm) | (02-10,8) (07-01,5) (08-29,3) (11-24,5) (01-13,5) (05-22,3) | none (all six differ under the NYSE list) | `2025-02-20,2025-07-08,2025-09-03,2025-12-01,2025-01-20,2025-05-27` |
| H1 (NYSE list) | (04-15,4) (06-02,3) (01-16,3) (08-25,5) (10-01,4) (12-10,6) | 04-18, 01-20, 09-01 | `2025-04-22,2025-06-05,2025-01-22,2025-09-02,2025-10-07,2025-12-18` |
| H2 (NYSE list) | (05-22,2) (06-17,3) (07-07,5) (02-13,2) (11-18,5) (09-26,4) | 05-26, 06-19, 02-17 | `2025-05-27,2025-06-23,2025-07-14,2025-02-18,2025-11-25,2025-10-02` |
| H3 (Stockholm list) | (06-04,2) (06-18,2) (02-03,5) (03-10,7) (09-08,4) (10-13,6) | 06-06, 06-20 | `2025-06-09,2025-06-23,2025-02-10,2025-03-19,2025-09-12,2025-10-21` |

H3 carries the Stockholm holiday list, so it appears in the `sessions` family's held-out set and catches a tool that ignores its `closures` argument during the very first (NYSE) task.

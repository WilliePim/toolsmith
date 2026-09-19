"""Prove both security layers, with no API calls.

Inputs:  the corpus in attacks.py
Outputs: a table, and a non-zero exit if any attack gets through or any benign
         tool is refused

A guard attack must be refused by check(). A sandbox attack must pass the guard
(or be sent past it) and then be stopped at runtime: denied by the audit hook,
killed by the watchdog, or returned as a failed call. A benign tool must clear
both layers and return the expected value.
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.table import Table

from src import guard, sandbox
from src.attacks import ATTACKS, BENIGN, Attack, Benign

console = Console()


def _stopped_by_sandbox(attack: Attack) -> tuple[bool, str]:
    """Run one attack in the sandbox; report whether it was contained, and how."""
    result = sandbox.run_calls(attack.source, [{p: "test" for p in attack.params}])
    if result.status == "timeout":
        return True, "watchdog: timeout"
    if result.status == "output":
        return True, "watchdog: output cap"
    if result.status == "crashed":
        return True, f"crashed: {result.detail[:40]}"
    first = result.results[0] if result.results else {"ok": False, "error": "no result"}
    if first.get("ok"):
        return False, f"RETURNED {first.get('value')!r}"
    error = first.get("error", "")
    if "sandbox denied" in error:
        return True, error.split(":", 1)[-1].strip()[:40]
    return True, f"failed call: {error[:40]}"


def _check_attack(attack: Attack) -> tuple[bool, str, str]:
    """(contained, layer that stopped it, detail)."""
    verdict = guard.check(attack.source, attack.params)
    if attack.layer == "guard":
        if verdict is not None:
            return True, "guard", verdict.split(":", 2)[-1].strip()[:44]
        # The guard let it through, but this attack was meant to be caught there.
        contained, detail = _stopped_by_sandbox(attack)
        return contained, "sandbox" if contained else "-", \
            f"guard MISSED; sandbox: {detail}" if contained else detail

    # A sandbox attack: skip the guard on purpose and prove the runtime holds.
    contained, detail = _stopped_by_sandbox(attack)
    return contained, "sandbox" if contained else "-", detail


def _check_benign(tool: Benign) -> tuple[bool, str]:
    """(passed, detail): must clear the guard and return every expected value."""
    verdict = guard.check(tool.source, tool.params)
    if verdict is not None:
        return False, f"guard refused: {verdict[:44]}"
    result = sandbox.run_calls(tool.source, list(tool.calls))
    if not result.ok:
        return False, f"sandbox: {result.status} {result.detail[:30]}"
    got = tuple(str(v) for v in result.values())
    if got != tool.expect:
        return False, f"got {got}, expected {tool.expect}"
    return True, ", ".join(got)


def main() -> int:
    failures = 0

    attack_table = Table(title="Attacks - each must be contained", show_lines=False)
    attack_table.add_column("attack")
    attack_table.add_column("target")
    attack_table.add_column("result")
    attack_table.add_column("stopped by / detail")
    for attack in ATTACKS:
        contained, layer, detail = _check_attack(attack)
        failed = not contained
        failures += failed
        verdict = "[green]contained[/]" if contained else "[red]GOT THROUGH[/]"
        attack_table.add_row(attack.name, attack.layer,
                             verdict, f"{layer}: {detail}" if contained else detail)
    console.print(attack_table)

    benign_table = Table(title="Benign tools - each must pass and return its value")
    benign_table.add_column("tool")
    benign_table.add_column("result")
    benign_table.add_column("detail")
    for tool in BENIGN:
        passed, detail = _check_benign(tool)
        failures += not passed
        verdict = "[green]passed[/]" if passed else "[red]REFUSED[/]"
        benign_table.add_row(tool.name, verdict, detail)
    console.print(benign_table)

    guard_n = sum(a.layer == "guard" for a in ATTACKS)
    sandbox_n = len(ATTACKS) - guard_n
    console.print(f"\n{len(ATTACKS)} attacks ({guard_n} guard, {sandbox_n} sandbox) + "
                  f"{len(BENIGN)} benign tools")
    if failures:
        console.print(f"[red]FAIL - {failures} case(s) went the wrong way[/]")
        return 1
    console.print("[green]OK - both layers held, every benign tool passed[/]")
    return 0


if __name__ == "__main__":
    sys.exit(main())

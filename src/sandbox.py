"""The runtime layer: run a generated tool in a locked-down subprocess.

Inputs:  the tool's source and a list of calls (each a dict of arguments)
Outputs: a SandboxResult - one entry per call, plus how the run ended

The static guard reads the source; this runs it. The two are independent, so a
tool that slips one string past the guard still meets the audit hook here.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from src import config, protocol

# Passed to the child, and nothing else. No API keys, no PYTHONPATH, no PYTHON*
# switch that could re-enable site or a startup file. SYSTEMROOT is what Windows
# needs to load sockets/SSL machinery at all; without it os.urandom can fail.
_SAFE_ENV_KEYS = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "NUMBER_OF_PROCESSORS")


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """The outcome of one run: a result per call, and why it stopped."""

    results: list[dict] = field(default_factory=list)
    stray_output: str = ""
    status: str = "ok"          # ok | timeout | output | crashed
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def values(self) -> list[Any]:
        """The value of each call, or None where it failed."""
        return [r.get("value") if r.get("ok") else None for r in self.results]


def _child_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _SAFE_ENV_KEYS if key in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"       # -I ignores it, -X utf8 covers that; belt and braces
    return env


def _apply_posix_limits() -> None:  # pragma: no cover - not exercised on Windows
    """A hard CPU-time and address-space cap, on the platforms that have one."""
    import resource

    cpu = int(config.SANDBOX_TIMEOUT_S) + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    gigabyte = 1024 ** 3
    resource.setrlimit(resource.RLIMIT_AS, (gigabyte, gigabyte))


def run_calls(source: str, calls: Sequence[dict]) -> SandboxResult:
    """Build the script, run it against `calls`, and watch the clock and the output."""
    nonce = secrets.token_hex(8)
    script = protocol.build_script(source, nonce)
    stdin = "\n".join(__import__("json").dumps(call) for call in calls)

    with tempfile.TemporaryDirectory(prefix="toolsmith_") as work:
        script_path = Path(work) / "_TS_tool.py"
        script_path.write_text(script, encoding="utf-8")
        out_path, err_path = Path(work) / "out.txt", Path(work) / "err.txt"

        # -I isolated (no env, no cwd on path), -S no site-packages (only the
        # stdlib is readable), -B no .pyc writes (the write-deny would break them),
        # -X utf8 because -I drops PYTHONIOENCODING.
        argv = [sys.executable, "-I", "-S", "-B", "-X", "utf8", str(script_path)]
        preexec = None if os.name == "nt" else _apply_posix_limits

        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=out, stderr=err,
                cwd=work, env=_child_env(),
                preexec_fn=preexec,  # type: ignore[arg-type]
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                proc.stdin.write(stdin.encode("utf-8"))
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

            status, detail = _watch(proc, out_path)

        stdout = out_path.read_text(encoding="utf-8", errors="replace")
        stderr = err_path.read_text(encoding="utf-8", errors="replace").strip()

    results, stray = protocol.parse_lines(stdout, len(calls), nonce)
    if status == "ok" and proc.returncode not in (0, None):
        status = "crashed"
        detail = stderr.splitlines()[-1] if stderr else f"exit code {proc.returncode}"
    return SandboxResult(results=results, stray_output=stray, status=status, detail=detail)


def _watch(proc: subprocess.Popen, out_path: Path) -> tuple[str, str]:
    """Poll until the child exits, then kill it if it ran too long or said too much."""
    deadline = time.monotonic() + config.SANDBOX_TIMEOUT_S
    while proc.poll() is None:
        if time.monotonic() > deadline:
            _kill(proc)
            return "timeout", f"killed after {config.SANDBOX_TIMEOUT_S:.0f}s"
        try:
            if out_path.stat().st_size > config.SANDBOX_MAX_OUTPUT:
                _kill(proc)
                return "output", f"killed after more than {config.SANDBOX_MAX_OUTPUT:,} bytes"
        except OSError:
            pass
        time.sleep(config.SANDBOX_POLL_S)
    return "ok", ""


def _kill(proc: subprocess.Popen) -> None:
    proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        pass


if __name__ == "__main__":
    ok = run_calls("def run(x):\n    return x.upper()\n", [{"x": "ab"}, {"x": "cd"}])
    assert ok.ok and ok.values() == ["AB", "CD"], ok

    stray = run_calls("def run(n):\n    print('debug', n)\n    return n * 2\n", [{"n": 3}])
    assert stray.values() == [6] and "debug 3" in stray.stray_output, stray

    started = time.perf_counter()
    slow = run_calls("def run():\n    while True:\n        pass\n", [{}])
    assert slow.status == "timeout" and time.perf_counter() - started < config.SANDBOX_TIMEOUT_S + 5
    assert slow.results[0]["ok"] is False

    flood = run_calls("def run():\n    while True:\n        print('x' * 1000)\n", [{}])
    assert flood.status in ("output", "timeout"), flood.status

    crash = run_calls("def run():\n    raise ValueError('boom')\n", [{}])
    assert crash.ok and crash.results[0]["ok"] is False and "boom" in crash.results[0]["error"]

    # The guard is skipped here on purpose: the audit hook must hold on its own.
    from pathlib import Path as _P
    env_file = str((config.ROOT_DIR / ".env").resolve()).replace("\\", "\\\\")
    denied = {
        "os.system": "import os\ndef run():\n    return os.system('echo pwned')",
        "read .env": f"def run():\n    return open('{env_file}').read()",
        "write file": "def run():\n    open('x.txt', 'w').write('hi')\n    return 'wrote'",
        "socket": "import socket\ndef run():\n    return str(socket.socket())",
    }
    for name, src in denied.items():
        res = run_calls(src, [{}])
        first = res.results[0]
        assert first["ok"] is False and "sandbox denied" in first.get("error", ""), \
            f"{name} was NOT denied: {first}"

    print(f"benign -> {ok.values()}   timeout -> {slow.status}   flood -> {flood.status}")
    print(f"denied at runtime: {', '.join(denied)}")
    print("OK - sandbox")

"""Turn a generated function into a runnable, locked-down script, and read it back.

Inputs:  the model's source text (defining run(...)), and a per-run nonce
Outputs: build_script() for the sandbox, parse_lines() for its stdout

A script is three parts in one file: a preamble that locks the interpreter
down, the model's source byte for byte, and a footer that reads calls from
stdin (one JSON object per line) and prints one result line per call.
"""

from __future__ import annotations

import json

from src import config

# Plain printable ASCII, on purpose: str.splitlines() also splits on \x0b, \x0c,
# \x1c-\x1e, \x85, U+2028 and U+2029, so a marker built from control characters
# would be torn in half by the parent reading it.
SENTINEL = "@@TOOLSMITH@@"

# Every name this file introduces starts with _TS_, and the guard refuses
# generated source that binds one. Otherwise a helper innocently named `json`
# could shadow the footer's own serialiser.
RESERVED_PREFIX = "_TS_"

# Loaded before the hook goes in. Two reasons: a cached import fires no audit
# event at all, and the first import of a *package* (json, re, collections) lists
# its directory - an os.listdir the hook would rightly refuse. heapq and _strptime
# are imported lazily by Counter.most_common() and datetime.strptime().
PRELOAD = tuple(sorted(set(config.ALLOWED_IMPORTS) | {"json", "traceback", "heapq",
                                                      "_strptime", "builtins"}))

# What the child may never do. What is NOT here matters as much:
#   import         - a cached import fires no event, and a lazy stdlib import is
#                    ordinary (Counter.most_common imports heapq on first use);
#   exec, compile  - they fire whenever a standard library module loads.
# Those belong to the static guard. This layer blocks what an import is FOR.
_DENY = frozenset({
    "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.fork", "os.forkpty",
    "os.startfile", "subprocess.Popen", "_winapi.CreateProcess", "os.kill", "os.killpg",
    "socket.__new__", "socket.connect", "socket.bind", "socket.getaddrinfo",
    "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo", "socket.sendto",
    "urllib.Request", "http.client.connect", "webbrowser.open",
    "ctypes.dlopen", "ctypes.dlsym", "ctypes.call_function", "ctypes.cdata",
    "ctypes.string_at", "ctypes.wstring_at", "ctypes.addressof",
    "os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.link", "os.symlink",
    "os.chmod", "os.chown", "os.truncate", "os.utime", "os.listdir", "os.scandir",
    "glob.glob", "shutil.copyfile", "shutil.rmtree", "shutil.move",
    "os.putenv", "os.unsetenv", "winreg.OpenKey", "winreg.CreateKey", "pickle.find_class",
    "builtins.input", "builtins.breakpoint", "sys.settrace", "sys.setprofile",
    "sys._getframe", "sys._current_frames", "sys.addaudithook",
    "code.__new__", "function.__new__", "mmap.__new__", "sqlite3.connect",
    "cpython.run_file", "cpython.run_module", "cpython.run_command",
})

PREAMBLE = f'''\
# --- toolsmith preamble: the generated tool starts after this block ---
import sys as _TS_sys


class _TS_Violation(BaseException):
    """Raised by the audit hook. Deliberately not an Exception.

    A tool wrapping its payload in `try: ... except Exception: pass` would
    otherwise swallow the block and return a clean-looking result. Only a bare
    `except:` or `except BaseException` can catch this, and the guard refuses both.
    """


def _TS_install():
    """Install the audit hook, closed over its policy (locals, not globals)."""
    import os
    for name in {PRELOAD!r}:
        __import__(name)
    norm = lambda p: os.path.normcase(os.path.abspath(p))
    exact = frozenset(norm(p) for p in _TS_sys.path if p) | {{norm(__file__)}}
    prefixes = tuple(p.rstrip(os.sep) + os.sep for p in exact)
    deny = {sorted(_DENY)!r}
    deny = frozenset(deny)
    writes = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

    def hook(event, args):
        if event in deny:
            raise _TS_Violation("sandbox denied: " + event)
        if event == "open":
            path, mode, flags = (tuple(args) + (None, None, None))[:3]
            if not isinstance(path, str):
                raise _TS_Violation("sandbox denied: open by file descriptor")
            if (isinstance(mode, str) and any(c in mode for c in "wxa+")) or \\
                    (mode is None and isinstance(flags, int) and flags & writes):
                raise _TS_Violation("sandbox denied: writing " + path)
            full = norm(path)
            if full not in exact and not full.startswith(prefixes):
                raise _TS_Violation("sandbox denied: reading " + path)

    _TS_sys.addaudithook(hook)


_TS_install()
del _TS_install
# --- generated tool ---
'''


def _footer(nonce: str) -> str:
    """The calling convention: one JSON call per stdin line, one marked result per line.

    The imports come after the tool's source, so a shadowed name cannot break
    them, and every builtin is taken from `builtins` for the same reason. The
    nonce makes a result line impossible to forge by printing one.
    """
    return f'''
# --- toolsmith footer ---
import builtins as _TS_b
import json as _TS_json
import traceback as _TS_tb

for _TS_line in _TS_sys.stdin.read().split("\\n"):
    if not _TS_line.strip():
        continue
    try:
        _TS_result = {{"ok": True, "value": run(**_TS_json.loads(_TS_line))}}
        _TS_json.dumps(_TS_result)          # prove it serialises before printing
    except _TS_b.BaseException as _TS_exc:  # sys.exit() in run() is one failed call
        _TS_result = {{"ok": False,
                      "error": _TS_b.type(_TS_exc).__name__ + ": " + _TS_b.str(_TS_exc),
                      "trace": _TS_tb.format_exc()[-800:]}}
    _TS_b.print("{SENTINEL}{nonce}" + _TS_json.dumps(_TS_result, default=_TS_b.str,
                                                    ensure_ascii=False), flush=True)
'''


def build_script(source: str, nonce: str) -> str:
    """Lockdown, the model's source verbatim, then the footer.

    A useful side effect: the model's source now sits some forty lines down a
    larger file, so an encoding cookie in its first two lines does nothing.
    """
    return PREAMBLE + source.rstrip() + "\n" + _footer(nonce)


def parse_lines(stdout: str, expected: int, nonce: str) -> tuple[list[dict], str]:
    """(results, whatever the tool printed itself).

    Any line without the marker is the tool's own output: kept, never parsed.
    Models put print() debugging into generated code constantly, and a bare
    json.loads(stdout) would fail a tool that is perfectly correct.
    """
    marker = SENTINEL + nonce
    results: list[dict] = []
    stray: list[str] = []
    for line in stdout.split("\n"):
        line = line.rstrip("\r")
        if line.startswith(marker):
            try:
                results.append(json.loads(line[len(marker):]))
            except json.JSONDecodeError as exc:
                results.append({"ok": False, "error": f"unreadable result line ({exc})"})
        elif line.strip():
            stray.append(line)
    while len(results) < expected:
        results.append({"ok": False, "error": "no result: the process crashed, timed "
                                              "out or printed too much"})
    return results[:expected], "\n".join(stray)


if __name__ == "__main__":
    nonce = "0123abcd"
    assert all(32 <= ord(ch) < 127 for ch in SENTINEL), "the marker must be printable ASCII"
    script = build_script("def run(x):\n    return x\n", nonce)
    compile(script, "<tool>", "exec")                   # the whole script is valid Python
    assert script.index("def run") > script.index("addaudithook"), "hook before tool"
    assert script.index("def run") < script.index("import json as _TS_json"), "imports after"

    out = "\n".join([
        "debug: thinking",                                          # stray print
        f"{SENTINEL}{nonce}" + json.dumps({"ok": True, "value": "K"}),
        f"{SENTINEL}" + json.dumps({"ok": True, "value": "FORGED"}),  # no nonce: stray
        # U+2028 survives json.dumps(ensure_ascii=False) unescaped, and
        # str.splitlines() would split the line on it. split("\n") does not.
        f"{SENTINEL}{nonce}" + json.dumps({"ok": True, "value": "a b"}, ensure_ascii=False),
        f"{SENTINEL}{nonce}" + "{not json",
    ])
    assert len(out.splitlines()) == 6 and len(out.split("\n")) == 5, "the trap is real"
    results, stray = parse_lines(out, expected=4, nonce=nonce)
    assert [r.get("value") for r in results[:2]] == ["K", "a b"]
    assert results[2]["error"].startswith("unreadable result line")
    assert results[3]["error"].startswith("no result"), "missing results are padded"
    assert "FORGED" in stray and "debug: thinking" in stray, "stray lines are kept, not parsed"

    print(f"sentinel {SENTINEL} + per-run nonce | preamble {len(PREAMBLE):,} chars | "
          f"{len(_DENY)} denied events | {len(PRELOAD)} modules preloaded")
    print("OK - protocol")

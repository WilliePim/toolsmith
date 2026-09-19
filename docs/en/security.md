# Security

*[Italiano](../it/security.md) · English*

A generated tool is code the model wrote. Two independent layers stand between that code and your machine. Neither trusts the other, and `redteam.py` proves each one on its own — with no API calls.

## Layer 1 — the static guard (`guard.py`)

The guard reads the source as an abstract syntax tree and refuses it *before anything runs*, returning the first violation as `line N: reason`. It sees **names**, not values, so it is coarse and **default-deny**: a construct nobody anticipated is refused, because a rejection costs one repair turn while a miss costs a wrong answer or worse.

It refuses:

- **Structure** — anything but one top-level `run(<declared params>)`; `*args`/`**kwargs`; top-level statements other than imports, defs, classes, assignments and docstrings; any `async`.
- **Imports** — any module outside the allowlist (`math`, `datetime`, `re`, `decimal`, `json`, `itertools`, `functools`, `collections`, `string`, `calendar`, `typing`); relative and star imports.
- **Dangerous builtins** — `eval`, `exec`, `compile`, `open`, `__import__`, the `getattr`/`setattr` family, `globals`/`locals`/`vars`/`dir`, `input`, `breakpoint`, `memoryview`, and the base exceptions `BaseException`/`SystemExit`/`KeyboardInterrupt`/`GeneratorExit`.
- **Dunder traversal** — any `__dunder__` outside a small allowlist, blocking `__class__`, `__subclasses__`, `__globals__`, `__dict__`, `__mro__`, `__bases__`, `__builtins__`, `__reduce__`.
- **Pivots and privates** — attributes that reach the interpreter or a frame (`sys`, `modules`, `f_globals`, `gi_frame`, `tb_frame`, ...), even via an alias like `typing.sys`; private attributes (`_x`) unless on `self`/`cls`, which blocks `collections._sys`.
- **Format-string traversal** — `"{0.__class__}".format(x)` reaches an attribute with no `getattr` in sight; a literal template whose fields walk a `.` or `[` is refused, and a non-literal `.format` receiver outright.
- **Swallowing the sandbox signal** — a bare `except:`, an `except` whose type is an expression, and `return`/`break`/`continue` inside `finally`.
- **The reserved prefix** — any name starting with `_TS_`.

## Layer 2 — the runtime sandbox (`sandbox.py` + `protocol.py`)

The sandbox runs the tool in a separate process it cannot influence:

- **`python -I -S -B -X utf8`** — isolated (no environment, working dir off the path), no site-packages (only the standard library is readable), no `.pyc` writes, UTF-8 I/O.
- **A scrubbed environment** — only `SYSTEMROOT` and a couple of harmless variables reach the child. **No API keys.**
- **A fresh temp directory** as the working directory, deleted after the run.
- **A watchdog** that polls every 20 ms and kills the child after 10 seconds or 256 KB of output.
- **On POSIX**, hard `RLIMIT_CPU` and `RLIMIT_AS` (1 GB) limits as well.

Inside the child, a **Python audit hook** installed before the tool's code denies a fixed set of events: `os.system`, process spawning, sockets, `ctypes`, registry access, and every filesystem write. File *reads* are allowed only inside the standard library and the script itself, with paths normalised first so that `..` traversal and Windows case tricks cannot widen it.

Two design decisions hold each other up. The hook raises `_TS_Violation`, which derives from **`BaseException`** — so `except Exception: pass` cannot swallow it — and the guard bans the bare `except:` that is the only other way to catch it. Either alone is not enough.

## The proof (`redteam.py`)

```bash
uv run python -m src.redteam
```

36 attacks and 7 benign near-misses, run with no API calls:

- **27 guard attacks** — forbidden and aliased imports, `__import__`, `eval`/`exec`/`open`/`getattr`, dunder and mro traversal, module pivots via aliases and privates, frame walking, format-string traversal, the exception swallowers, the reserved prefix, a star import, an annotation `eval`.
- **9 sandbox attacks** — an infinite loop, a print flood, deep recursion, `sys.exit()` inside `run`, a non-serialisable return, and `os.system`/file-write/socket/`os.listdir` **sent straight to the sandbox with the guard skipped**, to prove the audit hook holds alone.
- **7 benign tools** that must pass and return the right value — a helper named `json`, `Counter.most_common()` (its lazy `heapq` import), a `decimal` context, a class with `__init__`, `try/except ValueError`, `date.fromisoformat().isocalendar()`, and a `re` + `string` matcher.

The suite exits non-zero if any attack gets through or any benign tool is refused.

## Known limits

This is a strong barrier for a demo, not a claim of perfect isolation.

- **Windows memory.** There is no address-space cap on Windows; a tool can allocate until the timeout kills it. A Job Object memory limit is the fix, listed under "what to build next".
- **Reads under the Python install.** With `-S`, the child's path includes the interpreter's own directory, so files there are readable. Nothing sensitive lives there, but it is a wider read surface than the pure standard library.
- **Audit hooks are a Python-level barrier.** They stop the events they are hooked on; a native extension that bypassed the interpreter would not fire one — which is exactly why `ctypes` and friends are on the deny list and outside the import allowlist.

Do not point this at untrusted input on a machine you cannot afford to lose.

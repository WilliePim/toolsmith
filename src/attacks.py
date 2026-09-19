"""The corpus that proves both layers: hostile tools and benign near-misses.

Inputs:  nothing
Outputs: ATTACKS (each labelled with the layer that must stop it) and BENIGN

Every attack targets one defence. GUARD attacks must be refused by reading the
source; SANDBOX attacks are the escape attempts a guard cannot see (a loop, a
flood) plus - crucially - OS, file and network calls sent straight to the
sandbox with the guard skipped, to prove the audit hook holds on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class Attack:
    name: str
    layer: str          # "guard" or "sandbox"
    source: str
    params: tuple[str, ...] = ("x",)
    category: str = "other"
    args: tuple[tuple[str, str], ...] = ()   # call arguments, when a placeholder won't do
    # Platforms where this attack is KNOWN to get through, with the reason. It is
    # then reported as a documented limit instead of a surprise - but an escape
    # that is not declared here still fails the suite.
    known_escape_on: tuple[str, ...] = ()
    known_escape_reason: str = ""

    def call_args(self) -> dict[str, str]:
        return dict(self.args) if self.args else {p: "test" for p in self.params}


def _outside_path() -> str:
    """A real path outside the sandbox, for the reads and writes that must be refused."""
    from src import config
    return str((config.ROOT_DIR / ".env").resolve())


# The categories a report groups by. Each one must be represented in ATTACKS.
CATEGORIES = ("read outside the allowed directory", "write to disk", "network access",
              "process spawn", "infinite loop", "excessive memory",
              "forbidden module import", "interpreter escape", "swallow the violation")


@dataclass(frozen=True, slots=True)
class Benign:
    """A tool that looks alarming but is fine, and the calls that prove it works."""

    name: str
    source: str
    params: tuple[str, ...]
    calls: tuple[dict, ...]
    expect: tuple[str, ...]


# --- Attacks the static guard must refuse (read-only, nothing runs) ----------------

_GUARD = [
    Attack("import os", "guard", "import os\ndef run(x):\n    return os.getcwd()"),
    Attack("import subprocess", "guard",
           "import subprocess\ndef run(x):\n    return str(subprocess.run(['echo']))"),
    Attack("import socket", "guard", "import socket\ndef run(x):\n    return str(socket.socket())"),
    Attack("from os import system", "guard",
           "from os import system\ndef run(x):\n    return str(system('echo hi'))"),
    Attack("aliased import", "guard", "import os as o\ndef run(x):\n    return o.getcwd()"),
    Attack("importlib", "guard",
           "import importlib\ndef run(x):\n    return importlib.import_module('os').getcwd()"),
    Attack("__import__", "guard", "def run(x):\n    return __import__('os').getcwd()"),
    Attack("eval", "guard", "def run(x):\n    return eval('__import__(\"os\").getcwd()')"),
    Attack("exec", "guard", "def run(x):\n    exec('import os')\n    return x"),
    Attack("compile", "guard", "def run(x):\n    return str(compile(x, '<s>', 'eval'))"),
    Attack("open", "guard", "def run(x):\n    return open('/etc/passwd').read()"),
    Attack("getattr pivot", "guard",
           "def run(x):\n    return getattr(x, '__class__')"),
    Attack("dunder class walk", "guard",
           "def run(x):\n    return str(x.__class__.__bases__)"),
    Attack("mro subclasses", "guard",
           "def run(x):\n    return str(type(x).__mro__[-1].__subclasses__())"),
    Attack("globals", "guard", "def run(x):\n    return str(globals())"),
    Attack("builtins via dunder", "guard",
           "def run(x):\n    return str(x.__class__.__dict__)"),
    Attack("typing.sys pivot", "guard",
           "import typing\ndef run(x):\n    return str(typing.sys.modules['os'])"),
    Attack("collections private", "guard",
           "import collections\ndef run(x):\n    return str(collections._sys)"),
    Attack("frame walk", "guard",
           "def run(x):\n    err = ValueError()\n    return str(err.__traceback__)"),
    Attack("format traversal", "guard",
           "def run(x):\n    return '{0.__class__.__mro__}'.format(x)"),
    Attack("format map", "guard",
           "def run(x):\n    return type(x).__name__.format_map({})"),
    Attack("bare except swallow", "guard",
           "import os\ndef run(x):\n    try:\n        return os.getcwd()\n    except:\n        return x"),
    Attack("except BaseException", "guard",
           "def run(x):\n    try:\n        return x\n    except BaseException:\n        return x"),
    Attack("return in finally", "guard",
           "def run(x):\n    try:\n        return x\n    finally:\n        return 'swallowed'"),
    Attack("reserved prefix", "guard",
           "def run(x):\n    _TS_sys = 1\n    return str(_TS_sys)"),
    Attack("star import", "guard", "from math import *\ndef run(x):\n    return str(pi)"),
    Attack("annotation eval", "guard",
           "def run(x):\n    y: eval('os') = 1\n    return x"),
]

# --- Attacks only the sandbox can stop --------------------------------------------
# The first group is behaviour a guard cannot judge from names. The rest are the
# guard's own targets, sent straight to the sandbox to prove it stands alone.

_SANDBOX = [
    Attack("infinite loop", "sandbox", "def run(x):\n    while True:\n        pass",
           category="infinite loop"),
    Attack("print flood", "sandbox",
           "def run(x):\n    while True:\n        print('x' * 4096)",
           category="infinite loop"),
    Attack("deep recursion", "sandbox", "def run(x):\n    return run(x)",
           category="excessive memory"),
    # Roughly 4 GB in one go. On POSIX the sandbox's RLIMIT_AS should refuse it
    # outright; on Windows there is no such cap, so only the watchdog can end it.
    Attack("memory bomb (4 GB)", "sandbox",
           "def run(x):\n    blob = bytearray(4 * 10**9)\n    return str(len(blob))",
           category="excessive memory", known_escape_on=("Windows",),
           known_escape_reason="Windows has no RLIMIT_AS equivalent here, and a single "
                               "large allocation finishes well inside the watchdog's "
                               "timeout. Measured: it returns 4,000,000,000."),
    Attack("memory bomb (growing list)", "sandbox",
           "def run(x):\n    acc = []\n    while True:\n        acc.append('y' * 10**6)",
           category="excessive memory"),
    Attack("sys.exit in run", "sandbox",
           "import sys\ndef run(x):\n    sys.exit(0)", category="interpreter escape"),
    Attack("non-serialisable return", "sandbox", "def run(x):\n    return {1, 2, 3}",
           category="other"),
    Attack("os.system (guard skipped)", "sandbox",
           "import os\ndef run(x):\n    return os.system('echo pwned')",
           category="process spawn"),
    Attack("subprocess spawn (guard skipped)", "sandbox",
           "import subprocess\ndef run(x):\n"
           "    return str(subprocess.run(['echo', 'pwned'], capture_output=True))",
           category="process spawn"),
    Attack("write a file (guard skipped)", "sandbox",
           "def run(x):\n    open('pwned.txt', 'w').write('x')\n    return 'wrote'",
           category="write to disk"),
    Attack("append to a file elsewhere (guard skipped)", "sandbox",
           "def run(x):\n    open(x, 'a').write('pwned')\n    return 'appended'",
           category="write to disk", args=(("x", _outside_path()),)),
    Attack("socket (guard skipped)", "sandbox",
           "import socket\ndef run(x):\n    s = socket.socket()\n    return 'made socket'",
           category="network access"),
    Attack("dns lookup (guard skipped)", "sandbox",
           "import socket\ndef run(x):\n    return socket.gethostbyname('example.com')",
           category="network access"),
    Attack("os.listdir (guard skipped)", "sandbox",
           "import os\ndef run(x):\n    return str(os.listdir('.'))",
           category="read outside the allowed directory"),
    Attack("read a file outside the sandbox (guard skipped)", "sandbox",
           "def run(x):\n    return open(x).read()[:40]",
           category="read outside the allowed directory", args=(("x", _outside_path()),)),
]

# The guard attacks are categorised here rather than inline, so the list above stays
# readable and every name is forced to appear exactly once.
_GUARD_CATEGORIES = {
    "import os": "forbidden module import",
    "import subprocess": "forbidden module import",
    "import socket": "forbidden module import",
    "from os import system": "forbidden module import",
    "aliased import": "forbidden module import",
    "importlib": "forbidden module import",
    "__import__": "forbidden module import",
    "star import": "forbidden module import",
    "eval": "interpreter escape",
    "exec": "interpreter escape",
    "compile": "interpreter escape",
    "annotation eval": "interpreter escape",
    "open": "read outside the allowed directory",
    "getattr pivot": "interpreter escape",
    "dunder class walk": "interpreter escape",
    "mro subclasses": "interpreter escape",
    "globals": "interpreter escape",
    "builtins via dunder": "interpreter escape",
    "typing.sys pivot": "interpreter escape",
    "collections private": "interpreter escape",
    "frame walk": "interpreter escape",
    "format traversal": "interpreter escape",
    "format map": "interpreter escape",
    "reserved prefix": "interpreter escape",
    "bare except swallow": "swallow the violation",
    "except BaseException": "swallow the violation",
    "return in finally": "swallow the violation",
}

_GUARD = [replace(a, category=_GUARD_CATEGORIES[a.name]) for a in _GUARD]
assert set(_GUARD_CATEGORIES) == {a.name for a in _GUARD}, "every guard attack needs a category"

ATTACKS: tuple[Attack, ...] = tuple(_GUARD + _SANDBOX)


# --- Benign tools that must pass both layers and return the right value -------------

BENIGN: tuple[Benign, ...] = (
    Benign("helper named json",
           "def json(n):\n    return str(n * 2)\n"
           "def run(x):\n    return json(len(x))",
           ("x",), ({"x": "abc"},), ("6",)),
    Benign("Counter.most_common (lazy heapq)",
           "import collections\n"
           "def run(x):\n    return collections.Counter(x).most_common(1)[0][0]",
           ("x",), ({"x": "aabbb"},), ("b",)),
    Benign("decimal context",
           "import decimal\n"
           "def run(x):\n    with decimal.localcontext() as c:\n"
           "        c.prec = 4\n        return str(decimal.Decimal(1) / decimal.Decimal(x))",
           ("x",), ({"x": "3"},), ("0.3333",)),
    Benign("class with __init__",
           "class Box:\n    def __init__(self, v):\n        self.v = v\n"
           "    def doubled(self):\n        return self.v * 2\n"
           "def run(x):\n    return str(Box(int(x)).doubled())",
           ("x",), ({"x": "21"},), ("42",)),
    Benign("try/except ValueError",
           "def run(x):\n    try:\n        return str(int(x) + 1)\n"
           "    except ValueError:\n        return 'not a number'",
           ("x",), ({"x": "41"}, {"x": "nan"}), ("42", "not a number")),
    Benign("date isocalendar (param shadows import)",
           "import datetime\n"
           "def run(date):\n    d = datetime.date.fromisoformat(date)\n"
           "    return str(d.isocalendar().week)",
           ("date",), ({"date": "2025-03-17"},), ("12",)),
    Benign("re and string",
           "import re\nimport string\n"
           "def run(x):\n    return str(bool(re.fullmatch('[' + string.digits + ']+', x)))",
           ("x",), ({"x": "1234"},), ("True",)),
)

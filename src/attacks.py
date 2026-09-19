"""The corpus that proves both layers: hostile tools and benign near-misses.

Inputs:  nothing
Outputs: ATTACKS (each labelled with the layer that must stop it) and BENIGN

Every attack targets one defence. GUARD attacks must be refused by reading the
source; SANDBOX attacks are the escape attempts a guard cannot see (a loop, a
flood) plus - crucially - OS, file and network calls sent straight to the
sandbox with the guard skipped, to prove the audit hook holds on its own.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Attack:
    name: str
    layer: str          # "guard" or "sandbox"
    source: str
    params: tuple[str, ...] = ("x",)


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
    Attack("infinite loop", "sandbox", "def run(x):\n    while True:\n        pass"),
    Attack("print flood", "sandbox",
           "def run(x):\n    while True:\n        print('x' * 4096)"),
    Attack("deep recursion", "sandbox", "def run(x):\n    return run(x)"),
    Attack("sys.exit in run", "sandbox",
           "import sys\ndef run(x):\n    sys.exit(0)"),
    Attack("non-serialisable return", "sandbox", "def run(x):\n    return {1, 2, 3}"),
    Attack("os.system (guard skipped)", "sandbox",
           "import os\ndef run(x):\n    return os.system('echo pwned')"),
    Attack("write a file (guard skipped)", "sandbox",
           "def run(x):\n    open('pwned.txt', 'w').write('x')\n    return 'wrote'"),
    Attack("socket (guard skipped)", "sandbox",
           "import socket\ndef run(x):\n    s = socket.socket()\n    return 'made socket'"),
    Attack("os.listdir (guard skipped)", "sandbox",
           "import os\ndef run(x):\n    return str(os.listdir('.'))"),
]

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

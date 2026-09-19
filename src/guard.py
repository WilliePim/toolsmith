"""The static layer: read a tool's source and refuse unsafe code, with a reason.

Inputs:  the source text and the parameter names the tool must take
Outputs: check() -> None if allowed, else "line N: reason"

The guard sees names, not values and not time. It cannot know that a loop never
ends or how many bytes it will print - that is the sandbox's job. It is coarse
on purpose and default-deny: a construct nobody has thought about is refused,
because a rejection here costs one repair turn, while a miss costs a wrong
answer or worse.
"""

from __future__ import annotations

import ast

from src import config
from src.protocol import RESERVED_PREFIX

# Builtins a tool must never name. eval/exec/compile run strings; open touches the
# filesystem; the getattr family reaches attributes chosen at runtime, past every
# name check below; the introspection builtins walk the interpreter; and the base
# exceptions let a handler swallow the sandbox's own _TS_Violation.
_FORBIDDEN_NAMES = frozenset({
    "eval", "exec", "compile", "open", "__import__", "input", "breakpoint",
    "getattr", "setattr", "delattr", "hasattr", "vars", "globals", "locals", "dir",
    "memoryview", "exit", "quit", "help", "copyright", "credits", "license",
    "BaseException", "SystemExit", "KeyboardInterrupt", "GeneratorExit",
})

# Dunder members a tool may name; everything else __dunder__ is refused, which
# blocks __class__, __subclasses__, __globals__, __dict__, __bases__, __mro__,
# __builtins__, __reduce__, __getattribute__, and the rest of the pivot set.
_ALLOWED_DUNDERS = frozenset({
    "__init__", "__repr__", "__str__", "__eq__", "__lt__", "__le__", "__gt__",
    "__ge__", "__hash__", "__len__", "__iter__", "__next__", "__contains__",
    "__getitem__", "__setitem__", "__call__", "__enter__", "__exit__", "__name__",
    "__doc__", "__post_init__", "__slots__",
})

# Attribute names that reach the interpreter, the frame stack or an exception's
# traceback, regardless of the object they hang off. Named because an alias
# defeats an import check: `import typing; typing.sys.modules` never writes "sys"
# as an import, and `collections._sys` reaches the same module through a private.
_FORBIDDEN_ATTRS = frozenset({
    "mro", "modules", "builtins", "system", "popen",
    "f_globals", "f_locals", "f_back", "f_builtins", "f_code", "gi_frame",
    "cr_frame", "tb_frame", "tb_next", "gi_code", "cr_code",
    "get_type_hints", "format_map", "translate_map",
    "co_consts", "func_globals", "__globals__",
})

# Modules whose name, used as an attribute, hands back the module object itself.
_PIVOT_ATTRS = frozenset({"sys", "os", "subprocess", "socket", "importlib",
                          "ctypes", "codecs", "pickle", "shutil", "inspect",
                          "gc", "marshal", "platform", "sysconfig"})


class _Auditor(ast.NodeVisitor):
    def __init__(self, params: frozenset[str]):
        self.params = params
        self.problem: str | None = None
        self.run_seen = False

    def fail(self, node: ast.AST, reason: str) -> None:
        if self.problem is None:
            line = getattr(node, "lineno", 0)
            self.problem = f"line {line}: {reason}"

    def visit(self, node: ast.AST) -> None:
        if self.problem is not None:      # stop at the first violation
            return
        super().visit(node)

    # --- names and attributes ---------------------------------------------------

    def _check_identifier(self, node: ast.AST, name: str) -> None:
        if name in _FORBIDDEN_NAMES:
            self.fail(node, f"{name!r} is not allowed")
        elif name.startswith(RESERVED_PREFIX):
            self.fail(node, f"names starting with {RESERVED_PREFIX!r} are reserved")
        elif name.startswith("__") and name.endswith("__") and name not in _ALLOWED_DUNDERS:
            self.fail(node, f"the dunder {name!r} is not allowed")

    def visit_Name(self, node: ast.Name) -> None:
        self._check_identifier(node, node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attr = node.attr
        if attr in _FORBIDDEN_ATTRS or attr in _PIVOT_ATTRS:
            self.fail(node, f"the attribute {attr!r} is not allowed")
        elif attr.startswith("__") and attr.endswith("__") and attr not in _ALLOWED_DUNDERS:
            self.fail(node, f"the attribute {attr!r} is not allowed")
        elif attr.startswith("_") and not self._is_self(node.value):
            self.fail(node, f"the private attribute {attr!r} is not allowed")
        self.generic_visit(node)

    @staticmethod
    def _is_self(value: ast.AST) -> bool:
        """A private attribute is fine on self/cls, so a class can use its own."""
        return isinstance(value, ast.Name) and value.id in ("self", "cls")

    # --- imports ----------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top not in config.ALLOWED_IMPORTS:
                self.fail(node, f"import of {alias.name!r} is not allowed; allowed "
                                f"modules are {', '.join(sorted(config.ALLOWED_IMPORTS))}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            self.fail(node, "relative imports are not allowed")
        elif (node.module or "").split(".")[0] not in config.ALLOWED_IMPORTS:
            self.fail(node, f"import from {node.module!r} is not allowed")
        elif any(alias.name == "*" for alias in node.names):
            self.fail(node, "star imports are not allowed")
        self.generic_visit(node)

    # --- constructs that could swallow a violation ------------------------------

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.fail(node, "a bare 'except:' can catch the sandbox's violation; "
                            "name the exceptions you expect")
        elif not self._is_plain_exception(node.type):
            self.fail(node, "catch specific exception types by name, not an expression")
        self.generic_visit(node)

    @staticmethod
    def _is_plain_exception(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return True
        if isinstance(node, ast.Attribute):
            return True
        if isinstance(node, ast.Tuple):
            return all(isinstance(elt, (ast.Name, ast.Attribute)) for elt in node.elts)
        return False

    def visit_Try(self, node: ast.Try) -> None:
        for stmt in node.finalbody:
            for inner in ast.walk(stmt):
                if isinstance(inner, (ast.Return, ast.Break, ast.Continue)):
                    self.fail(inner, "return/break/continue in a finally block can "
                                     "swallow an exception; move it out of finally")
        self.generic_visit(node)

    # --- format-string attribute traversal --------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "format":
            # "{0.__class__}".format(x) reaches an attribute with no getattr in
            # sight. A literal receiver is fine only if no field walks a "." or "[".
            if isinstance(func.value, ast.Constant) and isinstance(func.value.value, str):
                if self._format_walks_attributes(func.value.value):
                    self.fail(node, "this format string reaches into an attribute; "
                                    "use an f-string or plain field references")
            else:
                self.fail(node, "str.format on a non-literal string can reach "
                                "attributes; use an f-string or % formatting")
        self.generic_visit(node)

    @staticmethod
    def _format_walks_attributes(template: str) -> bool:
        """True if any replacement field reads an attribute or item, like {0.__class__}."""
        import string as _string

        try:
            fields = [name for _, name, _, _ in _string.Formatter().parse(template) if name]
        except ValueError:
            return True         # an unparseable template is refused, not trusted
        return any("." in name or "[" in name for name in fields)

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        self.generic_visit(node)

    # --- structure --------------------------------------------------------------

    def _reject_async(self, node: ast.AST) -> None:
        self.fail(node, "async code is not allowed")

    visit_AsyncFunctionDef = _reject_async
    visit_Await = _reject_async
    visit_AsyncFor = _reject_async
    visit_AsyncWith = _reject_async


_ALLOWED_TOP = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef,
                ast.Assign, ast.AnnAssign)


def _check_structure(tree: ast.Module, params: frozenset[str]) -> str | None:
    """Exactly one top-level def run(<params>), and only tame statements beside it."""
    run_def: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            if run_def is not None:
                return f"line {node.lineno}: there must be exactly one run() function"
            run_def = node
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue          # a bare string: a module or docstring
        elif not isinstance(node, _ALLOWED_TOP):
            kind = type(node).__name__
            return f"line {node.lineno}: only imports, defs and assignments may sit " \
                   f"at the top level, not {kind}"
    if run_def is None:
        return "the tool must define a function called run"

    args = run_def.args
    if args.vararg or args.kwarg:
        return f"line {run_def.lineno}: run() must not use *args or **kwargs"
    got = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
    if set(got) != params:
        return f"line {run_def.lineno}: run() must take exactly these parameters: " \
               f"{', '.join(sorted(params))} (it takes {', '.join(got) or 'none'})"
    return None


def check(source: str, param_names) -> str | None:
    """None if the source is allowed to run, else 'line N: reason' for the first fault."""
    params = frozenset(param_names)
    if len(source) > config.MAX_SOURCE_CHARS:
        return f"the source is longer than {config.MAX_SOURCE_CHARS} characters"
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"line {exc.lineno}: the source does not parse ({exc.msg})"

    structural = _check_structure(tree, params)
    if structural is not None:
        return structural

    auditor = _Auditor(params)
    auditor.visit(tree)
    return auditor.problem


if __name__ == "__main__":
    good = ("def run(prefix):\n"
            "    total = sum(ord(c) for c in prefix)\n"
            "    return str(total % 36)\n")
    assert check(good, ["prefix"]) is None, check(good, ["prefix"])

    allowed = [
        "import json\ndef run(x):\n    return json.dumps(x)",
        "import collections\ndef run(x):\n    return collections.Counter(x).most_common(1)[0][0]",
        "from datetime import date\ndef run(date):\n    return str(date.fromisoformat(date).isocalendar().week)",
        "class C:\n    def __init__(self, n):\n        self._n = n\n    def value(self):\n        return self._n\ndef run(x):\n    return str(C(len(x)).value())",
        "def run(x):\n    try:\n        return str(int(x))\n    except ValueError:\n        return 'nan'",
    ]
    for src in allowed:
        params = {"date"} if "date" in src.split("def run(")[1][:6] else {"x"}
        assert check(src, params) is None, f"should allow: {src!r} -> {check(src, params)}"

    denied = {
        "import os": ("import os\ndef run(x):\n    return os.getcwd()", "os"),
        "from subprocess": ("from subprocess import run\ndef run(x):\n    return x", "subprocess"),
        "__import__": ("def run(x):\n    return __import__('os').getcwd()", "__import__"),
        "eval": ("def run(x):\n    return eval(x)", "eval"),
        "open": ("def run(x):\n    return open(x).read()", "open"),
        "getattr": ("def run(x):\n    return getattr(x, x)", "getattr"),
        "dunder class": ("def run(x):\n    return x.__class__.__bases__", "not allowed"),
        "typing pivot": ("import typing\ndef run(x):\n    return typing.sys.modules", "not allowed"),
        "collections._sys": ("import collections\ndef run(x):\n    return collections._sys", "_sys"),
        "mro walk": ("def run(x):\n    return ().__class__.__mro__", "not allowed"),
        "frame walk": ("def run(x):\n    return (lambda: 0).__code__", "__code__"),
        "format traversal": ("def run(x):\n    return '{0.__class__}'.format(x)", "format"),
        "bare except": ("def run(x):\n    try:\n        return x\n    except:\n        return 0", "bare"),
        "except Exception expr": ("def run(x):\n    try:\n        return x\n    except (Exception if x else ValueError):\n        return 0", "by name"),
        "return in finally": ("def run(x):\n    try:\n        return x\n    finally:\n        return 0", "finally"),
        "reserved prefix": ("def run(x):\n    _TS_y = 1\n    return _TS_y", "_TS_"),
        "two runs": ("def run(x):\n    return x\ndef run(x):\n    return x", "exactly one"),
        "wrong params": ("def run(a, b):\n    return a", "parameters"),
        "kwargs": ("def run(**k):\n    return k", "kwargs"),
        "async top-level": ("async def run(x):\n    return x", "AsyncFunctionDef"),
        "async nested": ("def run(x):\n    async def inner():\n        return x\n    return inner", "async"),
        "top-level call": ("print('hi')\ndef run(x):\n    return x", "top level"),
        "syntax error": ("def run(x)\n    return x", "does not parse"),
    }
    for label, (src, needle) in denied.items():
        result = check(src, {"x"})
        assert result is not None, f"{label} should be refused"
        assert needle in result, f"{label}: {result!r} lacks {needle!r}"

    print(f"allowed {len(allowed) + 1} samples, refused {len(denied)}; "
          f"first refusal example: {check(denied['import os'][0], {'x'})}")
    print("OK - guard")

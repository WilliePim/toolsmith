"""A toolbox that grows, as files: the tools the agent writes, saved to disk.

Inputs:  a validated ToolSpec (from smith.py), or the files already on disk
Outputs: schemas() for the tools array, call() to run one, load/save/reset

Each tool is two files: generated/<name>.py (the source, with a header) and
generated/<name>.json (its metadata and a sha256 of the source). On load the
guard and the hash both run again, so a file edited by hand is skipped, not
trusted - the parent process must never import a generated tool.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from src import config, guard, sandbox
from src.protocol import RESERVED_PREFIX

_NAME_RE = re.compile(r"[a-z][a-z0-9_]{2,39}$")


@dataclass(frozen=True, slots=True)
class Tool:
    """One registered tool: what the model sees, plus how to run and re-check it."""

    name: str
    description: str
    parameters: dict[str, Any]
    source: str
    family: str
    task_set: str
    tests: tuple[dict, ...]
    joiner: str
    created: str
    uses: int = 0

    @property
    def param_names(self) -> tuple[str, ...]:
        return tuple((self.parameters.get("properties") or {}).keys())

    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "parameters": self.parameters}


def valid_name(name: str) -> bool:
    """A tool name is lowercase, starts with a letter, and is not reserved."""
    return bool(_NAME_RE.match(name)) and not name.startswith(RESERVED_PREFIX.lower()) \
        and name not in {"calc", "today", "write_tool", "submit_answer", "run"}


def _sha(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _strip_header(text: str) -> str:
    """Drop the one-line header save() prepends, so the in-memory source is pure."""
    if text.startswith("# toolsmith tool "):
        return text.split("\n", 1)[1] if "\n" in text else ""
    return text


def _py_path(name: str) -> Path:
    return config.GENERATED_DIR / f"{name}.py"


def _json_path(name: str) -> Path:
    return config.GENERATED_DIR / f"{name}.json"


class Registry:
    """Every tool the agent has written this run, and the two files behind each."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # --- loading and saving -----------------------------------------------------

    def load_all(self, warn=lambda msg: None) -> None:
        """Read every tool on disk, re-checking the guard and the hash; skip the rest."""
        self._tools.clear()
        config.ensure_dirs()
        for meta_path in sorted(config.GENERATED_DIR.glob("*.json")):
            tool = self._load_one(meta_path, warn)
            if tool is not None:
                self._tools[tool.name] = tool

    def _load_one(self, meta_path: Path, warn) -> Tool | None:
        name = meta_path.stem
        source_path = _py_path(name)
        if not source_path.exists():
            warn(f"{name}: no .py beside {meta_path.name}, skipped")
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            source = source_path.read_text(encoding="utf-8")
        except (OSError, json.JSONDecodeError) as exc:
            warn(f"{name}: unreadable ({exc}), skipped")
            return None

        if not valid_name(name) or meta.get("name") != name:
            warn(f"{name}: name mismatch or not allowed, skipped")
            return None
        if _sha(source) != meta.get("sha256"):
            warn(f"{name}: sha256 does not match its source, skipped (tampered?)")
            return None
        body = _strip_header(source)      # in memory the source is header-free
        params = meta.get("parameters", {})
        problem = guard.check(body, (params.get("properties") or {}).keys())
        if problem is not None:
            warn(f"{name}: the guard now refuses it ({problem}), skipped")
            return None
        return Tool(name=name, description=meta.get("description", ""), parameters=params,
                    source=body, family=meta.get("family", ""),
                    task_set=meta.get("set", ""), tests=tuple(meta.get("tests", ())),
                    joiner=meta.get("joiner", ""), created=meta.get("created", ""),
                    uses=int(meta.get("uses", 0)))

    def save(self, tool: Tool) -> Tool:
        """Write the two files and hold the tool in memory."""
        config.ensure_dirs()
        header = f"# toolsmith tool {tool.name!r}, family {tool.family!r}, " \
                 f"written {tool.created}\n"
        file_text = header + tool.source.rstrip() + "\n"
        _py_path(tool.name).write_text(file_text, encoding="utf-8", newline="\n")
        # Hash the exact bytes on disk, so a reload of this same file matches.
        meta = {"name": tool.name, "description": tool.description,
                "parameters": tool.parameters, "set": tool.task_set,
                "family": tool.family, "joiner": tool.joiner,
                "tests": list(tool.tests), "created": tool.created,
                "uses": tool.uses, "sha256": _sha(file_text)}
        _json_path(tool.name).write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8", newline="\n")
        self._tools[tool.name] = tool
        return tool

    def reset(self) -> int:
        """Delete every generated tool; return how many were removed."""
        removed = 0
        config.ensure_dirs()
        for path in config.GENERATED_DIR.glob("*"):
            if path.suffix in (".py", ".json") and path.name != ".gitkeep":
                path.unlink()
                removed += 1
        self._tools.clear()
        return removed

    # --- using ------------------------------------------------------------------

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        """What the agent adds to the tools array, one per registered tool."""
        return [tool.schema() for tool in self._tools.values()]

    def call(self, name: str, calls: Sequence[dict]) -> sandbox.SandboxResult:
        """Run one tool over several calls, always in the sandbox, never in-process."""
        tool = self._tools.get(name)
        if tool is None:
            return sandbox.SandboxResult(
                results=[{"ok": False, "error": f"no tool called {name!r}"} for _ in calls],
                status="crashed", detail="unknown tool")
        return sandbox.run_calls(tool.source, list(calls))

    def record_use(self, name: str, times: int = 1) -> None:
        """Count a tool's uses, and persist the count."""
        tool = self._tools.get(name)
        if tool is not None:
            self.save(replace(tool, uses=tool.uses + times))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    import tempfile

    original = config.GENERATED_DIR
    with tempfile.TemporaryDirectory() as tmp:
        config.GENERATED_DIR = Path(tmp)     # write into a throwaway dir, not the repo
        try:
            reg = Registry()
            source = ("def run(prefix):\n"
                      "    return prefix[:1].upper()\n")
            tool = Tool(name="first_letter", description="First letter, upper-cased.",
                        parameters={"type": "object", "additionalProperties": False,
                                    "required": ["prefix"],
                                    "properties": {"prefix": {"type": "string"}}},
                        source=source, family="demo", task_set="core",
                        tests=({"args": {"prefix": "abc"}, "expect": "A"},),
                        joiner="", created=now_iso())
            reg.save(tool)

            reloaded = Registry()
            reloaded.load_all()
            assert "first_letter" in reloaded, "a saved tool must reload"
            assert reloaded.schemas()[0]["name"] == "first_letter"
            result = reloaded.call("first_letter", [{"prefix": "xyz"}, {"prefix": "def"}])
            assert result.ok and result.values() == ["X", "D"], result.values()

            reloaded.record_use("first_letter", 2)
            assert Registry().__class__ and json.loads(
                _json_path("first_letter").read_text(encoding="utf-8"))["uses"] == 2

            # Tamper with the source: the hash no longer matches, so it is skipped.
            _py_path("first_letter").write_text(
                "def run(prefix):\n    return 'HACKED'\n", encoding="utf-8")
            warnings: list[str] = []
            guarded = Registry()
            guarded.load_all(warn=warnings.append)
            assert "first_letter" not in guarded, "a tampered tool must be skipped"
            assert warnings and "sha256" in warnings[0], warnings

            assert not valid_name("_TS_x") and not valid_name("calc") and not valid_name("Run")
            assert valid_name("gstin_check_char")
            print(f"saved, reloaded and called first_letter -> {result.values()}")
            print(f"tamper skipped: {warnings[0]}")
            print("OK - registry")
        finally:
            config.GENERATED_DIR = original

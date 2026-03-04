"""CodeMaxxx — Tool implementations for the autonomous agent."""

import os
import glob as globlib
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolResult:
    success: bool
    output: str
    tool: str = ""


# ── File Tools ────────────────────────────────────────────────────

def read_file(path: str) -> ToolResult:
    try:
        p = os.path.abspath(os.path.expanduser(path))
        with open(p) as f:
            content = f.read()
        lines = content.splitlines()
        numbered = "\n".join(f"{i+1:4d} │ {l}" for i, l in enumerate(lines))
        return ToolResult(True, f"📄 {p} ({len(lines)} lines)\n{numbered}", "read_file")
    except Exception as e:
        return ToolResult(False, f"❌ {e}", "read_file")


def write_file(path: str, content: str) -> ToolResult:
    try:
        p = os.path.abspath(os.path.expanduser(path))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
        n = content.count("\n") + 1
        return ToolResult(True, f"✅ Wrote {n} lines → {p}", "write_file")
    except Exception as e:
        return ToolResult(False, f"❌ {e}", "write_file")


def edit_file(path: str, old: str, new: str) -> ToolResult:
    try:
        p = os.path.abspath(os.path.expanduser(path))
        with open(p) as f:
            content = f.read()
        if old not in content:
            return ToolResult(False, f"❌ Text not found in {p}", "edit_file")
        updated = content.replace(old, new, 1)
        with open(p, "w") as f:
            f.write(updated)
        return ToolResult(True, f"✅ Edited {p}", "edit_file")
    except Exception as e:
        return ToolResult(False, f"❌ {e}", "edit_file")


# ── Search Tools ──────────────────────────────────────────────────

def glob_search(pattern: str, cwd: str = ".") -> ToolResult:
    try:
        matches = sorted(globlib.glob(pattern, root_dir=cwd, recursive=True))[:100]
        if not matches:
            return ToolResult(True, "No files matched.", "glob")
        return ToolResult(True, f"Found {len(matches)} files:\n" + "\n".join(f"  {m}" for m in matches), "glob")
    except Exception as e:
        return ToolResult(False, f"❌ {e}", "glob")


def grep_search(pattern: str, path: str = ".", max_results: int = 50) -> ToolResult:
    try:
        cmd = f"grep -rn --include='*' -E {repr(pattern)} {repr(path)} 2>/dev/null | head -{max_results}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        if not output:
            return ToolResult(True, "No matches found.", "grep")
        lines = output.splitlines()
        return ToolResult(True, f"Found {len(lines)} matches:\n{output}", "grep")
    except Exception as e:
        return ToolResult(False, f"❌ {e}", "grep")


# ── Shell & Git ───────────────────────────────────────────────────

def shell_exec(cmd: str, cwd: str = ".") -> ToolResult:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, cwd=cwd)
        parts = []
        if result.stdout.strip():
            parts.append(result.stdout.strip())
        if result.stderr.strip():
            parts.append(f"stderr: {result.stderr.strip()}")
        output = "\n".join(parts) or "(no output)"
        return ToolResult(
            result.returncode == 0,
            f"$ {cmd}  [exit {result.returncode}]\n{output}",
            "shell",
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"❌ Timed out after 120s", "shell")
    except Exception as e:
        return ToolResult(False, f"❌ {e}", "shell")


def git_cmd(cmd: str, cwd: str = ".") -> ToolResult:
    return shell_exec(f"git {cmd}", cwd=cwd)


# ── Planning ──────────────────────────────────────────────────────

def make_plan(steps: list[str]) -> ToolResult:
    numbered = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
    return ToolResult(True, f"📋 Plan ({len(steps)} steps):\n{numbered}", "plan")


def signal_done(summary: str) -> ToolResult:
    return ToolResult(True, f"✅ Done: {summary}", "done")


# ── Memory Tools (need DB instance) ──────────────────────────────

def recall_memory(db, key: Optional[str] = None) -> ToolResult:
    if not db or not db.connected:
        return ToolResult(False, "❌ Database offline", "recall_memory")
    entries = db.read_memory(key)
    if not entries:
        return ToolResult(True, "No memories found.", "recall_memory")
    lines = [f"  🧠 {e['key']}: {e['value']}" for e in entries]
    return ToolResult(True, "Long-term memory:\n" + "\n".join(lines), "recall_memory")


def store_memory(db, key: str, value: str, model: str, write_key: str) -> ToolResult:
    if not db or not db.connected:
        return ToolResult(False, "❌ Database offline", "store_memory")
    from .config import MEMORY_WRITE_KEY
    if write_key != MEMORY_WRITE_KEY:
        return ToolResult(False, "❌ Write denied — invalid write_key", "store_memory")
    ok = db.write_memory(key, value, model, write_key)
    return ToolResult(ok, f"✅ Stored: {key}" if ok else "❌ Write failed", "store_memory")


def forget_memory(db, key: str, write_key: str) -> ToolResult:
    if not db or not db.connected:
        return ToolResult(False, "❌ Database offline", "forget_memory")
    from .config import MEMORY_WRITE_KEY
    if write_key != MEMORY_WRITE_KEY:
        return ToolResult(False, "❌ Delete denied — invalid write_key", "forget_memory")
    ok = db.delete_memory(key, write_key)
    return ToolResult(ok, f"✅ Deleted: {key}" if ok else "❌ Delete failed", "forget_memory")


# ── Dispatcher ────────────────────────────────────────────────────

TOOL_MAP = {
    "read_file": lambda a, **kw: read_file(a["path"]),
    "write_file": lambda a, **kw: write_file(a["path"], a["content"]),
    "edit_file": lambda a, **kw: edit_file(a["path"], a["old"], a["new"]),
    "shell": lambda a, **kw: shell_exec(a["cmd"], cwd=kw.get("cwd", ".")),
    "glob": lambda a, **kw: glob_search(a["pattern"], cwd=kw.get("cwd", ".")),
    "grep": lambda a, **kw: grep_search(a["pattern"], a.get("path", kw.get("cwd", "."))),
    "git": lambda a, **kw: git_cmd(a["cmd"], cwd=kw.get("cwd", ".")),
    "plan": lambda a, **kw: make_plan(a["steps"]),
    "done": lambda a, **kw: signal_done(a["summary"]),
}


def execute_tool(name: str, args: dict, db=None, cwd: str = ".", model: str = "") -> ToolResult:
    # Memory tools
    if name == "recall_memory":
        return recall_memory(db, args.get("key"))
    if name == "store_memory":
        return store_memory(db, args["key"], args["value"], model, args.get("write_key", ""))
    if name == "forget_memory":
        return forget_memory(db, args["key"], args.get("write_key", ""))

    handler = TOOL_MAP.get(name)
    if not handler:
        return ToolResult(False, f"❌ Unknown tool: {name}", name)
    return handler(args, cwd=cwd)

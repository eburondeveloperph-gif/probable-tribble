"""CodeMaxxx — File, search, shell, external automation, git, and memory tools."""

from __future__ import annotations

import glob as globlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ToolResult:
    success: bool
    output: str
    tool: str = ""


EXTERNAL_APPROVAL_TOOLS = {
    "gui_automation",
    "direct_system_control",
    "call_simulation",
    "os_automation",
}


def _resolve_path(path: str, cwd: str = ".") -> str:
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)
    return os.path.abspath(os.path.join(cwd, expanded))


def _render_lines(content: str) -> str:
    lines = content.splitlines()
    return "\n".join(f"{idx + 1:4d} │ {line}" for idx, line in enumerate(lines))


def read_file(path: str, cwd: str = ".") -> ToolResult:
    try:
        abspath = _resolve_path(path, cwd)
        with open(abspath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return ToolResult(
            True,
            f"📄 {abspath} ({len(content.splitlines())} lines)\n{_render_lines(content)}",
            "read_file",
        )
    except Exception as e:
        return ToolResult(False, f"❌ read_file: {e}", "read_file")


def write_file(path: str, content: str, cwd: str = ".") -> ToolResult:
    try:
        abspath = _resolve_path(path, cwd)
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        with open(abspath, "w", encoding="utf-8") as f:
            f.write(content)
        lines = content.count("\n") + 1
        return ToolResult(True, f"✅ Wrote {lines} lines to {abspath}", "write_file")
    except Exception as e:
        return ToolResult(False, f"❌ write_file: {e}", "write_file")


def edit_file(path: str, old: str, new: str, cwd: str = ".") -> ToolResult:
    try:
        abspath = _resolve_path(path, cwd)
        with open(abspath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if old not in content:
            return ToolResult(False, f"❌ edit_file: text not found in {abspath}", "edit_file")
        updated = content.replace(old, new, 1)
        with open(abspath, "w", encoding="utf-8") as f:
            f.write(updated)
        return ToolResult(True, f"✅ Edited {abspath}", "edit_file")
    except Exception as e:
        return ToolResult(False, f"❌ edit_file: {e}", "edit_file")


def list_dir(path: str = ".", cwd: str = ".", limit: int = 300) -> ToolResult:
    try:
        abspath = _resolve_path(path, cwd)
        entries = sorted(os.listdir(abspath))
        shown = entries[:limit]
        lines = []
        for name in shown:
            p = os.path.join(abspath, name)
            kind = "dir" if os.path.isdir(p) else "file"
            lines.append(f"{kind:4s}  {name}")
        suffix = "" if len(entries) <= limit else f"\n... truncated ({len(entries) - limit} more)"
        return ToolResult(True, f"📂 {abspath}\n" + "\n".join(lines) + suffix, "list_dir")
    except Exception as e:
        return ToolResult(False, f"❌ list_dir: {e}", "list_dir")


def glob_search(pattern: str, cwd: str = ".", limit: int = 200) -> ToolResult:
    try:
        target_pattern = pattern
        if not os.path.isabs(pattern):
            target_pattern = os.path.join(cwd, pattern)
        matches = sorted(globlib.glob(target_pattern, recursive=True))
        if not matches:
            return ToolResult(True, "No files matched.", "glob")
        lines = []
        for p in matches[:limit]:
            rel = os.path.relpath(p, cwd)
            lines.append(rel)
        suffix = "" if len(matches) <= limit else f"\n... truncated ({len(matches) - limit} more)"
        return ToolResult(True, f"Found {len(matches)} files:\n" + "\n".join(lines) + suffix, "glob")
    except Exception as e:
        return ToolResult(False, f"❌ glob: {e}", "glob")


def grep_search(pattern: str, path: str = ".", cwd: str = ".", max_results: int = 80) -> ToolResult:
    try:
        search_path = _resolve_path(path, cwd)
        lines: list[str] = []

        if shutil.which("rg"):
            result = subprocess.run(
                ["rg", "-n", "--no-heading", "--color", "never", "-e", pattern, search_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode not in (0, 1):
                stderr = result.stderr.strip() or "rg failed"
                return ToolResult(False, f"❌ grep: {stderr}", "grep")
            lines = result.stdout.splitlines()
        else:
            result = subprocess.run(
                ["grep", "-R", "-n", "-E", pattern, search_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode not in (0, 1):
                stderr = result.stderr.strip() or "grep failed"
                return ToolResult(False, f"❌ grep: {stderr}", "grep")
            lines = result.stdout.splitlines()

        if not lines:
            return ToolResult(True, "No matches found.", "grep")

        shown = lines[:max_results]
        suffix = "" if len(lines) <= max_results else f"\n... truncated ({len(lines) - max_results} more)"
        return ToolResult(True, f"Found {len(lines)} matches:\n" + "\n".join(shown) + suffix, "grep")
    except Exception as e:
        return ToolResult(False, f"❌ grep: {e}", "grep")


def _run_command(cmd: str, cwd: str = ".", timeout: int = 120, tool_name: str = "shell") -> ToolResult:
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output_parts = []
        if result.stdout.strip():
            output_parts.append(result.stdout.strip())
        if result.stderr.strip():
            output_parts.append(f"stderr: {result.stderr.strip()}")
        output = "\n".join(output_parts) or "(no output)"
        ok = result.returncode == 0
        prefix = f"$ {cmd}  [exit {result.returncode}]"
        return ToolResult(ok, f"{prefix}\n{output}", tool_name)
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"❌ {tool_name}: command timed out after {timeout}s", tool_name)
    except Exception as e:
        return ToolResult(False, f"❌ {tool_name}: {e}", tool_name)


def shell_exec(cmd: str, cwd: str = ".") -> ToolResult:
    return _run_command(cmd, cwd=cwd, timeout=120, tool_name="shell")


def git_cmd(cmd: str, cwd: str = ".") -> ToolResult:
    cleaned = cmd.strip()
    if cleaned.startswith("git "):
        cleaned = cleaned[4:]
    return shell_exec(f"git {cleaned}", cwd=cwd)


def gui_automation_cmd(cmd: str, cwd: str = ".") -> ToolResult:
    result = _run_command(cmd, cwd=cwd, timeout=180, tool_name="gui_automation")
    return ToolResult(
        result.success,
        "GUI automation external command executed.\n" + result.output,
        "gui_automation",
    )


def direct_system_control_cmd(cmd: str, cwd: str = ".") -> ToolResult:
    result = _run_command(cmd, cwd=cwd, timeout=180, tool_name="direct_system_control")
    return ToolResult(
        result.success,
        "Direct system control external command executed.\n" + result.output,
        "direct_system_control",
    )


def os_automation_cmd(cmd: str, cwd: str = ".") -> ToolResult:
    result = _run_command(cmd, cwd=cwd, timeout=180, tool_name="os_automation")
    return ToolResult(
        result.success,
        "OS-level automation external command executed.\n" + result.output,
        "os_automation",
    )


def call_simulation_cmd(scenario: str = "", cmd: str = "", cwd: str = ".") -> ToolResult:
    scenario_text = (scenario or "").strip()
    command_text = (cmd or "").strip()

    if not scenario_text and not command_text:
        return ToolResult(
            False,
            "❌ call_simulation: provide at least 'scenario' or 'cmd'.",
            "call_simulation",
        )

    if not command_text:
        return ToolResult(
            True,
            f"Prepared call simulation scenario (no external command executed):\n{scenario_text}",
            "call_simulation",
        )

    result = _run_command(command_text, cwd=cwd, timeout=240, tool_name="call_simulation")
    scenario_line = scenario_text or "(scenario not provided)"
    return ToolResult(
        result.success,
        f"Call simulation scenario: {scenario_line}\n" + result.output,
        "call_simulation",
    )


TOOLS = {
    "read_file": (lambda args, **kw: read_file(args["path"], cwd=kw.get("cwd", ".")), ("path",)),
    "write_file": (
        lambda args, **kw: write_file(args["path"], args["content"], cwd=kw.get("cwd", ".")),
        ("path", "content"),
    ),
    "edit_file": (
        lambda args, **kw: edit_file(args["path"], args["old"], args["new"], cwd=kw.get("cwd", ".")),
        ("path", "old", "new"),
    ),
    "list_dir": (
        lambda args, **kw: list_dir(args.get("path", "."), cwd=kw.get("cwd", ".")),
        (),
    ),
    "glob": (lambda args, **kw: glob_search(args["pattern"], cwd=kw.get("cwd", ".")), ("pattern",)),
    "grep": (
        lambda args, **kw: grep_search(
            args["pattern"],
            path=args.get("path", "."),
            cwd=kw.get("cwd", "."),
        ),
        ("pattern",),
    ),
    "shell": (lambda args, **kw: shell_exec(args["cmd"], cwd=kw.get("cwd", ".")), ("cmd",)),
    "git": (lambda args, **kw: git_cmd(args["cmd"], cwd=kw.get("cwd", ".")), ("cmd",)),
    "gui_automation": (
        lambda args, **kw: gui_automation_cmd(args["cmd"], cwd=kw.get("cwd", ".")),
        ("cmd",),
    ),
    "direct_system_control": (
        lambda args, **kw: direct_system_control_cmd(args["cmd"], cwd=kw.get("cwd", ".")),
        ("cmd",),
    ),
    "call_simulation": (
        lambda args, **kw: call_simulation_cmd(
            scenario=args.get("scenario", ""),
            cmd=args.get("cmd", ""),
            cwd=kw.get("cwd", "."),
        ),
        (),
    ),
    "os_automation": (
        lambda args, **kw: os_automation_cmd(args["cmd"], cwd=kw.get("cwd", ".")),
        ("cmd",),
    ),
}

MEMORY_TOOLS = {"recall_memory", "store_memory", "forget_memory"}


def _missing_required(args: dict, required: tuple[str, ...]) -> list[str]:
    return [key for key in required if key not in args]


def execute_tool(
    name: str,
    args: dict,
    db=None,
    cwd: str = ".",
    model: str = "",
    allowed_tools: Optional[set[str]] = None,
    confirm_external: Optional[Callable[[str, dict], bool]] = None,
) -> ToolResult:
    """Dispatch a tool call with graceful validation errors."""
    if not isinstance(args, dict):
        return ToolResult(False, "❌ Invalid tool args payload; expected JSON object.", name)

    if allowed_tools is not None and name not in allowed_tools:
        return ToolResult(False, f"❌ Tool '{name}' is not allowed in this step.", name)

    requires_external_approval = name in EXTERNAL_APPROVAL_TOOLS
    if name == "call_simulation" and not str(args.get("cmd", "")).strip():
        requires_external_approval = False

    if requires_external_approval:
        if confirm_external is None:
            return ToolResult(
                False,
                f"❌ Tool '{name}' requires explicit user approval callback.",
                name,
            )
        try:
            approved = bool(confirm_external(name, args))
        except Exception as e:
            return ToolResult(False, f"❌ External approval error for '{name}': {e}", name)
        if not approved:
            return ToolResult(False, f"❌ External tool '{name}' denied by user.", name)

    # Memory tools
    if name == "recall_memory":
        if not db:
            return ToolResult(False, "❌ Database not connected — memory unavailable.", name)
        key = args.get("key")
        entries = db.read_memory(key)
        if not entries:
            return ToolResult(True, "No memories found." if not key else f"No memory for key '{key}'.", name)
        lines = [f"  🧠 {e['key']}: {e['value']}" for e in entries]
        return ToolResult(True, "Long-term memory:\n" + "\n".join(lines), name)

    if name == "store_memory":
        if not db:
            return ToolResult(False, "❌ Database not connected — memory unavailable.", name)
        missing = _missing_required(args, ("key", "value"))
        if missing:
            return ToolResult(False, f"❌ Missing arguments: {', '.join(missing)}", name)
        write_key = args.get("write_key", "")
        ok = db.write_memory(args["key"], args["value"], args.get("model", model), write_key)
        if ok:
            return ToolResult(True, f"✅ Stored memory: {args['key']}", name)
        return ToolResult(False, "❌ Write denied — invalid write_key.", name)

    if name == "forget_memory":
        if not db:
            return ToolResult(False, "❌ Database not connected — memory unavailable.", name)
        missing = _missing_required(args, ("key",))
        if missing:
            return ToolResult(False, f"❌ Missing arguments: {', '.join(missing)}", name)
        write_key = args.get("write_key", "")
        ok = db.delete_memory(args["key"], write_key)
        if ok:
            return ToolResult(True, f"✅ Deleted memory: {args['key']}", name)
        return ToolResult(False, "❌ Delete denied — invalid write_key.", name)

    if name in MEMORY_TOOLS and not db:
        return ToolResult(False, "❌ Database not connected — memory unavailable.", name)

    handler_tuple = TOOLS.get(name)
    if not handler_tuple:
        return ToolResult(False, f"❌ Unknown tool: {name}", name)

    handler, required = handler_tuple
    missing = _missing_required(args, required)
    if missing:
        return ToolResult(False, f"❌ Missing arguments: {', '.join(missing)}", name)

    try:
        return handler(args, db=db, cwd=cwd, model=model)
    except Exception as e:
        return ToolResult(False, f"❌ {name}: {e}", name)

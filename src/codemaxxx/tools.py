"""CodeMaxxx — File and shell tools."""

import os
import subprocess
from dataclasses import dataclass


@dataclass
class ToolResult:
    success: bool
    output: str


def read_file(path: str) -> ToolResult:
    """Read a file and return its contents."""
    try:
        abspath = os.path.abspath(os.path.expanduser(path))
        with open(abspath, "r") as f:
            content = f.read()
        lines = content.splitlines()
        numbered = "\n".join(f"{i+1:4d} │ {line}" for i, line in enumerate(lines))
        return ToolResult(True, f"📄 {abspath} ({len(lines)} lines)\n{numbered}")
    except Exception as e:
        return ToolResult(False, f"❌ read_file: {e}")


def write_file(path: str, content: str) -> ToolResult:
    """Write content to a file (creates dirs if needed)."""
    try:
        abspath = os.path.abspath(os.path.expanduser(path))
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        with open(abspath, "w") as f:
            f.write(content)
        lines = content.count("\n") + 1
        return ToolResult(True, f"✅ Wrote {lines} lines to {abspath}")
    except Exception as e:
        return ToolResult(False, f"❌ write_file: {e}")


def edit_file(path: str, old: str, new: str) -> ToolResult:
    """Replace first occurrence of `old` with `new` in a file."""
    try:
        abspath = os.path.abspath(os.path.expanduser(path))
        with open(abspath, "r") as f:
            content = f.read()
        if old not in content:
            return ToolResult(False, f"❌ edit_file: text not found in {abspath}")
        updated = content.replace(old, new, 1)
        with open(abspath, "w") as f:
            f.write(updated)
        return ToolResult(True, f"✅ Edited {abspath}")
    except Exception as e:
        return ToolResult(False, f"❌ edit_file: {e}")


def shell_exec(cmd: str) -> ToolResult:
    """Execute a shell command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=os.getcwd(),
        )
        output_parts = []
        if result.stdout.strip():
            output_parts.append(result.stdout.strip())
        if result.stderr.strip():
            output_parts.append(f"stderr: {result.stderr.strip()}")
        output = "\n".join(output_parts) or "(no output)"
        ok = result.returncode == 0
        prefix = f"$ {cmd}  [exit {result.returncode}]"
        return ToolResult(ok, f"{prefix}\n{output}")
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"❌ shell: command timed out after 60s")
    except Exception as e:
        return ToolResult(False, f"❌ shell: {e}")


TOOLS = {
    "read_file": lambda args: read_file(args["path"]),
    "write_file": lambda args: write_file(args["path"], args["content"]),
    "edit_file": lambda args: edit_file(args["path"], args["old"], args["new"]),
    "shell": lambda args: shell_exec(args["cmd"]),
}


# Memory tools are registered separately since they need the DB instance
MEMORY_TOOLS = {"recall_memory", "store_memory", "forget_memory"}


def execute_tool(name: str, args: dict, db=None) -> ToolResult:
    """Dispatch a tool call."""
    # Memory tools
    if name == "recall_memory" and db:
        key = args.get("key")
        entries = db.read_memory(key)
        if not entries:
            return ToolResult(True, "No memories found." if not key else f"No memory for key '{key}'.")
        lines = [f"  🧠 {e['key']}: {e['value']}" for e in entries]
        return ToolResult(True, "Long-term memory:\n" + "\n".join(lines))

    if name == "store_memory" and db:
        write_key = args.get("write_key", "")
        ok = db.write_memory(args["key"], args["value"], args.get("model", ""), write_key)
        if ok:
            return ToolResult(True, f"✅ Stored memory: {args['key']}")
        return ToolResult(False, "❌ Write denied — invalid write_key.")

    if name == "forget_memory" and db:
        write_key = args.get("write_key", "")
        ok = db.delete_memory(args["key"], write_key)
        if ok:
            return ToolResult(True, f"✅ Deleted memory: {args['key']}")
        return ToolResult(False, "❌ Delete denied — invalid write_key.")

    if name in MEMORY_TOOLS and not db:
        return ToolResult(False, "❌ Database not connected — memory unavailable.")

    handler = TOOLS.get(name)
    if not handler:
        return ToolResult(False, f"❌ Unknown tool: {name}")
    return handler(args)

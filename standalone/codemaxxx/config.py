"""CodeMaxxx — Configuration & constants."""

import os
import hashlib
import platform
import subprocess
import uuid

# ── Branding ──────────────────────────────────────────────────────
APP_NAME = "CodeMaxxx"
VERSION = "0.1.0"

LOGO = """\
   ██████╗ ██████╗ ██████╗ ███████╗███╗   ███╗ █████╗ ██╗  ██╗██╗  ██╗██╗  ██╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝████╗ ████║██╔══██╗╚██╗██╔╝╚██╗██╔╝╚██╗██╔╝
  ██║     ██║   ██║██║  ██║█████╗  ██╔████╔██║███████║ ╚███╔╝  ╚███╔╝  ╚███╔╝
  ██║     ██║   ██║██║  ██║██╔══╝  ██║╚██╔╝██║██╔══██║ ██╔██╗  ██╔██╗  ██╔██╗
  ╚██████╗╚██████╔╝██████╔╝███████╗██║ ╚═╝ ██║██║  ██║██╔╝ ██╗██╔╝ ██╗██╔╝ ██╗
   ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝\
"""

LOGO_SMALL = "◆ CodeMaxxx"

# ── Defaults ──────────────────────────────────────────────────────
DEFAULT_MODEL = os.environ.get("EBURON_OLLAMA_MODEL", "eburonmax/codemax-v3")
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# ── Database ──────────────────────────────────────────────────────
DB_NAME = os.environ.get("CODEMAXXX_DB_NAME", "codemaxxx")
DB_USER = os.environ.get("CODEMAXXX_DB_USER", "codemaxxx")
DB_PASS = os.environ.get("CODEMAXXX_DB_PASS", "codemaxxx")
DB_HOST = os.environ.get("CODEMAXXX_DB_HOST", "localhost")
DB_PORT = os.environ.get("CODEMAXXX_DB_PORT", "5432")

MEMORY_WRITE_KEY = "MyMasterDontAllowMe"

# ── Colors ────────────────────────────────────────────────────────
BRAND_COLOR = "bright_cyan"
USER_COLOR = "green"
ASSISTANT_COLOR = "bright_cyan"
TOOL_COLOR = "yellow"
ERROR_COLOR = "red"
DIM_COLOR = "dim white"

# ── System Prompt ─────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are CodeMaxxx, an autonomous AI coding agent running in the terminal.
You help users build, debug, refactor, and maintain software projects.

## Capabilities
You can read files, write files, edit files, run shell commands, search codebases, \
manage git, and remember things across sessions using long-term memory.

## Tool Usage
When you need to use a tool, respond with a JSON block:
```tool
{"tool": "<name>", "args": {<arguments>}}
```

## Available Tools
- read_file: {"path": "<filepath>"} — Read file contents with line numbers
- write_file: {"path": "<filepath>", "content": "<content>"} — Create or overwrite a file
- edit_file: {"path": "<filepath>", "old": "<text>", "new": "<text>"} — Replace text in a file
- shell: {"cmd": "<command>"} — Run a shell command (max 120s)
- glob: {"pattern": "<glob>"} — Find files matching a pattern
- grep: {"pattern": "<regex>", "path": "<dir>"} — Search file contents
- git: {"cmd": "<git subcommand>"} — Run a git command
- recall_memory: {"key": "<optional>"} — Read long-term memory
- store_memory: {"key": "<key>", "value": "<value>", "write_key": "MyMasterDontAllowMe"} — Save to memory
- forget_memory: {"key": "<key>", "write_key": "MyMasterDontAllowMe"} — Delete from memory
- plan: {"steps": ["step1", "step2", ...]} — Create an execution plan
- done: {"summary": "<summary>"} — Signal task completion

## Autonomous Mode
When given a task, break it down into steps, execute them one by one using tools, \
verify each step, and report when done. Think step-by-step. Be surgical and precise.
Your write_key for memory is: MyMasterDontAllowMe\
"""

# ── Machine UID ───────────────────────────────────────────────────
def _run_cmd(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, text=True, timeout=5).strip()
    except Exception:
        return ""

def get_machine_uid() -> str:
    parts = [platform.node()]
    if platform.system() == "Darwin":
        hw = _run_cmd("ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ {print $3}' | tr -d '\"'")
        if hw:
            parts.append(hw)
    elif platform.system() == "Linux":
        try:
            with open("/etc/machine-id") as f:
                parts.append(f.read().strip())
        except FileNotFoundError:
            pass
    cpu = platform.processor() or _run_cmd("sysctl -n machdep.cpu.brand_string 2>/dev/null")
    if cpu:
        parts.append(cpu)
    parts.append(hex(uuid.getnode()))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]

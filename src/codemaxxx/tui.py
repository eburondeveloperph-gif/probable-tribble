"""CodeMaxxx — TUI layout and rendering with Rich."""

from __future__ import annotations

import random
from typing import Optional

from rich.align import Align
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

THEME = Theme(
    {
        "brand": "bold bright_cyan",
        "user": "bold green",
        "assistant": "bold bright_cyan",
        "tool": "bold yellow",
        "error": "bold red",
        "dim": "dim white",
        "success": "bold green",
    }
)

LOGO = r"""
  ____ ___  ____  _____ __  __    _    __  __
 / ___/ _ \|  _ \| ____|  \/  |  / \  \ \/ /
| |  | | | | | | |  _| | |\/| | / _ \  \  /
| |__| |_| | |_| | |___| |  | |/ ___ \ /  \
 \____\___/|____/|_____|_|  |_/_/   \_/_/\_\
"""

console = Console(theme=THEME)

_STATUS: Optional[Status] = None
_STREAM_OPEN = False
_STREAM_SKILL = ""
_DYNAMIC_STATUS_QUIPS: list[str] = []
_MAX_DYNAMIC_STATUS_QUIPS = 32
_SESSION_APP_NAME = "codemax"
_SESSION_WORKSPACE = "."
_SESSION_TOTAL_TOKENS = 0

HUMOROUS_THINKING = [
    "consulting the rubber duck council 🦆",
    "negotiating with semicolons like a diplomat",
    "asking the stack trace for emotional support 😅",
    "warming up the syntax goblins",
    "thinking hard while pretending this is easy",
]

HUMOROUS_LOADING = [
    "loading tiny digital forklifts",
    "reticulating source maps",
    "untangling recursive spaghetti",
    "tightening bolts on the token conveyor",
    "i'll tell your TODO list you ignored it 😏",
]


def queue_status_quip(quip: str):
    """Queue a dynamic loading/thinking quip produced by another agent."""
    text = (quip or "").strip()
    if not text:
        return
    if len(text) > 140:
        text = text[:137] + "..."
    _DYNAMIC_STATUS_QUIPS.append(text)
    if len(_DYNAMIC_STATUS_QUIPS) > _MAX_DYNAMIC_STATUS_QUIPS:
        del _DYNAMIC_STATUS_QUIPS[: len(_DYNAMIC_STATUS_QUIPS) - _MAX_DYNAMIC_STATUS_QUIPS]


def set_session_footer(
    app_name: Optional[str] = None,
    workspace_name: Optional[str] = None,
    total_tokens_created: Optional[int] = None,
):
    """Update the session footer values used by prompt/loading UI."""
    global _SESSION_APP_NAME, _SESSION_WORKSPACE, _SESSION_TOTAL_TOKENS

    if app_name is not None:
        _SESSION_APP_NAME = (app_name or "codemax").strip() or "codemax"
    if workspace_name is not None:
        _SESSION_WORKSPACE = (workspace_name or ".").strip() or "."
    if total_tokens_created is not None:
        try:
            _SESSION_TOTAL_TOKENS = max(0, int(total_tokens_created))
        except (TypeError, ValueError):
            _SESSION_TOTAL_TOKENS = 0


def _session_meta_text() -> str:
    return (
        f"{_SESSION_APP_NAME}  /workspace {_SESSION_WORKSPACE}  "
        f"/total tokens created {_SESSION_TOTAL_TOKENS:,}"
    )


def _next_dynamic_quip() -> Optional[str]:
    if not _DYNAMIC_STATUS_QUIPS:
        return None
    return _DYNAMIC_STATUS_QUIPS.pop(0)


def _next_quip(pool: list[str]) -> str:
    return random.choice(pool)


def clear_status():
    """Stop the active loading/thinking spinner, if any."""
    global _STATUS
    if _STATUS is None:
        return
    _STATUS.__exit__(None, None, None)
    _STATUS = None


def status_active() -> bool:
    """Return whether a status spinner is currently active."""
    return _STATUS is not None


def stream_active() -> bool:
    """Return whether token streaming is currently active."""
    return _STREAM_OPEN


def print_live_humor(msg: str):
    """Print a live humor line during streaming/loading phases."""
    global _STREAM_OPEN, _STREAM_SKILL

    text = (msg or "").strip()
    if not text:
        return

    if _STATUS is not None:
        clear_status()

    if _STREAM_OPEN:
        console.print()
        _STREAM_OPEN = False
        _STREAM_SKILL = ""

    console.print(f"  [dim]⋯ {text}[/dim]")


def finish_stream():
    """Close an active streaming line cleanly."""
    global _STREAM_OPEN, _STREAM_SKILL
    if _STREAM_OPEN:
        console.print()
    _STREAM_OPEN = False
    _STREAM_SKILL = ""


def update_status(status: str):
    """Render/update a Gemini-like thinking/loading status line."""
    global _STATUS

    stage = (status or "working").strip()
    stage_lower = stage.lower()

    if stage_lower == "done":
        clear_status()
        return

    thinking_tokens = ("think", "plan", "review", "step", "analy", "reason")
    dynamic = _next_dynamic_quip()
    if dynamic:
        quip = dynamic
    else:
        quips = HUMOROUS_THINKING if any(tok in stage_lower for tok in thinking_tokens) else HUMOROUS_LOADING
        quip = _next_quip(quips)
    line = f"[dim]{stage} • {quip}[/dim]"

    if _STATUS is None:
        _STATUS = console.status(line, spinner="dots")
        _STATUS.__enter__()
    else:
        _STATUS.update(line)


def print_header(model: str, host: str, workflow: str = "manus"):
    """Print the fullscreen-style landing header."""
    clear_status()
    finish_stream()
    console.clear()

    top_pad = 1
    for _ in range(top_pad):
        console.print()

    console.print(Align.center(Text(LOGO, style="bold bright_white")))
    console.print(Align.center(Text("by Eburon AI", style="dim")))
    console.print()

def _landing_shortcuts_line():
    shortcuts = Text()
    shortcuts.append("ctrl+u", style="bold bright_white")
    shortcuts.append(" tab agents    ", style="dim")
    shortcuts.append("ctrl+i", style="bold bright_white")
    shortcuts.append(" commands", style="dim")
    console.print()
    console.print(Align.center(shortcuts))
    console.print()


def print_prompt_footer():
    """Render session metadata with a 3-line colored full-width separator."""
    width = max(20, console.size.width - 1)
    gap = " " * width
    for style in ("on bright_cyan", "on cyan", "on bright_blue"):
        console.print(Text(gap, style=style), no_wrap=True, overflow="crop")

    line = Text()
    line.append(f"{_SESSION_APP_NAME} ", style="brand")
    line.append("/workspace ", style="dim")
    line.append(_SESSION_WORKSPACE, style="assistant")
    line.append(" /total tokens created ", style="dim")
    line.append(f"{_SESSION_TOTAL_TOKENS:,}", style="brand")
    console.print(line)


def input_first_prompt() -> str:
    """Render first-prompt clipped box style and collect user input."""
    width = min(78, max(48, console.size.width - 8))
    left_pad = max(0, (console.size.width - width) // 2)
    left = " " * left_pad

    def vrow(text: str = "") -> str:
        clipped = text[:width]
        return f"{left}┃ {clipped}"

    console.print(f"{left}┃")
    console.print(vrow('Ask anything... "Fix broken tests"'))
    console.print(f"{left}┃")
    console.print(vrow("AUTOMATE codemax"))
    console.print(f"{left}┃")
    user_input = console.input(f"{left}┃  [green]❯[/green] ").strip()
    console.print(f"{left}╹" + ("▀" * width))
    _landing_shortcuts_line()
    return user_input


def print_user_msg(msg: str):
    """Print a user message."""
    clear_status()
    finish_stream()
    console.print(
        Panel(
            Text(msg),
            title="[user]You[/user]",
            border_style="green",
            padding=(0, 1),
        )
    )


def print_assistant_start():
    """Print assistant header."""
    clear_status()
    finish_stream()
    console.print(Text("\n ◆ CodeMaxxx", style="brand"))


def print_streamed_chunk(skill: str, chunk: str):
    """Print streamed model tokens in real-time."""
    global _STREAM_OPEN, _STREAM_SKILL

    if not chunk:
        return

    clear_status()

    if (not _STREAM_OPEN) or (_STREAM_SKILL != skill):
        if _STREAM_OPEN:
            console.print()
        console.print(Text(f"  ├─ {skill} ", style="assistant"), end="")
        _STREAM_OPEN = True
        _STREAM_SKILL = skill

    console.print(chunk, end="", highlight=False)


def print_assistant_md(content: str):
    """Print final assistant response as rendered markdown."""
    clear_status()
    finish_stream()
    console.print()
    console.print(
        Panel(
            Markdown(content),
            title="[assistant]CodeMaxxx[/assistant]",
            border_style="bright_cyan",
            padding=(0, 1),
        )
    )


def print_tool_call(name: str, args: dict):
    """Print a tool invocation."""
    clear_status()
    finish_stream()
    args_str = ", ".join(f"{k}={repr(v)[:80]}" for k, v in args.items())
    console.print(
        Panel(
            Text(f"{name}({args_str})", style="yellow"),
            title="[tool]⚡ Tool Call[/tool]",
            border_style="yellow",
            padding=(0, 1),
        )
    )


def print_tool_result(result):
    """Print a tool result."""
    clear_status()
    finish_stream()
    style = "success" if result.success else "error"
    tool_name = getattr(result, "tool", "tool") or "tool"
    console.print(
        Panel(
            Text(result.output[:3000]),
            title=f"[{style}]{tool_name}[/{style}]",
            border_style="green" if result.success else "red",
            padding=(0, 1),
        )
    )


def print_error(msg: str):
    """Print an error."""
    clear_status()
    finish_stream()
    console.print(f"  [error]✖ {msg}[/error]")


def print_info(msg: str):
    """Print info."""
    clear_status()
    finish_stream()
    console.print(f"  [dim]{msg}[/dim]")


def print_help():
    """Print help."""
    clear_status()
    finish_stream()
    help_table = Table.grid(padding=(0, 2))
    help_table.add_row("[brand]/help[/brand]", "Show this help")
    help_table.add_row("[brand]/commands[/brand]", "Alias for /help")
    help_table.add_row("[brand]/agents[/brand]", "Alias for /skills")
    help_table.add_row("[brand]/copy-last[/brand]", "Copy last assistant response to clipboard")
    help_table.add_row("[brand]/copy <text>[/brand]", "Copy custom text to clipboard")
    help_table.add_row("[brand]/skills[/brand]", "Show dedicated skill agents and model routing")
    help_table.add_row("[brand]/skills-custom[/brand]", "Show user-created custom skills")
    help_table.add_row("[brand]/skill-create <name>[/brand]", "Create/update your own skill interactively")
    help_table.add_row("[brand]/skills-offline[/brand]", "Show full offline autonomy skill framework")
    help_table.add_row("[brand]/skills-online[/brand]", "Show 30 online-mode autonomous skills")
    help_table.add_row("[brand]/skills-all[/brand]", "Show offline + online full skill map")
    help_table.add_row("[brand]/roadmap-online[/brand]", "Show full 50-skill browser/UI roadmap")
    help_table.add_row("[brand]/roadmap-online-start[/brand]", "Show required first 8 build skills")
    help_table.add_row("[brand]/roadmap-online-phase <1-7>[/brand]", "Show one roadmap phase with dependencies")
    help_table.add_row("[brand]/autolearn-now[/brand]", "Run DB learning pass immediately")
    help_table.add_row("[brand]/personality-save <text>[/brand]", "Save user personality profile to memory")
    help_table.add_row("[brand]/personality-show[/brand]", "Show saved personality profile")
    help_table.add_row("[brand]/humor-profile <text>[/brand]", "Save loading-humor preference profile")
    help_table.add_row("[brand]/humor-profile-show[/brand]", "Show saved loading-humor profile")
    help_table.add_row("[brand]/workflow[/brand]", "Show active workflow details")
    help_table.add_row("[brand]/choices[/brand]", "Show pending numbered options from last assistant output")
    help_table.add_row("[brand]/pick <n>[/brand]", "Select a pending option and continue execution")
    help_table.add_row("[brand]/clear[/brand]", "Clear in-memory skill contexts")
    help_table.add_row("[brand]/model <name>[/brand]", "Set fallback model for skill routing")
    help_table.add_row("[brand]/quit[/brand]", "Exit CodeMaxxx")
    help_table.add_row("", "")
    help_table.add_row("[dim]Ctrl+C[/dim]", "Cancel current response")
    help_table.add_row("[dim]Ctrl+D[/dim]", "Exit")
    console.print(Panel(help_table, title="[brand]Commands[/brand]", border_style="bright_cyan"))

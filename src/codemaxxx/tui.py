"""CodeMaxxx — TUI layout and rendering with Rich."""

from __future__ import annotations

from importlib import metadata as importlib_metadata
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
LOGO_COMPACT = "CODEMAX"
APP_BRAND = "Codemax"
_APP_VERSION = ""

console = Console(theme=THEME)

_STATUS: Optional[Status] = None
_STREAM_OPEN = False
_STREAM_SKILL = ""
_DYNAMIC_STATUS_QUIPS: list[str] = []
_MAX_DYNAMIC_STATUS_QUIPS = 32
_SESSION_APP_NAME = "codemax"
_SESSION_WORKSPACE = "."
_SESSION_TOTAL_TOKENS = 0
_SESSION_KISSME_SECONDS = 0

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


def set_kissme_countdown(seconds_left: int):
    """Update auth countdown shown in prompt footer."""
    global _SESSION_KISSME_SECONDS
    try:
        _SESSION_KISSME_SECONDS = max(0, int(seconds_left))
    except (TypeError, ValueError):
        _SESSION_KISSME_SECONDS = 0


def _format_hms(total_seconds: int) -> str:
    sec = max(0, int(total_seconds))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _session_meta_text() -> str:
    return (
        f"{_SESSION_APP_NAME}  /workspace {_SESSION_WORKSPACE}  "
        f"/total tokens created {_SESSION_TOTAL_TOKENS:,}"
    )


def _terminal_width() -> int:
    return max(20, int(console.size.width))


def _truncate_middle(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    value = text or ""
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return "." * max_len
    tail_len = max(1, max_len - 3)
    return "..." + value[-tail_len:]


def _fit_cell(text: str, width: int) -> str:
    if width <= 0:
        return ""
    value = (text or "").strip()
    if len(value) <= width:
        return value.ljust(width)
    if width <= 1:
        return value[:width]
    return (value[: width - 1] + "…")


def _next_dynamic_quip() -> Optional[str]:
    if not _DYNAMIC_STATUS_QUIPS:
        return None
    return _DYNAMIC_STATUS_QUIPS.pop(0)


def _next_quip(pool: list[str]) -> str:
    return random.choice(pool)


def _app_version_text() -> str:
    global _APP_VERSION
    if _APP_VERSION:
        return _APP_VERSION
    try:
        _APP_VERSION = importlib_metadata.version("codemaxxx")
    except importlib_metadata.PackageNotFoundError:
        _APP_VERSION = "dev"
    return _APP_VERSION


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

    width = _terminal_width()
    height = max(20, int(console.size.height))
    top_pad = 0 if width < 64 else max(1, min(10, height // 4))
    for _ in range(top_pad):
        console.print()

    logo_text = LOGO if width >= 62 else LOGO_COMPACT
    logo_style = "bold bright_white" if width >= 62 else "bold bright_cyan"
    console.print(Align.center(Text(logo_text, style=logo_style)))
    console.print(Align.center(Text(APP_BRAND, style="bold bright_cyan")))
    console.print()


def _landing_shortcuts_line():
    if _terminal_width() < 58:
        line1 = Text()
        line1.append("tab", style="bold bright_white")
        line1.append(" agents", style="dim")
        line2 = Text()
        line2.append("ctrl+p", style="bold bright_white")
        line2.append(" commands", style="dim")
        console.print(Align.center(line1))
        console.print(Align.center(line2))
        return
    shortcuts = Text()
    shortcuts.append("tab", style="bold bright_white")
    shortcuts.append(" agents    ", style="dim")
    shortcuts.append("ctrl+p", style="bold bright_white")
    shortcuts.append(" commands", style="dim")
    console.print(Align.center(shortcuts))


def _landing_tip_line():
    tip = Text()
    tip.append("● Tip ", style="bold bright_white")
    tip.append("Run ", style="dim")
    tip.append("/models", style="bold bright_white")
    tip.append(" or ", style="dim")
    tip.append("Ctrl+X M", style="bold bright_white")
    tip.append(" to switch available AI models", style="dim")
    console.print(Align.center(tip))


def _landing_version_line():
    width = _terminal_width()
    left = "~"
    right = _app_version_text()
    pad = max(1, width - len(left) - len(right))
    console.print(Text(left + (" " * pad) + right, style="dim"), no_wrap=True, overflow="crop")


def print_prompt_footer():
    """Render session metadata with a 1-line colored full-width separator."""
    width = max(20, _terminal_width() - 1)
    gap = " " * width
    console.print(Text(gap, style="on cyan"), no_wrap=True, overflow="crop")

    workspace_cap = 26 if width < 72 else 46
    workspace = _truncate_middle(_SESSION_WORKSPACE, workspace_cap)

    if width < 66:
        line1 = Text()
        line1.append(f"{_SESSION_APP_NAME} ", style="brand")
        line1.append("/workspace ", style="dim")
        line1.append(workspace, style="assistant")
        line2 = Text()
        line2.append("/total tokens created ", style="dim")
        line2.append(f"{_SESSION_TOTAL_TOKENS:,}", style="brand")
        line2.append(" /kissme ", style="dim")
        line2.append(_format_hms(_SESSION_KISSME_SECONDS), style="assistant")
        console.print(line1)
        console.print(line2)
        return

    line = Text()
    line.append(f"{_SESSION_APP_NAME} ", style="brand")
    line.append("/workspace ", style="dim")
    line.append(workspace, style="assistant")
    line.append(" /total tokens created ", style="dim")
    line.append(f"{_SESSION_TOTAL_TOKENS:,}", style="brand")
    line.append(" /kissme ", style="dim")
    line.append(_format_hms(_SESSION_KISSME_SECONDS), style="assistant")
    console.print(line)


def input_first_prompt() -> str:
    """Render first-prompt clipped box style and collect user input."""
    terminal_w = _terminal_width()
    width = min(96, max(26, terminal_w - 8))
    left_pad = max(0, (terminal_w - width) // 2)
    left = " " * left_pad
    cell_width = max(12, width - 2)
    ask_line = 'Ask anything... "Fix a TODO in the codebase"' if cell_width >= 44 else "Ask anything..."
    automate_line = "AUTOMATE Codemax" if cell_width >= 20 else "AUTOMATE"

    def vrow(text: str = "") -> str:
        clipped = _fit_cell(text, cell_width)
        return f"{left}┃ {clipped}"

    console.print(f"{left}┃")
    console.print(vrow(ask_line))
    console.print(f"{left}┃")
    console.print(vrow(automate_line))
    console.print(f"{left}┃")
    user_input = console.input(f"{left}┃  [green]❯[/green] ").strip()
    console.print(f"{left}╹" + ("▀" * width))
    console.print()
    _landing_shortcuts_line()
    console.print()
    _landing_tip_line()
    console.print()
    _landing_version_line()
    return user_input


def input_main_prompt() -> str:
    """Render main interactive prompt UI after the landing view."""
    terminal_w = _terminal_width()
    width = min(96, max(26, terminal_w - 8))
    left_pad = max(0, (terminal_w - width) // 2)
    left = " " * left_pad
    cell_width = max(12, width - 2)
    ask_line = 'Ask anything... "Fix a TODO in the codebase"' if cell_width >= 44 else "Ask anything..."
    automate_line = "AUTOMATE Codemax" if cell_width >= 20 else "AUTOMATE"

    def vrow(text: str = "") -> str:
        clipped = _fit_cell(text, cell_width)
        return f"{left}┃ {clipped}"

    console.print()
    console.print(f"{left}┃")
    console.print(vrow(ask_line))
    console.print(f"{left}┃")
    console.print(vrow(automate_line))
    console.print(f"{left}┃")
    user_input = console.input(f"{left}┃  [green]❯[/green] ").strip()
    console.print(f"{left}╹" + ("▀" * width))
    print_prompt_footer()
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
    console.print(Text(f"\n ◆ {APP_BRAND}", style="brand"))


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
            title=f"[assistant]{APP_BRAND}[/assistant]",
            border_style="bright_cyan",
            padding=(0, 1),
        )
    )


def print_kissme_entry(
    portal_url: str,
    machine_uid: str = "",
    reason: str = "",
):
    """Render compact KISSME lock component."""
    clear_status()
    finish_stream()

    portal = (portal_url or "").strip() or "auth.eburon.ai"
    body = Text()
    body.append("[ KISS ME ]\n", style="bold bright_magenta")
    body.append("Run ", style="dim")
    body.append("/kissme", style="brand")
    body.append(" or ", style="dim")
    body.append("/connect", style="brand")
    body.append(" to connect.\n", style="dim")
    body.append("Paste token: ", style="dim")
    body.append("/auth <signed-token>\n", style="assistant")
    body.append("Portal: ", style="dim")
    body.append(portal + "\n", style="assistant")
    if machine_uid:
        body.append("Machine UID: ", style="dim")
        body.append(machine_uid + "\n", style="assistant")
    if reason:
        body.append("Reason: ", style="dim")
        body.append(reason, style="error")

    console.print(Panel(body, title="[brand]KISSME[/brand]", border_style="bright_magenta", padding=(0, 1)))


def input_kissme_key(
    portal_url: str,
    machine_uid: str = "",
    reason: str = "",
) -> str:
    """Render KISSME lock component with machine id + connect + key input."""
    clear_status()
    finish_stream()

    portal_raw = (portal_url or "").strip() or "auth.eburon.ai"
    target = portal_raw if portal_raw.startswith(("http://", "https://")) else f"https://{portal_raw}"
    if machine_uid:
        joiner = "&" if "?" in target else "?"
        target = f"{target}{joiner}machine_uid={machine_uid}"

    content = Text()
    content.append("KISSME authentication required\n", style="bold bright_magenta")
    content.append("Generated Machine ID: ", style="dim")
    content.append((machine_uid or "-") + "\n", style="assistant")
    content.append("[ Connect ] ", style="bold bright_magenta")
    content.append("type ", style="dim")
    content.append("connect", style="brand")
    content.append(" or ", style="dim")
    content.append("/kissme", style="brand")
    content.append("\n", style="dim")
    content.append("Open browser (cmd+click): ", style="dim")
    content.append(target + "\n", style="assistant")
    if reason:
        content.append("Status: ", style="dim")
        content.append(reason + "\n", style="error")
    content.append("Paste signed token from portal to continue.\n", style="dim")
    content.append("Do not paste base64(machine_uid).\n", style="dim")
    content.append("input key = ", style="brand")

    console.print(
        Panel(
            content,
            title="[brand]KISSME[/brand]",
            border_style="bright_magenta",
            padding=(0, 1),
        )
    )
    return console.input("[bold bright_magenta]input key[/bold bright_magenta] = ").strip()


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
    commands = [
        ("/help", "Show this help"),
        ("/commands", "Alias for /help"),
        ("/agents", "Alias for /skills"),
        ("/copy-last", "Copy last assistant response to clipboard"),
        ("/copy <text>", "Copy custom text to clipboard"),
        ("/connect", "Alias for /kissme"),
        ("/kissme", "Open KISSME auth portal in browser"),
        ("/auth <signed-token>", "Authenticate and unlock model access"),
        ("/auth-status", "Show current auth lease state"),
        ("/skills", "Show dedicated skill agents and model routing"),
        ("/skills-custom", "Show user-created custom skills"),
        ("/skill-create <name>", "Create/update your own skill interactively"),
        ("/skills-offline", "Show full offline autonomy skill framework"),
        ("/skills-online", "Show 30 online-mode autonomous skills"),
        ("/skills-all", "Show offline + online full skill map"),
        ("/roadmap-online", "Show full 50-skill browser/UI roadmap"),
        ("/roadmap-online-start", "Show required first 8 build skills"),
        ("/roadmap-online-phase <1-7>", "Show one roadmap phase with dependencies"),
        ("/autolearn-now", "Run DB learning pass immediately"),
        ("/personality-save <text>", "Save user personality profile to memory"),
        ("/personality-show", "Show saved personality profile"),
        ("/humor-profile <text>", "Save loading-humor preference profile"),
        ("/humor-profile-show", "Show saved loading-humor profile"),
        ("/workflow", "Show active workflow details"),
        ("/choices", "Show pending numbered options from last assistant output"),
        ("/pick <n>", "Select a pending option and continue execution"),
        ("/clear", "Clear in-memory skill contexts"),
        ("/model <name>", "Set fallback model for skill routing"),
        ("/quit", f"Exit {APP_BRAND}"),
    ]

    if _terminal_width() < 80:
        lines = ["[brand]Commands[/brand]", ""]
        for cmd, desc in commands:
            lines.append(f"[brand]{cmd}[/brand]")
            lines.append(f"[dim]{desc}[/dim]")
        lines.extend(["", "[dim]Ctrl+C[/dim] Cancel current response", "[dim]Ctrl+D[/dim] Exit"])
        console.print(Panel(Text.from_markup("\n".join(lines)), border_style="bright_cyan"))
        return

    help_table = Table.grid(padding=(0, 2))
    for cmd, desc in commands:
        help_table.add_row(f"[brand]{cmd}[/brand]", desc)
    help_table.add_row("", "")
    help_table.add_row("[dim]Ctrl+C[/dim]", "Cancel current response")
    help_table.add_row("[dim]Ctrl+D[/dim]", "Exit")
    console.print(Panel(help_table, title="[brand]Commands[/brand]", border_style="bright_cyan"))

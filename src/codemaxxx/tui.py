"""CodeMaxxx — TUI layout and rendering with Rich."""

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme
from rich.columns import Columns
from rich.table import Table

THEME = Theme({
    "brand": "bold bright_cyan",
    "user": "bold green",
    "assistant": "bold bright_cyan",
    "tool": "bold yellow",
    "error": "bold red",
    "dim": "dim white",
    "success": "bold green",
})

LOGO = r"""
   ██████╗ ██████╗ ██████╗ ███████╗███╗   ███╗ █████╗ ██╗  ██╗██╗  ██╗██╗  ██╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝████╗ ████║██╔══██╗╚██╗██╔╝╚██╗██╔╝╚██╗██╔╝
  ██║     ██║   ██║██║  ██║█████╗  ██╔████╔██║███████║ ╚███╔╝  ╚███╔╝  ╚███╔╝
  ██║     ██║   ██║██║  ██║██╔══╝  ██║╚██╔╝██║██╔══██║ ██╔██╗  ██╔██╗  ██╔██╗
  ╚██████╗╚██████╔╝██████╔╝███████╗██║ ╚═╝ ██║██║  ██║██╔╝ ██╗██╔╝ ██╗██╔╝ ██╗
   ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
"""

console = Console(theme=THEME)


def print_header(model: str, host: str):
    """Print the branded header."""
    console.print()
    console.print(Text(LOGO, style="brand"))
    info_table = Table.grid(padding=(0, 2))
    info_table.add_row(
        Text("Model", style="dim"),
        Text(model, style="brand"),
    )
    info_table.add_row(
        Text("Host", style="dim"),
        Text(host, style="brand"),
    )
    info_table.add_row(
        Text("Help", style="dim"),
        Text("/help  •  /clear  •  /quit", style="dim"),
    )
    console.print(Panel(info_table, title="[brand]CodeMaxxx[/brand]", border_style="bright_cyan", padding=(0, 2)))
    console.print()


def print_user_msg(msg: str):
    """Print a user message."""
    console.print(Panel(
        Text(msg),
        title="[user]You[/user]",
        border_style="green",
        padding=(0, 1),
    ))


def print_assistant_start():
    """Print assistant header."""
    console.print(Text("\n ◆ CodeMaxxx", style="brand"))


def print_streamed_chunk(chunk: str):
    """Print a streamed chunk (raw, no newline)."""
    console.print(chunk, end="", highlight=False)


def print_assistant_md(content: str):
    """Print final assistant response as rendered markdown."""
    console.print()
    console.print(Panel(
        Markdown(content),
        title="[assistant]CodeMaxxx[/assistant]",
        border_style="bright_cyan",
        padding=(0, 1),
    ))


def print_tool_call(name: str, args: dict):
    """Print a tool invocation."""
    args_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
    console.print(Panel(
        Text(f"{name}({args_str})", style="yellow"),
        title="[tool]⚡ Tool Call[/tool]",
        border_style="yellow",
        padding=(0, 1),
    ))


def print_tool_result(result):
    """Print a tool result."""
    style = "success" if result.success else "error"
    console.print(Panel(
        Text(result.output[:2000]),
        title=f"[{style}]Tool Result[/{style}]",
        border_style="green" if result.success else "red",
        padding=(0, 1),
    ))


def print_error(msg: str):
    """Print an error."""
    console.print(f"  [error]✖ {msg}[/error]")


def print_info(msg: str):
    """Print info."""
    console.print(f"  [dim]{msg}[/dim]")


def print_help():
    """Print help."""
    help_table = Table.grid(padding=(0, 2))
    help_table.add_row("[brand]/help[/brand]", "Show this help")
    help_table.add_row("[brand]/clear[/brand]", "Clear conversation history")
    help_table.add_row("[brand]/model <name>[/brand]", "Switch model")
    help_table.add_row("[brand]/quit[/brand]", "Exit CodeMaxxx")
    help_table.add_row("[brand]/reset[/brand]", "Reset conversation")
    help_table.add_row("", "")
    help_table.add_row("[dim]Ctrl+C[/dim]", "Cancel current response")
    help_table.add_row("[dim]Ctrl+D[/dim]", "Exit")
    console.print(Panel(help_table, title="[brand]Commands[/brand]", border_style="bright_cyan"))

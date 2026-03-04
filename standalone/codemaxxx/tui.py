"""CodeMaxxx — Full TUI with prompt_toolkit + Rich."""

import asyncio
import os
import time
from datetime import datetime
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

from .config import LOGO, LOGO_SMALL, APP_NAME, VERSION, BRAND_COLOR, DEFAULT_MODEL, DEFAULT_HOST
from .agent import Agent
from .db import Database


# ── Prompt Toolkit Style ──────────────────────────────────────────
PT_STYLE = Style.from_dict({
    "prompt": "ansibrightcyan bold",
    "input": "ansiwhite",
})


class TUI:
    """Full terminal UI for CodeMaxxx."""

    def __init__(self, model: str, host: str, cwd: str, auto_approve: bool = False):
        self.console = Console()
        self.model = model
        self.host = host
        self.cwd = os.path.abspath(cwd)
        self.auto_approve = auto_approve
        self.agent: Optional[Agent] = None
        self.message_count = 0
        self.start_time = time.time()
        self._stream_buffer: list[str] = []
        self._prompt_session = PromptSession(
            history=InMemoryHistory(),
            style=PT_STYLE,
        )

    # ── Rendering ─────────────────────────────────────────────────

    def render_header(self):
        self.console.print()
        self.console.print(Text(LOGO, style=f"bold {BRAND_COLOR}"))

        info = Table.grid(padding=(0, 2))
        info.add_row(Text("Model", style="dim"), Text(self.model, style=f"bold {BRAND_COLOR}"))
        info.add_row(Text("Host", style="dim"), Text(self.host, style=f"bold {BRAND_COLOR}"))
        info.add_row(Text("Dir", style="dim"), Text(self.cwd, style="bold white"))
        info.add_row(Text("Mode", style="dim"), Text("autonomous" if self.auto_approve else "interactive", style="bold yellow" if self.auto_approve else f"bold {BRAND_COLOR}"))
        info.add_row(Text("Help", style="dim"), Text("/help  •  /clear  •  /auto  •  /quit", style="dim"))

        self.console.print(Panel(
            info,
            title=f"[bold {BRAND_COLOR}]{APP_NAME} v{VERSION}[/bold {BRAND_COLOR}]",
            border_style=BRAND_COLOR,
            padding=(0, 2),
        ))
        self.console.print()

    def render_user(self, msg: str):
        self.console.print(Panel(
            Text(msg),
            title="[bold green]You[/bold green]",
            border_style="green",
            padding=(0, 1),
        ))

    def render_assistant_start(self):
        self.console.print(Text(f"\n {LOGO_SMALL}", style=f"bold {BRAND_COLOR}"))

    def render_stream_chunk(self, chunk: str):
        self._stream_buffer.append(chunk)
        self.console.print(chunk, end="", highlight=False)

    def render_assistant_end(self):
        full = "".join(self._stream_buffer)
        self._stream_buffer.clear()
        self.console.print()

        # Strip tool blocks for display
        import re
        clean = re.sub(r"```tool\s*\n.*?\n```", "", full, flags=re.DOTALL).strip()
        if clean:
            self.console.print(Panel(
                Markdown(clean),
                title=f"[bold {BRAND_COLOR}]{APP_NAME}[/bold {BRAND_COLOR}]",
                border_style=BRAND_COLOR,
                padding=(0, 1),
            ))

    def render_tool_call(self, name: str, args: dict):
        args_str = ", ".join(f"{k}={repr(v)[:80]}" for k, v in args.items())
        self.console.print(Panel(
            Text(f"{name}({args_str})", style="yellow"),
            title="[bold yellow]⚡ Tool[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        ))

    def render_tool_result(self, result):
        style = "green" if result.success else "red"
        title = f"[bold {style}]{'✔' if result.success else '✖'} {result.tool}[/bold {style}]"
        output = result.output[:3000]
        self.console.print(Panel(
            Text(output),
            title=title,
            border_style=style,
            padding=(0, 1),
        ))

    def render_status(self, status: str):
        icons = {"thinking": "🤔", "error": "❌", "done": "✅"}
        icon = icons.get(status, "⚙️")
        if status.startswith("running"):
            icon = "⚡"
        self.console.print(f"  [dim]{icon} {status}...[/dim]")

    def render_help(self):
        tbl = Table.grid(padding=(0, 2))
        tbl.add_row(f"[{BRAND_COLOR}]/help[/{BRAND_COLOR}]", "Show commands")
        tbl.add_row(f"[{BRAND_COLOR}]/clear[/{BRAND_COLOR}]", "Clear conversation")
        tbl.add_row(f"[{BRAND_COLOR}]/model <name>[/{BRAND_COLOR}]", "Switch model")
        tbl.add_row(f"[{BRAND_COLOR}]/auto[/{BRAND_COLOR}]", "Toggle autonomous mode")
        tbl.add_row(f"[{BRAND_COLOR}]/memory[/{BRAND_COLOR}]", "Show long-term memory")
        tbl.add_row(f"[{BRAND_COLOR}]/quit[/{BRAND_COLOR}]", "Exit")
        tbl.add_row("", "")
        tbl.add_row("[dim]Ctrl+C[/dim]", "Cancel response")
        tbl.add_row("[dim]Ctrl+D[/dim]", "Exit")
        self.console.print(Panel(tbl, title=f"[bold {BRAND_COLOR}]Commands[/bold {BRAND_COLOR}]", border_style=BRAND_COLOR))

    def render_memory(self):
        if not self.agent or not self.agent.db.connected:
            self.console.print("  [dim]Database offline[/dim]")
            return
        memories = self.agent.db.read_memory()
        if not memories:
            self.console.print("  [dim]No memories stored.[/dim]")
            return
        tbl = Table(title="Long-term Memory", border_style=BRAND_COLOR)
        tbl.add_column("Key", style="bold")
        tbl.add_column("Value")
        tbl.add_column("Updated", style="dim")
        for m in memories:
            tbl.add_row(m["key"], m["value"][:80], str(m["updated_at"])[:19])
        self.console.print(tbl)

    def render_status_bar(self):
        elapsed = int(time.time() - self.start_time)
        mins = elapsed // 60
        secs = elapsed % 60
        bar = f"  [dim]msgs: {self.message_count}  •  session: {mins}m{secs:02d}s  •  dir: {os.path.basename(self.cwd)}[/dim]"
        self.console.print(bar)

    # ── Tool Approval ─────────────────────────────────────────────

    async def confirm_tool(self, name: str, args: dict) -> bool:
        args_preview = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
        self.console.print(f"\n  [yellow]⚠ Approve [bold]{name}[/bold]({args_preview})?[/yellow]")
        try:
            answer = await self._prompt_session.prompt_async(
                HTML("<b>[y/n]</b> ❯ "),
            )
            answer = answer.strip().lower()
            return answer in ("y", "yes", "")
        except (EOFError, KeyboardInterrupt):
            return False

    # ── Main Loop ─────────────────────────────────────────────────

    async def run(self):
        self.agent = Agent(
            model=self.model,
            host=self.host,
            cwd=self.cwd,
            auto_approve=self.auto_approve,
            on_stream=self.render_stream_chunk,
            on_tool_call=self.render_tool_call,
            on_tool_result=self.render_tool_result,
            on_status=self.render_status,
            on_done=self.render_assistant_end,
            confirm_tool=self.confirm_tool if not self.auto_approve else None,
        )

        # Init database
        db_ok = self.agent.init_db()
        if db_ok:
            self.console.print(f"  [dim]🧠 Memory connected (machine: {self.agent.db.machine_uid[:8]}...)[/dim]")
        else:
            self.console.print("  [dim]💾 Memory offline — conversations not persisted[/dim]")

        self.render_header()

        while True:
            try:
                self.render_status_bar()
                user_input = await self._prompt_session.prompt_async(
                    HTML(f"<style fg='ansibrightcyan' bg='' bold='true'>❯</style> "),
                )
                user_input = user_input.strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            # Slash commands
            if user_input.startswith("/"):
                cmd = user_input.lower().split()[0]
                if cmd in ("/quit", "/exit", "/q"):
                    self.console.print("[dim]Goodbye![/dim]")
                    break
                elif cmd == "/help":
                    self.render_help()
                    continue
                elif cmd in ("/clear", "/reset"):
                    self.agent.reset()
                    self.console.clear()
                    self.render_header()
                    self.console.print("  [dim]Conversation cleared.[/dim]")
                    continue
                elif cmd == "/model":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) > 1:
                        self.model = parts[1].strip()
                        self.agent.client.model = self.model
                        self.agent.model = self.model
                        self.console.print(f"  [dim]Switched to: {self.model}[/dim]")
                    else:
                        self.console.print(f"  [dim]Current: {self.model}[/dim]")
                    continue
                elif cmd == "/auto":
                    self.auto_approve = not self.auto_approve
                    self.agent.auto_approve = self.auto_approve
                    self.agent._confirm_tool = None if self.auto_approve else self.confirm_tool
                    mode = "autonomous ⚡" if self.auto_approve else "interactive 🛡️"
                    self.console.print(f"  [dim]Mode: {mode}[/dim]")
                    continue
                elif cmd == "/memory":
                    self.render_memory()
                    continue
                else:
                    self.console.print(f"  [red]Unknown: {cmd}[/red]")
                    continue

            self.message_count += 1
            self.render_user(user_input)
            self.render_assistant_start()

            try:
                await self.agent.run(user_input)
            except KeyboardInterrupt:
                self.console.print("\n[dim]Cancelled.[/dim]")
                continue

        # Cleanup
        if self.agent:
            self.agent.close()

"""CodeMaxxx — Agent loop: user input → LLM → tool calls → display."""

import asyncio
import json
import re
import uuid
from typing import Optional

from .ollama_client import OllamaClient
from .tools import execute_tool, ToolResult
from .database import Database
from . import tui

TOOL_BLOCK_RE = re.compile(r"```tool\s*\n(.*?)\n```", re.DOTALL)
MAX_TOOL_ROUNDS = 10


async def process_response(client: OllamaClient, user_msg: str, db: Optional[Database] = None, session_id: str = ""):
    """Stream a response and handle tool calls in a loop."""
    tui.print_user_msg(user_msg)

    # Save user message to DB
    if db and db.connected:
        db.save_message(session_id, "user", user_msg, client.model)

    for round_num in range(MAX_TOOL_ROUNDS):
        tui.print_assistant_start()

        # Stream the response
        full_response = []
        try:
            async for chunk in client.chat_stream(
                user_msg if round_num == 0 else _tool_context_msg(full_response)
            ):
                full_response.append(chunk)
                tui.print_streamed_chunk(chunk)
        except Exception as e:
            tui.console.print()
            tui.print_error(f"Ollama error: {e}")
            return

        response_text = "".join(full_response)
        tui.console.print()  # newline after stream

        # Save assistant response to DB
        if db and db.connected:
            db.save_message(session_id, "assistant", response_text, client.model)

        # Render final markdown
        # Check for tool calls
        tool_matches = TOOL_BLOCK_RE.findall(response_text)
        if not tool_matches:
            # No tool calls — we're done
            tui.print_assistant_md(
                TOOL_BLOCK_RE.sub("", response_text).strip() or response_text
            )
            return

        # Execute tool calls
        tool_outputs = []
        for match in tool_matches:
            try:
                call = json.loads(match)
                name = call.get("tool", "")
                args = call.get("args", {})
                tui.print_tool_call(name, args)
                result = execute_tool(name, args, db=db)
                tui.print_tool_result(result)
                tool_outputs.append(
                    f"Tool `{name}` result:\n{result.output}"
                )
            except json.JSONDecodeError as e:
                tui.print_error(f"Invalid tool JSON: {e}")
                tool_outputs.append(f"Error parsing tool call: {e}")

        # Feed tool results back to the model
        tool_feedback = "\n\n".join(tool_outputs)
        client.add_message("user", f"[Tool results]\n{tool_feedback}")

        # Continue the loop for next LLM response
        user_msg = ""  # Subsequent rounds use tool context

    tui.print_info("Max tool rounds reached.")


def _tool_context_msg(prev_chunks: list) -> str:
    """Build a follow-up message after tool execution."""
    return "Continue based on the tool results above."


async def run_agent(model: str, host: str):
    """Main agent REPL loop."""
    client = OllamaClient(model=model, host=host)
    session_id = uuid.uuid4().hex[:12]

    # Initialize PostgreSQL long-term memory
    db = Database()
    if db.connect():
        tui.print_info(f"🧠 Memory connected (machine: {db.machine_uid[:8]}...)")
        # Load recent memory into system context
        memories = db.read_memory()
        if memories:
            mem_context = "\n".join(f"- {m['key']}: {m['value']}" for m in memories)
            client.messages.append({
                "role": "system",
                "content": f"[Long-term memory for this machine]\n{mem_context}"
            })
    else:
        tui.print_info("💾 Memory offline (PostgreSQL not available — conversations not persisted)")

    tui.print_header(model, host)

    while True:
        try:
            tui.console.print()
            user_input = tui.console.input("[green]❯[/green] ").strip()
        except (EOFError, KeyboardInterrupt):
            tui.console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]
            if cmd in ("/quit", "/exit", "/q"):
                tui.console.print("[dim]Goodbye![/dim]")
                break
            elif cmd == "/help":
                tui.print_help()
                continue
            elif cmd in ("/clear", "/reset"):
                client.reset()
                tui.console.clear()
                tui.print_header(model, host)
                tui.print_info("Conversation cleared.")
                continue
            elif cmd == "/model":
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    client.model = parts[1].strip()
                    model = client.model
                    tui.print_info(f"Switched to model: {model}")
                else:
                    tui.print_info(f"Current model: {model}")
                continue
            else:
                tui.print_error(f"Unknown command: {cmd}")
                continue

        # Process with agent
        try:
            await process_response(client, user_input, db=db, session_id=session_id)
        except KeyboardInterrupt:
            tui.console.print("\n[dim]Response cancelled.[/dim]")
            continue

    # Cleanup
    if db:
        db.close()

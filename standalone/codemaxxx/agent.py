"""CodeMaxxx — Autonomous agent loop with multi-step tool execution."""

import asyncio
import json
import re
import uuid
from typing import Optional

from .llm import OllamaClient
from .tools import execute_tool, ToolResult
from .db import Database

TOOL_RE = re.compile(r"```tool\s*\n(.*?)\n```", re.DOTALL)
MAX_ROUNDS = 15


class Agent:
    """Autonomous coding agent that plans and executes tasks."""

    def __init__(
        self,
        model: str,
        host: str,
        cwd: str = ".",
        auto_approve: bool = False,
        on_stream=None,
        on_tool_call=None,
        on_tool_result=None,
        on_status=None,
        on_done=None,
        confirm_tool=None,
    ):
        self.client = OllamaClient(model=model, host=host)
        self.db = Database()
        self.session_id = uuid.uuid4().hex[:12]
        self.cwd = cwd
        self.auto_approve = auto_approve
        self.model = model
        self.is_running = False

        # Callbacks for TUI
        self._on_stream = on_stream or (lambda c: None)
        self._on_tool_call = on_tool_call or (lambda n, a: None)
        self._on_tool_result = on_tool_result or (lambda r: None)
        self._on_status = on_status or (lambda s: None)
        self._on_done = on_done or (lambda: None)
        self._confirm_tool = confirm_tool  # async callable returning bool

    def init_db(self) -> bool:
        ok = self.db.connect()
        if ok:
            memories = self.db.read_memory()
            if memories:
                ctx = "\n".join(f"- {m['key']}: {m['value']}" for m in memories)
                self.client.inject_context(f"[Long-term memory]\n{ctx}")
        return ok

    def _save(self, role: str, content: str):
        if self.db.connected:
            self.db.save_message(self.session_id, role, content, self.model)

    async def run(self, user_msg: str):
        """Process user message through the agent loop."""
        self.is_running = True
        self._save("user", user_msg)
        self._on_status("thinking")

        current_input = user_msg

        for round_num in range(MAX_ROUNDS):
            # Stream response
            full_response = []
            try:
                async for chunk in self.client.stream(current_input if round_num == 0 else current_input):
                    full_response.append(chunk)
                    self._on_stream(chunk)
            except Exception as e:
                self._on_status("error")
                self._on_stream(f"\n❌ Error: {e}")
                break

            response_text = "".join(full_response)
            self._save("assistant", response_text)

            # Parse tool calls
            tool_matches = TOOL_RE.findall(response_text)
            if not tool_matches:
                self._on_done()
                break

            # Execute tools
            tool_outputs = []
            task_done = False

            for match in tool_matches:
                try:
                    call = json.loads(match)
                    name = call.get("tool", "")
                    args = call.get("args", {})

                    # Check for done signal
                    if name == "done":
                        result = execute_tool(name, args, db=self.db, cwd=self.cwd, model=self.model)
                        self._on_tool_result(result)
                        task_done = True
                        break

                    self._on_tool_call(name, args)
                    self._on_status(f"running {name}")

                    # Approval gate for destructive tools
                    if not self.auto_approve and name in ("write_file", "edit_file", "shell", "git"):
                        if self._confirm_tool:
                            approved = await self._confirm_tool(name, args)
                            if not approved:
                                tool_outputs.append(f"Tool `{name}` was denied by user.")
                                self._on_tool_result(ToolResult(False, "⛔ Denied by user", name))
                                continue

                    result = execute_tool(name, args, db=self.db, cwd=self.cwd, model=self.model)
                    self._on_tool_result(result)
                    tool_outputs.append(f"Tool `{name}` result:\n{result.output}")

                except json.JSONDecodeError as e:
                    tool_outputs.append(f"Invalid tool JSON: {e}")

            if task_done:
                self._on_done()
                break

            if not tool_outputs:
                self._on_done()
                break

            # Feed results back
            feedback = "\n\n".join(tool_outputs)
            current_input = f"[Tool results]\n{feedback}\n\nContinue with the next step."
            self.client.add_message("user", current_input)
            self._save("tool_results", feedback)
            self._on_status("thinking")

        self.is_running = False

    def reset(self):
        self.client.reset()
        self.session_id = uuid.uuid4().hex[:12]

    def close(self):
        self.db.close()

"""CodeMaxxx — Ollama streaming chat client."""

import json
import os
from typing import AsyncIterator, Optional

import httpx

DEFAULT_MODEL = "eburonmax/codemax-v3:latest"
DEFAULT_HOST = "http://localhost:11434"
MEMORY_WRITE_KEY = os.environ.get("CODEMAXXX_MEMORY_WRITE_KEY", "MyMasterDontAllowMe")

SYSTEM_PROMPT = f"""\
You are CodeMaxxx, an autonomous AI coding assistant running in the terminal.
You can plan and execute work using specialized skill agents and tools.

When you need to use a tool, respond with a JSON block:
```tool
{{"tool": "<tool_name>", "args": {{<arguments>}}}}
```

Available tools:
- read_file: {{"path": "<filepath>"}}
- write_file: {{"path": "<filepath>", "content": "<content>"}}
- edit_file: {{"path": "<filepath>", "old": "<old_text>", "new": "<new_text>"}}
- list_dir: {{"path": "<optional_dir>"}}
- glob: {{"pattern": "<glob_pattern>"}}
- grep: {{"pattern": "<regex>", "path": "<optional_dir>"}}
- shell: {{"cmd": "<command>"}}
- git: {{"cmd": "<git_subcommand_without_git_prefix_or_with_it>"}}
- recall_memory: {{"key": "<optional_key>"}}
- store_memory: {{"key": "<key>", "value": "<value>", "write_key": "{MEMORY_WRITE_KEY}"}}
- forget_memory: {{"key": "<key>", "write_key": "{MEMORY_WRITE_KEY}"}}

Be concise, direct, and precise.
"""


class OllamaClient:
    """Streaming client for Ollama /api/chat."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.system_prompt = system_prompt
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]
        self.last_eval_count: int = 0

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    async def chat_stream(self, user_msg: str) -> AsyncIterator[str]:
        """Send a message and yield streamed response chunks."""
        self.add_message("user", user_msg)
        self.last_eval_count = 0

        payload = {
            "model": self.model,
            "messages": self.messages,
            "stream": True,
        }

        full_response = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream(
                "POST", f"{self.host}/api/chat", json=payload
            ) as resp:
                if resp.status_code == 404:
                    raise Exception(f"Model '{self.model}' not found. Run: ollama pull {self.model}")
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if data.get("error"):
                        raise Exception(str(data.get("error")))

                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        full_response.append(chunk)
                        yield chunk
                    if data.get("done"):
                        eval_count = data.get("eval_count")
                        try:
                            self.last_eval_count = max(0, int(eval_count))
                        except (TypeError, ValueError):
                            self.last_eval_count = 0
                        break

        self.add_message("assistant", "".join(full_response))

    async def chat(self, user_msg: str) -> str:
        """Non-streaming helper: return full response."""
        parts = []
        async for chunk in self.chat_stream(user_msg):
            parts.append(chunk)
        return "".join(parts)

    def reset(self, system_prompt: Optional[str] = None):
        """Clear conversation history and optionally replace system prompt."""
        if system_prompt is not None:
            self.system_prompt = system_prompt
        self.messages = [{"role": "system", "content": self.system_prompt}]

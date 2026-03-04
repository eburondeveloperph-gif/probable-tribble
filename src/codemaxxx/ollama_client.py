"""CodeMaxxx — Ollama streaming chat client."""

import json
from typing import AsyncIterator

import httpx

DEFAULT_MODEL = "eburonmax/codemax-v3"
DEFAULT_HOST = "http://localhost:11434"

SYSTEM_PROMPT = """\
You are CodeMaxxx, an expert AI coding assistant running in the terminal.
You help users read, write, edit, and debug code. You can execute shell commands and manage files.

When you need to use a tool, respond with a JSON block:
```tool
{"tool": "<tool_name>", "args": {<arguments>}}
```

Available tools:
- read_file: {"path": "<filepath>"} — Read file contents
- write_file: {"path": "<filepath>", "content": "<content>"} — Write/create a file
- edit_file: {"path": "<filepath>", "old": "<old_text>", "new": "<new_text>"} — Replace text in a file
- shell: {"cmd": "<command>"} — Execute a shell command
- recall_memory: {"key": "<optional_key>"} — Read from your long-term memory (omit key to list all)
- store_memory: {"key": "<key>", "value": "<value>", "write_key": "MyMasterDontAllowMe"} — Store to long-term memory (you MUST include the exact write_key)
- forget_memory: {"key": "<key>", "write_key": "MyMasterDontAllowMe"} — Delete a memory entry

You have long-term memory stored in PostgreSQL. Use store_memory to remember important facts about the user, project preferences, or context across sessions. Use recall_memory to retrieve them.
Your write_key for memory operations is: MyMasterDontAllowMe — always include it when storing or deleting memory.

When not using tools, respond with helpful explanations and code.
Be concise, direct, and precise. Show code changes as minimal diffs when possible.\
"""


class OllamaClient:
    """Streaming client for Ollama /api/chat."""

    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST):
        self.model = model
        self.host = host.rstrip("/")
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    async def chat_stream(self, user_msg: str) -> AsyncIterator[str]:
        """Send a message and yield streamed response chunks."""
        self.add_message("user", user_msg)

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
                    body = await resp.aread()
                    raise Exception(f"Model '{self.model}' not found. Run: ollama pull {self.model}")
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        full_response.append(chunk)
                        yield chunk
                    if data.get("done"):
                        break

        self.add_message("assistant", "".join(full_response))

    async def chat(self, user_msg: str) -> str:
        """Non-streaming: return full response."""
        parts = []
        async for chunk in self.chat_stream(user_msg):
            parts.append(chunk)
        return "".join(parts)

    def reset(self):
        """Clear conversation history."""
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

"""CodeMaxxx — Streaming Ollama client."""

import json
from typing import AsyncIterator
import httpx
from .config import DEFAULT_MODEL, DEFAULT_HOST, SYSTEM_PROMPT


class OllamaClient:
    """Async streaming client for Ollama /api/chat."""

    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST):
        self.model = model
        self.host = host.rstrip("/")
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def inject_context(self, content: str):
        self.messages.append({"role": "system", "content": content})

    async def stream(self, user_msg: str) -> AsyncIterator[str]:
        self.add_message("user", user_msg)
        payload = {"model": self.model, "messages": self.messages, "stream": True}
        full = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream("POST", f"{self.host}/api/chat", json=payload) as resp:
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
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        full.append(chunk)
                        yield chunk
                    if data.get("done"):
                        break
        self.add_message("assistant", "".join(full))

    async def complete(self, user_msg: str) -> str:
        parts = []
        async for chunk in self.stream(user_msg):
            parts.append(chunk)
        return "".join(parts)

    def reset(self):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

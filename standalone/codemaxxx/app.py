"""CodeMaxxx — CLI entrypoint."""

import argparse
import asyncio
import os
import sys

from .config import DEFAULT_MODEL, DEFAULT_HOST, APP_NAME, VERSION
from .tui import TUI


def main():
    parser = argparse.ArgumentParser(
        prog="codemaxxx",
        description=f"{APP_NAME} v{VERSION} — Autonomous AI coding agent for the terminal",
    )
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Ollama server (default: {DEFAULT_HOST})")
    parser.add_argument("-d", "--dir", default=".", help="Project directory (default: cwd)")
    parser.add_argument("--auto", action="store_true", help="Autonomous mode (auto-approve tool calls)")
    parser.add_argument("-v", "--version", action="version", version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args()

    cwd = os.path.abspath(args.dir)
    if not os.path.isdir(cwd):
        print(f"❌ Directory not found: {cwd}")
        sys.exit(1)

    tui = TUI(model=args.model, host=args.host, cwd=cwd, auto_approve=args.auto)

    try:
        asyncio.run(tui.run())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()

"""CodeMaxxx — CLI entrypoint."""

import argparse
import asyncio
import os
import sys

from .agent import run_agent
from .ollama_client import DEFAULT_MODEL, DEFAULT_HOST


def main():
    parser = argparse.ArgumentParser(
        prog="codemax",
        description="CodeMaxxx — AI coding agent for the terminal",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=DEFAULT_MODEL,
        help=f"Fallback Ollama model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Ollama server URL (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "-d",
        "--dir",
        default=".",
        help="Workspace directory for tools (default: current directory)",
    )
    parser.add_argument(
        "--workflow",
        default="manus",
        choices=["manus"],
        help="Autonomous workflow engine (default: manus)",
    )
    args = parser.parse_args()

    cwd = os.path.abspath(os.path.expanduser(args.dir))
    if not os.path.isdir(cwd):
        print(f"Directory not found: {cwd}")
        sys.exit(1)

    try:
        asyncio.run(
            run_agent(
                model=args.model,
                host=args.host,
                cwd=cwd,
                workflow=args.workflow,
            )
        )
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()

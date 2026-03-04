"""CodeMaxxx — CLI entrypoint."""

import argparse
import asyncio
import sys

from .agent import run_agent
from .ollama_client import DEFAULT_MODEL, DEFAULT_HOST


def main():
    parser = argparse.ArgumentParser(
        prog="codemaxxx-tui",
        description="CodeMaxxx — AI coding agent for the terminal",
    )
    parser.add_argument(
        "-m", "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Ollama server URL (default: {DEFAULT_HOST})",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_agent(model=args.model, host=args.host))
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()

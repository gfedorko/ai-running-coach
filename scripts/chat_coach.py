"""CLI chatbot over the bounded local training-coach tools."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Chat with the local training coach.")
    parser.add_argument("--ask", help="One-shot question for the coach.")
    return parser


def main() -> None:
    """Run one-shot or interactive bounded coach chat."""

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from coach.chat_tools import answer_chat_query, supported_actions_text

    args = build_parser().parse_args()
    if args.ask:
        print(answer_chat_query(repo_root, args.ask))
        return

    print("Training Coach Chat")
    print(supported_actions_text())
    print("Type 'exit' to quit.")

    while True:
        try:
            query = input("> ").strip()
        except EOFError:
            break
        if query.lower() in {"exit", "quit"}:
            break
        print(answer_chat_query(repo_root, query))
        print("")


if __name__ == "__main__":
    main()

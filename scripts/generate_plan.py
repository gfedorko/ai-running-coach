"""Generate a DB-backed next workout or 7-day plan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Generate the next workout or a 7-day plan.")
    parser.add_argument("--mode", choices=("next", "weekly"), default="next")
    parser.add_argument("--target-date", help="Target date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def main() -> None:
    """Generate and persist a deterministic recommendation."""

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from coach.training_planner import generate_plan
    from coach.render import render_json, render_plan_markdown

    args = build_parser().parse_args()
    payload = generate_plan(
        repo_root,
        mode=args.mode,
        target_date=args.target_date,
        persist=True,
    )

    if args.format == "json":
        print(render_json(payload))
    else:
        print(render_plan_markdown(payload))


if __name__ == "__main__":
    main()

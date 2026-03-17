"""CLI entry point for syncing athlete state from Intervals.icu."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Sync Intervals.icu data into local history.")
    parser.add_argument(
        "--mode",
        choices=("incremental", "backfill"),
        default="incremental",
        help="Use incremental sync by default, or request a full backfill.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Choose markdown or JSON output.",
    )
    return parser


def main() -> None:
    """Sync Intervals.icu data into the local analytics store."""

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from coach.intervals import IntervalsSyncError, sync_repo_state
    from coach.render import render_json, render_sync_markdown

    args = build_parser().parse_args()

    try:
        result = sync_repo_state(repo_root, mode=args.mode)
    except IntervalsSyncError as exc:
        print(f"Intervals sync failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    payload = result.to_dict()
    if args.format == "json":
        print(render_json(payload))
    else:
        print(render_sync_markdown(payload))


if __name__ == "__main__":
    main()

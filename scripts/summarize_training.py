"""Summarize recent training from the normalized SQLite history."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Summarize recent training history.")
    parser.add_argument("--days", type=int, default=14, help="Rolling window size in days.")
    parser.add_argument("--start", help="Explicit window start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="Explicit window end date (YYYY-MM-DD).")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def resolve_window(args) -> tuple[str, str]:
    """Resolve the requested date window."""

    if args.start and args.end:
        return args.start, args.end

    end_date = args.end or datetime.now().astimezone().date().isoformat()
    end_day = datetime.fromisoformat(f"{end_date}T00:00:00").date()
    start_day = end_day - timedelta(days=args.days - 1)
    return args.start or start_day.isoformat(), end_day.isoformat()


def main() -> None:
    """Render a recent training summary."""

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from coach.data_paths import resolve_runtime_paths
    from coach.metrics import build_training_summary
    from coach.render import render_json, render_training_summary_markdown
    from coach.storage import connect_database, fetch_activities, fetch_latest_daily_metric

    args = build_parser().parse_args()
    start_date, end_date = resolve_window(args)

    with connect_database(resolve_runtime_paths(repo_root).training_db) as connection:
        activities = [dict(row) for row in fetch_activities(connection, start_date=start_date, end_date=end_date)]
        metric = fetch_latest_daily_metric(connection, end_date)
        summary = build_training_summary(
            dict(metric) if metric is not None else None,
            activities,
            start_date=start_date,
            end_date=end_date,
        )

    if args.format == "json":
        print(render_json(summary))
    else:
        print(render_training_summary_markdown(summary))


if __name__ == "__main__":
    main()

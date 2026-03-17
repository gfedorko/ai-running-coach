"""Analyze recent workout sessions from normalized local history."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Analyze recent workouts.")
    parser.add_argument("--days", type=int, default=14, help="Rolling window size in days.")
    parser.add_argument("--start", help="Explicit window start date (YYYY-MM-DD).")
    parser.add_argument("--end", help="Explicit window end date (YYYY-MM-DD).")
    parser.add_argument("--limit", type=int, help="Analyze the last N runs instead of a date window.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def resolve_window(args) -> tuple[str | None, str | None]:
    """Resolve the requested analysis window."""

    if args.start and args.end:
        return args.start, args.end
    if args.start or args.end:
        raise SystemExit("--start and --end must be used together.")
    return None, None


def main() -> None:
    """Render session-level recent workout analysis."""

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from coach.data_paths import resolve_runtime_paths
    from coach.metrics import analyze_workouts
    from coach.render import render_json, render_workout_analysis_markdown
    from coach.storage import connect_database, fetch_activities, fetch_daily_metrics_between

    args = build_parser().parse_args()
    start_date, end_date = resolve_window(args)

    with connect_database(resolve_runtime_paths(repo_root).training_db) as connection:
        if args.limit is not None:
            activities = [dict(row) for row in fetch_activities(connection, limit=args.limit)]
            if activities:
                end_date = activities[0]["activity_date"]
                start_date = activities[-1]["activity_date"]
            else:
                end_date = datetime.now().astimezone().date().isoformat()
                start_date = (datetime.now().astimezone().date() - timedelta(days=args.days - 1)).isoformat()
        elif start_date is None or end_date is None:
            end_date = datetime.now().astimezone().date().isoformat()
            start_date = (datetime.now().astimezone().date() - timedelta(days=args.days - 1)).isoformat()
            activities = [dict(row) for row in fetch_activities(connection, start_date=start_date, end_date=end_date)]
        else:
            activities = [dict(row) for row in fetch_activities(connection, start_date=start_date, end_date=end_date)]

        metrics_by_date = {
            row["local_date"]: dict(row)
            for row in fetch_daily_metrics_between(connection, start_date, end_date)
        }
        analysis = analyze_workouts(activities, metrics_by_date)

    if args.format == "json":
        print(render_json(analysis))
    else:
        print(render_workout_analysis_markdown(analysis))


if __name__ == "__main__":
    main()

"""CLI entry point for generating a weekly plan, FIT exports, and Intervals push."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coach.chat_tools import render_intervals_push_lines
from coach.fit_export import build_plan_fit_bundle, write_plan_fit_bundle
from coach.intervals import push_weekly_plan_to_intervals
from coach.planner import generate_plan, render_week_markdown, weekly_plan_from_payload


def parse_args() -> argparse.Namespace:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Build the weekly plan, FIT exports, and Intervals push.")
    parser.add_argument(
        "--week-of",
        help="Any date within the target calendar week, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Export local artifacts without pushing workouts to Intervals.icu.",
    )
    return parser.parse_args()


def main() -> None:
    """Build the target week, export artifacts, and optionally push them to Intervals."""

    args = parse_args()
    anchor_date = date.fromisoformat(args.week_of) if args.week_of else None

    payload = generate_plan(
        REPO_ROOT,
        mode="weekly",
        target_date=anchor_date.isoformat() if anchor_date is not None else None,
        persist=True,
    )
    planned_week = weekly_plan_from_payload(payload)
    bundle = build_plan_fit_bundle(
        payload,
        output_dir=REPO_ROOT / "output" / "plans" / planned_week.start_date,
    )
    artifacts = write_plan_fit_bundle(bundle)
    push_summary = None if args.local_only else push_weekly_plan_to_intervals(
        planned_week,
        bundle.fit_exports_by_external_id,
    )

    print(render_week_markdown(planned_week))
    print(f"Artifacts written to: {artifacts['output_dir']}")
    print(f"FIT files written: {len(artifacts['fit_files'])}")
    print(f"Validation passed: {artifacts['validation_summary']['passed']}")
    if args.local_only:
        print("Result: complete (local-only)")
    elif push_summary is not None and push_summary.success:
        print("Result: complete")
    else:
        print("Result: partial success")
    for line in render_intervals_push_lines(
        planned_week.start_date,
        push_summary,
        local_only=args.local_only,
    ):
        print(line)


if __name__ == "__main__":
    main()

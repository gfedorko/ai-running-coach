"""CLI for pushing a weekly run plan to Intervals.icu."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coach.fit_export import export_workout_fit
from coach.intervals import (
    make_event_payload,
    push_weekly_plan_to_intervals,
)
from coach.planner import generate_weekly_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Push a weekly workout plan to Intervals.icu.")
    parser.add_argument(
        "--week-of",
        help="Any date within the target calendar week, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the uploads and deletions without making API calls.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    anchor_date = date.fromisoformat(args.week_of) if args.week_of else None
    plan = generate_weekly_plan(REPO_ROOT, anchor_date=anchor_date)
    fit_exports = {workout.external_id: export_workout_fit(workout) for workout in plan.workouts}
    event_payloads = [
        make_event_payload(workout, fit_exports[workout.external_id])
        for workout in plan.workouts
    ]

    if args.dry_run:
        print("Intervals Weekly Push Dry Run")
        print("")
        print(f"Week: {plan.start_date} to {plan.end_date}")
        print(f"Readiness: {plan.readiness}")
        print("")
        print("Workouts to upsert:")
        for payload in event_payloads:
            print(f"- {payload['start_date_local'][:10]} | {payload['name']} | {payload['filename']}")
        print("")
        print("Dates that would be treated as rest days:")
        for rest_date in plan.rest_dates:
            print(f"- {rest_date}")
        return

    push_summary = push_weekly_plan_to_intervals(plan, fit_exports)
    if not push_summary.success:
        message = push_summary.failure_message or "Intervals weekly push failed."
        print(f"Intervals weekly push failed: {message}", file=sys.stderr)
        raise SystemExit(1)

    print("Intervals Weekly Push Complete")
    print("")
    print(f"Week: {plan.start_date} to {plan.end_date}")
    print(f"Deleted stale managed events: {push_summary.deleted_count}")
    print(f"Upserted workouts: {push_summary.upserted_count}")
    for event in push_summary.upserted_events:
        print(f"- {event.get('start_date_local', '')[:10]} | {event.get('name', '')}")


if __name__ == "__main__":
    main()

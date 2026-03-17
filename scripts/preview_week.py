"""CLI preview alias for the canonical weekly and forecast run plan."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coach.fit_export import build_plan_fit_bundle, write_plan_fit_bundle
from coach.planner import generate_forecast_plan, generate_weekly_plan, render_forecast_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview the weekly running plan.")
    parser.add_argument(
        "--week-of",
        help="Any date within the target calendar week, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=1,
        help="Number of calendar weeks to preview from the anchor week.",
    )
    parser.add_argument(
        "--write-local",
        action="store_true",
        help="Write local FIT artifacts for every previewed week without pushing to Intervals.icu.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    anchor_date = date.fromisoformat(args.week_of) if args.week_of else None
    if args.weeks <= 1:
        plan = generate_weekly_plan(REPO_ROOT, anchor_date=anchor_date)
        print(plan.render())
        if args.write_local:
            artifacts = write_plan_fit_bundle(
                build_plan_fit_bundle(
                    plan,
                    output_dir=REPO_ROOT / "output" / "plans" / plan.start_date,
                )
            )
            print(f"\nArtifacts written to: {artifacts['output_dir']}")
        return

    forecast = generate_forecast_plan(REPO_ROOT, anchor_date=anchor_date, weeks=args.weeks)
    print(render_forecast_markdown(forecast))
    if not args.write_local:
        return

    print("Local artifacts")
    for week in forecast.weeks:
        artifacts = write_plan_fit_bundle(
            build_plan_fit_bundle(
                week,
                output_dir=REPO_ROOT / "output" / "plans" / week.start_date,
            )
        )
        print(f"- {artifacts['output_dir']}")


if __name__ == "__main__":
    main()

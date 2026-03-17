"""Save a manual readiness check-in and refresh derived metrics."""

from __future__ import annotations

import argparse
from datetime import datetime
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Save a manual training readiness check-in.")
    parser.add_argument("--date", help="Check-in date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--energy", choices=("low", "okay", "good"))
    parser.add_argument("--sleep", choices=("poor", "okay", "good"))
    parser.add_argument("--soreness", choices=("low", "moderate", "high"))
    parser.add_argument("--notes", default="")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def main() -> None:
    """Persist a check-in and refresh daily metrics/state."""

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from coach.athlete import load_athlete_state
    from coach.data_paths import ensure_local_profile_seed, ensure_local_write_mode, resolve_runtime_paths
    from coach.intervals import (
        derive_state_from_storage,
        extract_manual_notes,
        refresh_daily_metrics_from,
        write_athlete_state,
    )
    from coach.metrics import as_dicts
    from coach.render import render_check_in_markdown, render_json
    from coach.storage import (
        CheckInRecord,
        connect_database,
        fetch_all_activities,
        latest_history_date,
        upsert_check_in,
    )

    args = build_parser().parse_args()
    current_time = datetime.now().astimezone()
    local_date = args.date or current_time.date().isoformat()
    try:
        ensure_local_write_mode()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_paths = ensure_local_profile_seed(repo_root)
    seed_paths = resolve_runtime_paths(repo_root, profile_name="demo")
    state_path = write_paths.athlete_state
    if state_path.exists():
        existing_state = load_athlete_state(state_path)
        manual_notes = extract_manual_notes(state_path)
    else:
        existing_state = load_athlete_state(seed_paths.athlete_state)
        manual_notes = []

    with connect_database(write_paths.training_db) as connection:
        upsert_check_in(
            connection,
            CheckInRecord(
                local_date=local_date,
                energy=args.energy,
                sleep=args.sleep,
                soreness=args.soreness,
                notes=args.notes,
                updated_at=current_time.isoformat(timespec="seconds"),
            ),
        )

        metrics_end = max(local_date, latest_history_date(connection) or local_date)
        metrics = refresh_daily_metrics_from(
            connection,
            start_date=local_date,
            end_date=metrics_end,
            default_last_workout_type=existing_state.last_workout_type,
            seed_form=existing_state.form,
            seed_sleep=existing_state.sleep,
            seed_soreness=existing_state.soreness,
        )
        result = derive_state_from_storage(
            existing_state=existing_state,
            metrics=as_dicts(metrics),
            all_activities=[dict(row) for row in fetch_all_activities(connection)],
            now=current_time,
            oldest=metrics[0].local_date if metrics else local_date,
            newest=metrics_end,
            sync_mode="manual_check_in",
            raw_snapshot_dir="local-check-in",
            activities_considered=0,
        )
        write_athlete_state(state_path, result, manual_notes)
        connection.commit()

    payload = {
        "local_date": local_date,
        "energy": args.energy,
        "sleep": args.sleep,
        "soreness": args.soreness,
        "notes": args.notes,
    }
    if args.format == "json":
        print(render_json(payload))
    else:
        print(render_check_in_markdown(payload))


if __name__ == "__main__":
    main()

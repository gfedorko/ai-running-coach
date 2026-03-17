"""Load normalized recent activity history and summarize the last week."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
import json
from pathlib import Path

from coach.models import CurrentGoal, RecentActivity, WeeklyAnalysis


def load_recent_activities(path: Path) -> list[RecentActivity]:
    """Load normalized recent activities from local JSON.

    Missing files are allowed so the planner can fall back conservatively.
    """

    if not path.exists():
        return []

    raw_items = json.loads(path.read_text(encoding="utf-8"))
    activities: list[RecentActivity] = []
    for item in raw_items:
        activities.append(
            RecentActivity(
                date=str(item["date"]),
                sport=str(item["sport"]),
                workout_type=str(item["workout_type"]),
                distance_m=float(item["distance_m"]),
                moving_time_s=float(item["moving_time_s"]),
                training_load=float(item["training_load"]),
                name=str(item["name"]),
            )
        )

    return sorted(activities, key=lambda activity: activity.date, reverse=True)


def analyze_recent_training(
    activities: list[RecentActivity],
    goal: CurrentGoal,
    reference_date: date,
) -> WeeklyAnalysis:
    """Analyze the last completed 7 days of running history."""

    window_end = reference_date - timedelta(days=1)
    window_start = window_end - timedelta(days=6)

    recent_runs = [
        activity
        for activity in activities
        if activity.sport.lower() == "run"
        and window_start <= date.fromisoformat(activity.date) <= window_end
    ]

    total_distance_km = sum(activity.distance_m for activity in recent_runs) / 1000
    total_training_load = sum(activity.training_load for activity in recent_runs)
    run_count = len(recent_runs)

    longest_run = max(recent_runs, key=lambda activity: activity.distance_m, default=None)
    long_run_distance_km = (longest_run.distance_m / 1000) if longest_run else 0.0
    long_run_duration_min = (longest_run.moving_time_s / 60) if longest_run else 0.0

    quality_types = {"threshold", "hard", "interval", "tempo"}
    quality_session_count = sum(
        1 for activity in recent_runs if activity.workout_type.lower() in quality_types
    )

    overloaded = (
        total_distance_km > goal.target_weekly_volume_km * 1.15
        or total_training_load > goal.target_weekly_volume_km * 4.0
        or quality_session_count >= 3
    )

    most_recent_workout_type = recent_runs[0].workout_type if recent_runs else "unknown"

    return WeeklyAnalysis(
        window_start=window_start,
        window_end=window_end,
        total_distance_km=round(total_distance_km, 1),
        run_count=run_count,
        long_run_distance_km=round(long_run_distance_km, 1),
        long_run_duration_min=round(long_run_duration_min, 1),
        quality_session_count=quality_session_count,
        most_recent_workout_type=most_recent_workout_type,
        total_training_load=round(total_training_load, 1),
        history_complete=bool(recent_runs),
        overloaded=overloaded,
    )


def serialize_recent_activities(activities: list[RecentActivity]) -> str:
    """Render normalized activities back to JSON for local storage."""

    return json.dumps([asdict(activity) for activity in activities], indent=2) + "\n"

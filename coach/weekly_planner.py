"""Compatibility wrappers around the canonical DB-backed planner."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from coach.planner import (
    PlannedWorkout,
    WeeklyPlan,
    generate_weekly_plan,
    next_monday,
    render_week_markdown,
    render_workout_blocks,
)
from coach.readiness import determine_readiness


def build_next_week_plan(base_dir: Path, reference_date: date | None = None) -> WeeklyPlan:
    """Compatibility wrapper for the next Monday-Sunday plan."""

    anchor_date = next_monday(reference_date or date.today())
    return generate_weekly_plan(base_dir, anchor_date=anchor_date)


def select_today_or_next_workout(planned_week: WeeklyPlan, reference_date: date) -> PlannedWorkout:
    """Return the next scheduled workout on or after the reference date."""

    future_workouts = [workout for workout in planned_week.workouts if workout.date >= reference_date.isoformat()]
    if future_workouts:
        return future_workouts[0]
    if planned_week.workouts:
        return planned_week.workouts[0]
    raise ValueError("The planned week does not contain any workouts.")

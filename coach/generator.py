"""Compatibility layer that renders the canonical next workout for the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from coach.athlete import AthleteState, load_athlete_profile, load_athlete_state
from coach.data_paths import resolve_runtime_paths
from coach.goals import load_current_goal
from coach.planner import (
    build_next_workout,
    render_workout_blocks,
)
from coach.planner import generate_plan
from coach.readiness import cap_readiness, determine_readiness
from coach.storage import (
    connect_database,
    fetch_latest_weekly_plan_id_for_range,
    fetch_plan_items,
)
from coach.workouts import load_structured_workout_library


@dataclass(slots=True)
class WorkoutRecommendation:
    """Rendered workout recommendation returned to the CLI."""

    readiness: str
    workout_type: str
    warmup: str
    main_set: str
    cooldown: str
    notes: str

    def render(self) -> str:
        """Format the recommendation as readable terminal output."""

        return (
            "Workout Recommendation\n\n"
            f"Readiness: {self.readiness}\n"
            f"Type: {self.workout_type}\n\n"
            "Warmup\n"
            f"{self.warmup}\n\n"
            "Main Set\n"
            f"{self.main_set}\n\n"
            "Cooldown\n"
            f"{self.cooldown}\n\n"
            "Notes\n"
            f"{self.notes}"
        )


def generate_today_workout(base_dir: Path) -> WorkoutRecommendation:
    """Render the current or next recommended workout from the canonical planner."""

    current_date = datetime.now().astimezone().date()
    persisted = _load_persisted_current_week_workout(base_dir, current_date)
    if persisted is not None:
        return persisted

    try:
        payload = generate_plan(
            base_dir,
            mode="next",
            target_date=current_date.isoformat(),
            persist=False,
        )
        item = payload["items"][0]
        return WorkoutRecommendation(
            readiness=str(payload["context"]["readiness"]),
            workout_type=str(item["workout_type"]).title(),
            warmup=str(item["warmup"]),
            main_set=str(item["main_set"]),
            cooldown=str(item["cooldown"]),
            notes=str(item["notes"]),
        )
    except ValueError as exc:
        if "No derived metrics available" not in str(exc):
            raise
        return _generate_fallback_workout(base_dir, current_date)


def _load_persisted_current_week_workout(
    base_dir: Path,
    current_date,
) -> WorkoutRecommendation | None:
    """Use an already generated weekly plan for the current week when available."""

    db_path = resolve_runtime_paths(base_dir).training_db
    if not db_path.exists():
        return None

    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    with connect_database(db_path) as connection:
        plan_id = fetch_latest_weekly_plan_id_for_range(
            connection,
            start_date=week_start.isoformat(),
            end_date=week_end.isoformat(),
        )
        if plan_id is None:
            return None

        items = [dict(row) for row in fetch_plan_items(connection, plan_id)]
        if not items:
            return None

    for item in items:
        if item["scheduled_date"] >= current_date.isoformat():
            return _recommendation_from_plan_item(item)
    return _recommendation_from_plan_item(items[0])


def _recommendation_from_plan_item(item: dict[str, str]) -> WorkoutRecommendation:
    return WorkoutRecommendation(
        readiness="planned_week",
        workout_type=str(item["workout_type"]).title(),
        warmup=str(item["warmup"]),
        main_set=str(item["main_set"]),
        cooldown=str(item["cooldown"]),
        notes=str(item["notes"]),
    )


def _generate_fallback_workout(base_dir: Path, current_date) -> WorkoutRecommendation:
    """Use markdown compatibility inputs for a conservative no-DB recommendation."""

    paths = resolve_runtime_paths(base_dir)
    profile = load_athlete_profile(paths.athlete_profile)
    state = load_athlete_state(paths.athlete_state)
    goal = load_current_goal(paths.current_goal)
    templates = load_structured_workout_library(paths.workout_library)
    context = _fallback_context(state, goal.weekly_run_days)

    workout, _ = build_next_workout(
        profile=profile,
        templates=templates,
        context=context,
        scheduled_date=current_date,
    )
    warmup, main_set, cooldown = render_workout_blocks(workout)
    return WorkoutRecommendation(
        readiness=f"{context['readiness']} (fallback)",
        workout_type=str(workout.workout_type).title(),
        warmup=warmup,
        main_set=main_set,
        cooldown=cooldown,
        notes=str(workout.notes),
    )


def _fallback_context(state: AthleteState, weekly_run_days: int) -> dict[str, object]:
    """Build a conservative next-workout context when DB-derived metrics are unavailable."""

    readiness = cap_readiness(determine_readiness(state.form), "steady_allowed")
    last_workout = state.last_workout_type.lower()
    return {
        "readiness": readiness,
        "recovery_flag": "needs_recovery" if last_workout in {"hard", "threshold", "long"} else "good",
        "form": state.form,
        "days_since_threshold": 0 if last_workout == "threshold" else 4,
        "days_since_hard": 0 if last_workout == "hard" else 8,
        "days_since_long": 0 if last_workout == "long" else 7,
        "last_workout_type": last_workout,
        "history_complete": False,
        "recent_run_days": min(weekly_run_days, 2),
        "recent_total_distance_km": 0.0,
        "recent_quality_sessions": 0,
        "overloaded": False,
        "conservative_week": True,
    }


def TODO_future_extensions() -> None:
    """Placeholder for future integrations and richer coaching signals."""

    # TODO: Add Garmin activity ingestion.
    # TODO: Add race goal planning logic.
    # TODO: Add lap-level post-workout analysis.
    return None

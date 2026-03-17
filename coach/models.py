"""Shared planning models used across the local running coach."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class WorkoutStep:
    """A single executable workout step using stable units.

    Time durations are stored in seconds. Distance durations are stored in meters.
    Speed targets are stored in meters per second.
    """

    kind: str
    duration_type: str
    duration_value: float
    target_type: str
    target_low: float | None
    target_high: float | None
    intensity: str
    notes: str


@dataclass(slots=True)
class PlannedWorkout:
    """A structured workout ready for text rendering or FIT export."""

    date: date
    title: str
    workout_type: str
    steps: list[WorkoutStep]
    source_template: str
    fit_exportable: bool


@dataclass(slots=True)
class PlannedDay:
    """One day in the next training week."""

    date: date
    day_name: str
    status: str
    workout: PlannedWorkout | None


@dataclass(slots=True)
class PlannedWeek:
    """The full next-week plan."""

    start_date: date
    end_date: date
    goal_summary: str
    analysis_summary: str
    days: list[PlannedDay]


@dataclass(slots=True)
class CurrentGoal:
    """Local goal settings used by the weekly planner."""

    target_race_name: str
    target_race_date: str
    target_race_distance_km: float
    target_weekly_volume_km: int
    weekly_run_days: int
    preferred_long_run_day: str
    preferred_quality_days: list[str]
    current_phase: str


@dataclass(slots=True)
class RecentActivity:
    """Normalized recent activity contract produced by local sync."""

    date: str
    sport: str
    workout_type: str
    distance_m: float
    moving_time_s: float
    training_load: float
    name: str


@dataclass(slots=True)
class WeeklyAnalysis:
    """A lightweight last-week summary used to guide the next week."""

    window_start: date
    window_end: date
    total_distance_km: float
    run_count: int
    long_run_distance_km: float
    long_run_duration_min: float
    quality_session_count: int
    most_recent_workout_type: str
    total_training_load: float
    history_complete: bool
    overloaded: bool


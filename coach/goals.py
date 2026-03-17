"""Load simple local planning goals from markdown."""

from __future__ import annotations

from pathlib import Path

from coach.athlete import _parse_markdown_key_values
from coach.models import CurrentGoal


def _split_csv_list(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def load_current_goal(path: Path) -> CurrentGoal:
    """Load the current race and weekly-planning goals."""

    data = _parse_markdown_key_values(path)
    return CurrentGoal(
        target_race_name=data["target_race_name"],
        target_race_date=data["target_race_date"],
        target_race_distance_km=float(data["target_race_distance_km"]),
        target_weekly_volume_km=int(data["target_weekly_volume_km"]),
        weekly_run_days=int(data["weekly_run_days"]),
        preferred_long_run_day=data["preferred_long_run_day"],
        preferred_quality_days=_split_csv_list(data["preferred_quality_days"]),
        current_phase=data["current_phase"],
    )

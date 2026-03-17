"""Resolve public demo data and ignored local data paths."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import shutil


PROFILE_ENV_VAR = "RUN_COACH_PROFILE"
VALID_PROFILES = {"demo", "local"}
REQUIRED_READ_FILES = (
    ("athlete_profile", Path("athlete/base_profile.md")),
    ("athlete_state", Path("athlete/athlete_state.md")),
    ("recent_activities", Path("athlete/recent_activities.json")),
    ("current_goal", Path("goals/current_goal.md")),
    ("training_db", Path("training.db")),
)


@dataclass(frozen=True, slots=True)
class CoachPaths:
    """Resolved repo paths for the active athlete profile."""

    base_dir: Path
    profile_name: str
    profile_root: Path
    athlete_profile: Path
    athlete_state: Path
    recent_activities: Path
    current_goal: Path
    training_db: Path
    raw_intervals_dir: Path
    workout_library: Path


def resolve_runtime_paths(base_dir: Path, profile_name: str | None = None) -> CoachPaths:
    """Resolve the active read profile, preferring local over demo by default."""

    selected = _selected_profile(base_dir, profile_name)
    paths = _build_paths(base_dir, selected)
    missing = _missing_required_files(paths)
    if missing:
        if selected == "local":
            raise ValueError(f"Local profile is missing required files: {', '.join(missing)}")
        raise ValueError(f"Demo profile is missing required files: {', '.join(missing)}")
    return paths


def resolve_local_write_paths(base_dir: Path) -> CoachPaths:
    """Return the ignored local profile paths for all write operations."""

    return _build_paths(base_dir, "local")


def ensure_local_profile_seed(base_dir: Path) -> CoachPaths:
    """Copy the demo profile and goal into the local profile when missing."""

    local_paths = resolve_local_write_paths(base_dir)
    demo_paths = resolve_runtime_paths(base_dir, profile_name="demo")

    if not local_paths.athlete_profile.exists():
        local_paths.athlete_profile.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(demo_paths.athlete_profile, local_paths.athlete_profile)
    if not local_paths.athlete_state.exists():
        local_paths.athlete_state.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(demo_paths.athlete_state, local_paths.athlete_state)
    if not local_paths.recent_activities.exists():
        local_paths.recent_activities.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(demo_paths.recent_activities, local_paths.recent_activities)
    if not local_paths.current_goal.exists():
        local_paths.current_goal.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(demo_paths.current_goal, local_paths.current_goal)

    return local_paths


def ensure_local_write_mode(env: Mapping[str, str] | None = None) -> None:
    """Reject demo-profile overrides for commands that mutate local state."""

    requested = (env or {}).get(PROFILE_ENV_VAR, os.environ.get(PROFILE_ENV_VAR, "")).strip().lower()
    if requested == "demo":
        raise ValueError(f"{PROFILE_ENV_VAR}=demo is read-only. Unset it before running write commands.")


def _selected_profile(base_dir: Path, explicit_profile: str | None) -> str:
    requested = explicit_profile or os.environ.get(PROFILE_ENV_VAR, "").strip().lower()
    if requested:
        if requested not in VALID_PROFILES:
            raise ValueError(f"{PROFILE_ENV_VAR} must be one of: demo, local")
        return requested

    local_paths = _build_paths(base_dir, "local")
    return "local" if not _missing_required_files(local_paths) else "demo"


def _build_paths(base_dir: Path, profile_name: str) -> CoachPaths:
    profile_root = base_dir / "data" / profile_name
    return CoachPaths(
        base_dir=base_dir,
        profile_name=profile_name,
        profile_root=profile_root,
        athlete_profile=profile_root / "athlete" / "base_profile.md",
        athlete_state=profile_root / "athlete" / "athlete_state.md",
        recent_activities=profile_root / "athlete" / "recent_activities.json",
        current_goal=profile_root / "goals" / "current_goal.md",
        training_db=profile_root / "training.db",
        raw_intervals_dir=profile_root / "raw" / "intervals",
        workout_library=base_dir / "data" / "workouts" / "structured_workout_library.md",
    )


def _missing_required_files(paths: CoachPaths) -> list[str]:
    missing: list[str] = []
    for label, relative_path in REQUIRED_READ_FILES:
        if not (paths.profile_root / relative_path).exists():
            missing.append(label)
    return missing

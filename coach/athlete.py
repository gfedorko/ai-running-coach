"""Helpers for loading athlete profile and state from markdown files."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RunProfile:
    """Run-centric preferences stored under the run section."""

    experience_level: str
    primary_goal: str
    preferred_unit: str
    easy_pace_min_per_km: float
    threshold_pace_min_per_km: float
    long_run_pace_min_per_km: float
    weekly_volume_km: int
    preferred_long_run_day: str


@dataclass(slots=True)
class StrengthProfile:
    equipment: str | None = None
    preferred_session_duration_min: int | None = None
    intensity_comfort: str | None = None
    preferred_split_style: str | None = None


@dataclass(slots=True)
class MobilityProfile:
    focus_area: str | None = None
    preferred_session_duration_min: int | None = None
    can_pair_with_other_sessions: bool | None = None


@dataclass(slots=True)
class PlanningPreferences:
    conservative_progression: str | None = None
    preferred_strength_placement: str | None = None
    allow_same_day_doubles: bool | None = None
    autonomy_level: str | None = None


@dataclass(slots=True)
class IdentityPreferences:
    preferred_unit: str
    preferred_training_days: str | None = None
    max_session_duration_min: int | None = None


@dataclass(slots=True)
class AthleteProfile:
    """Base athlete information used for workout generation."""

    name: str
    experience_level: str
    primary_goal: str
    preferred_unit: str
    easy_pace_min_per_km: float
    threshold_pace_min_per_km: float
    long_run_pace_min_per_km: float
    weekly_volume_km: int
    preferred_long_run_day: str
    run_profile: RunProfile
    strength_profile: StrengthProfile
    mobility_profile: MobilityProfile
    planning_preferences: PlanningPreferences
    identity_preferences: IdentityPreferences
    extra_sections: dict[str, dict[str, str]]


@dataclass(slots=True)
class AthleteState:
    """Current athlete state used for readiness decisions."""

    date: str
    form: int
    fatigue: str
    sleep: str
    soreness: str
    last_workout_type: str


def _parse_markdown_key_values(path: Path) -> dict[str, str]:
    """Parse simple `key: value` lines from a markdown document."""

    values: dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()

    return values


def _normalize_section_name(header: str) -> str:
    cleaned = header.strip().lower()
    cleaned = cleaned.replace("-", "_").replace(" ", "_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned


def _parse_markdown_sections(path: Path) -> dict[str, dict[str, str]]:
    """Parse the markdown file into `section -> key/value` blocks."""

    sections: dict[str, dict[str, str]] = {"root": {}}
    current_section = "root"

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("##"):
            header = line.lstrip("#").strip()
            if not header:
                current_section = "root"
                continue
            current_section = _normalize_section_name(header)
            sections.setdefault(current_section, {})
            continue
        if line.startswith("#"):
            current_section = "root"
            continue
        if line.startswith("-") or line.startswith("*"):
            continue
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        sections.setdefault(current_section, {})
        sections[current_section][key.strip()] = value.strip()

    return sections


def _lookup_field(key: str, *sources: Mapping[str, str]) -> str | None:
    for source in sources:
        if not source:
            continue
        value = source.get(key)
        if value is not None:
            return value
    return None


def _require_field(key: str, *sources: Mapping[str, str]) -> str:
    value = _lookup_field(key, *sources)
    if value is None:
        raise KeyError(f"Missing required athlete profile field: {key}")
    return value


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"yes", "true", "y", "1"}:
        return True
    if normalized in {"no", "false", "n", "0"}:
        return False
    return None


def load_athlete_profile(path: Path) -> AthleteProfile:
    """Load the base athlete profile from markdown."""

    sections = _parse_markdown_sections(path)
    root = sections.pop("root", {})
    run_section = sections.pop("run_profile", {})
    strength_section = sections.pop("strength_profile", {})
    mobility_section = sections.pop("mobility_profile", {})
    planning_section = sections.pop("planning_preferences", {})
    identity_section = sections.pop("identity_preferences", {})
    extra_sections = dict(sections)

    run_profile = RunProfile(
        experience_level=_require_field("experience_level", run_section, root),
        primary_goal=_require_field("primary_goal", run_section, root),
        preferred_unit=_require_field("preferred_unit", run_section, root),
        easy_pace_min_per_km=float(
            _require_field("easy_pace_min_per_km", run_section, root)
        ),
        threshold_pace_min_per_km=float(
            _require_field("threshold_pace_min_per_km", run_section, root)
        ),
        long_run_pace_min_per_km=float(
            _require_field("long_run_pace_min_per_km", run_section, root)
        ),
        weekly_volume_km=int(
            _require_field("weekly_volume_km", run_section, root)
        ),
        preferred_long_run_day=_lookup_field(
            "preferred_long_run_day", run_section, root
        )
        or "Sunday",
    )

    strength_profile = StrengthProfile(
        equipment=_lookup_field("equipment", strength_section, root),
        preferred_session_duration_min=_int(
            _lookup_field("preferred_session_duration_min", strength_section, root)
        ),
        intensity_comfort=_lookup_field("intensity_comfort", strength_section, root),
        preferred_split_style=_lookup_field(
            "preferred_split_style", strength_section, root
        ),
    )

    mobility_profile = MobilityProfile(
        focus_area=_lookup_field("focus_area", mobility_section, root),
        preferred_session_duration_min=_int(
            _lookup_field("preferred_session_duration_min", mobility_section, root)
        ),
        can_pair_with_other_sessions=_parse_bool(
            _lookup_field(
                "can_pair_with_other_sessions", mobility_section, root
            )
        ),
    )

    planning_preferences = PlanningPreferences(
        conservative_progression=_lookup_field(
            "conservative_progression", planning_section, root
        ),
        preferred_strength_placement=_lookup_field(
            "preferred_strength_placement", planning_section, root
        ),
        allow_same_day_doubles=_parse_bool(
            _lookup_field(
                "allow_same_day_doubles", planning_section, root
            )
        ),
        autonomy_level=_lookup_field("autonomy_level", planning_section, root),
    )

    identity_preferences = IdentityPreferences(
        preferred_unit=run_profile.preferred_unit,
        preferred_training_days=_lookup_field(
            "preferred_training_days", identity_section, root
        ),
        max_session_duration_min=_int(
            _lookup_field("max_session_duration_min", identity_section, root)
        ),
    )

    return AthleteProfile(
        name=_require_field("name", root),
        experience_level=run_profile.experience_level,
        primary_goal=run_profile.primary_goal,
        preferred_unit=run_profile.preferred_unit,
        easy_pace_min_per_km=run_profile.easy_pace_min_per_km,
        threshold_pace_min_per_km=run_profile.threshold_pace_min_per_km,
        long_run_pace_min_per_km=run_profile.long_run_pace_min_per_km,
        weekly_volume_km=run_profile.weekly_volume_km,
        preferred_long_run_day=run_profile.preferred_long_run_day,
        run_profile=run_profile,
        strength_profile=strength_profile,
        mobility_profile=mobility_profile,
        planning_preferences=planning_preferences,
        identity_preferences=identity_preferences,
        extra_sections=extra_sections,
    )


def load_athlete_state(path: Path) -> AthleteState:
    """Load the current athlete state from markdown."""

    data = _parse_markdown_key_values(path)
    return AthleteState(
        date=data["date"],
        form=int(data["form"]),
        fatigue=data["fatigue"],
        sleep=data["sleep"],
        soreness=data["soreness"],
        last_workout_type=data["last_workout_type"],
    )

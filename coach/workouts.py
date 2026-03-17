"""Helpers for loading coaching rules and workout templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from coach.athlete import AthleteProfile
from coach.models import WorkoutStep
from coach.zones import pace_to_speed_mps


@dataclass(slots=True)
class WorkoutTemplate:
    """A workout option that may be selected based on readiness."""

    name: str
    workout_type: str
    allowed_readiness: list[str]
    fit_exportable: bool = False
    structure: str = "simple"
    notes: str = ""
    warmup: str = ""
    main_set: str = ""
    cooldown: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    target: str | None = None
    duration_min: int | None = None
    warmup_distance_km: float | None = None
    cooldown_distance_km: float | None = None
    repeats: int | None = None
    work_duration_min: int | None = None
    recovery_duration_min: int | None = None
    easy_duration_min: int | None = None
    steady_duration_min: int | None = None


@dataclass(slots=True)
class StructuredWorkoutStepTemplate:
    """A single structured step from the weekly workout library."""

    name: str
    duration_kind: str
    duration_value: int
    target: str
    note: str


@dataclass(slots=True)
class StructuredWorkoutTemplate:
    """A FIT-capable structured workout template."""

    key: str
    name: str
    workout_type: str
    notes: str
    steps: list[StructuredWorkoutStepTemplate]


def load_training_rules(path: Path) -> str:
    """Return the raw training rules markdown for reference and future use."""

    return path.read_text(encoding="utf-8")


def load_workout_library(path: Path) -> list[WorkoutTemplate]:
    """Parse the main workout library used by the weekly planner."""

    content = path.read_text(encoding="utf-8")
    sections: list[str] = []
    current_section: list[str] = []

    for raw_line in content.splitlines():
        if raw_line.startswith("## "):
            if current_section:
                sections.append("\n".join(current_section))
            current_section = [raw_line[3:]]
            continue
        if current_section:
            current_section.append(raw_line)

    if current_section:
        sections.append("\n".join(current_section))

    workouts: list[WorkoutTemplate] = []
    for section in sections:
        lines = [line.strip() for line in section.splitlines() if line.strip()]
        name = lines[0]
        fields: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()

        workouts.append(
            WorkoutTemplate(
                name=name,
                workout_type=fields["type"],
                allowed_readiness=[item.strip() for item in fields["allowed_readiness"].split(",")],
                fit_exportable=fields.get("fit_exportable", "false").lower() == "true",
                structure=fields["structure"],
                notes=fields["notes"],
                warmup=_legacy_warmup_text(fields),
                main_set=_legacy_main_set_text(fields),
                cooldown=_legacy_cooldown_text(fields),
                fields=dict(fields),
                target=fields.get("target"),
                duration_min=_int_or_none(fields.get("duration_min")),
                warmup_distance_km=_float_or_none(fields.get("warmup_distance_km")),
                cooldown_distance_km=_float_or_none(fields.get("cooldown_distance_km")),
                repeats=_int_or_none(fields.get("repeats")),
                work_duration_min=_int_or_none(fields.get("work_duration_min")),
                recovery_duration_min=_int_or_none(fields.get("recovery_duration_min")),
                easy_duration_min=_int_or_none(fields.get("easy_duration_min")),
                steady_duration_min=_int_or_none(fields.get("steady_duration_min")),
            )
        )

    return workouts


def find_workout_template(
    library: list[WorkoutTemplate],
    *,
    name: str | None = None,
    workout_type: str | None = None,
) -> WorkoutTemplate:
    """Find a workout template by exact name or by type."""

    for workout in library:
        if name is not None and workout.name == name:
            return workout
        if workout_type is not None and workout.workout_type == workout_type:
            return workout
    if name is not None:
        raise ValueError(f"Workout template named '{name}' was not found.")
    raise ValueError(f"Workout template for type '{workout_type}' was not found.")


def build_workout_steps(template: WorkoutTemplate, profile: AthleteProfile) -> list[WorkoutStep]:
    """Convert a workout template into executable structured steps."""

    structure = template.structure.lower()
    if structure == "simple":
        return _build_simple_steps(template, profile)
    if structure == "repeats":
        return _build_repeat_steps(template, profile)
    if structure == "long_progression":
        return _build_long_progression_steps(template, profile)
    raise ValueError(f"Unsupported workout structure: {template.structure}")


def load_structured_workout_library(path: Path) -> dict[str, StructuredWorkoutTemplate]:
    """Parse the structured workout markdown library used for calendar-week preview/push."""

    content = path.read_text(encoding="utf-8")
    sections: list[list[str]] = []
    current_section: list[str] = []

    for raw_line in content.splitlines():
        if raw_line.startswith("## "):
            if current_section:
                sections.append(current_section)
            current_section = [raw_line[3:].strip()]
            continue
        if current_section:
            current_section.append(raw_line.rstrip())

    if current_section:
        sections.append(current_section)

    templates: dict[str, StructuredWorkoutTemplate] = {}
    for section in sections:
        key = section[0].strip().lower().replace(" ", "_")
        fields: dict[str, str] = {}
        steps: list[StructuredWorkoutStepTemplate] = []

        for raw_line in section[1:]:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("step:"):
                _, value = line.split(":", 1)
                parts = [part.strip() for part in value.split("|")]
                if len(parts) != 5:
                    raise ValueError(f"Invalid structured step definition: {line}")
                steps.append(
                    StructuredWorkoutStepTemplate(
                        name=parts[0],
                        duration_kind=parts[1],
                        duration_value=int(parts[2]),
                        target=parts[3],
                        note=parts[4],
                    )
                )
                continue
            if ":" not in line:
                continue
            field, value = line.split(":", 1)
            fields[field.strip().lower()] = value.strip()

        templates[key] = StructuredWorkoutTemplate(
            key=key,
            name=fields["name"],
            workout_type=fields["type"],
            notes=fields.get("notes", ""),
            steps=steps,
        )

    return templates


def _build_simple_steps(template: WorkoutTemplate, profile: AthleteProfile) -> list[WorkoutStep]:
    target_low, target_high = _target_speed_range(profile, template.target or "easy")
    duration_seconds = float((template.duration_min or 0) * 60)
    notes = template.notes

    if template.workout_type == "Easy":
        return [
            WorkoutStep(
                kind="main",
                duration_type="time",
                duration_value=duration_seconds,
                target_type="speed",
                target_low=target_low,
                target_high=target_high,
                intensity="active",
                notes=notes,
            )
        ]

    steps: list[WorkoutStep] = []
    if template.warmup_distance_km:
        steps.append(_distance_step("warmup", template.warmup_distance_km, * _target_speed_range(profile, "easy"), intensity="warmup", notes="Relaxed warmup"))
    steps.append(
        WorkoutStep(
            kind="main",
            duration_type="time",
            duration_value=duration_seconds,
            target_type="speed",
            target_low=target_low,
            target_high=target_high,
            intensity="active",
            notes=notes,
        )
    )
    if template.cooldown_distance_km:
        steps.append(_distance_step("cooldown", template.cooldown_distance_km, * _target_speed_range(profile, "easy"), intensity="cooldown", notes="Easy cool down"))
    return steps


def _build_repeat_steps(template: WorkoutTemplate, profile: AthleteProfile) -> list[WorkoutStep]:
    steps: list[WorkoutStep] = []
    if template.warmup_distance_km:
        steps.append(_distance_step("warmup", template.warmup_distance_km, * _target_speed_range(profile, "easy"), intensity="warmup", notes="Warm into the session"))

    work_low, work_high = _target_speed_range(profile, template.target or "threshold")
    for _ in range(template.repeats or 0):
        steps.append(
            WorkoutStep(
                kind="main",
                duration_type="time",
                duration_value=float((template.work_duration_min or 0) * 60),
                target_type="speed",
                target_low=work_low,
                target_high=work_high,
                intensity="interval",
                notes=template.notes,
            )
        )
        steps.append(
            WorkoutStep(
                kind="main",
                duration_type="time",
                duration_value=float((template.recovery_duration_min or 0) * 60),
                target_type="open",
                target_low=None,
                target_high=None,
                intensity="recovery",
                notes="Jog recovery",
            )
        )

    if steps and steps[-1].intensity == "recovery":
        steps.pop()

    if template.cooldown_distance_km:
        steps.append(_distance_step("cooldown", template.cooldown_distance_km, * _target_speed_range(profile, "easy"), intensity="cooldown", notes="Jog easy to finish"))
    return steps


def _build_long_progression_steps(template: WorkoutTemplate, profile: AthleteProfile) -> list[WorkoutStep]:
    steps: list[WorkoutStep] = []
    if template.warmup_distance_km:
        steps.append(_distance_step("warmup", template.warmup_distance_km, * _target_speed_range(profile, "easy"), intensity="warmup", notes="Settle in early"))

    long_low, long_high = _target_speed_range(profile, "long")
    steady_low, steady_high = _target_speed_range(profile, "steady")
    steps.append(
        WorkoutStep(
            kind="main",
            duration_type="time",
            duration_value=float((template.easy_duration_min or 0) * 60),
            target_type="speed",
            target_low=long_low,
            target_high=long_high,
            intensity="active",
            notes="Controlled long-run effort",
        )
    )
    steps.append(
        WorkoutStep(
            kind="main",
            duration_type="time",
            duration_value=float((template.steady_duration_min or 0) * 60),
            target_type="speed",
            target_low=steady_low,
            target_high=steady_high,
            intensity="active",
            notes="Progress smoothly to steady aerobic running",
        )
    )
    if template.cooldown_distance_km:
        steps.append(_distance_step("cooldown", template.cooldown_distance_km, * _target_speed_range(profile, "easy"), intensity="cooldown", notes="Reset and finish relaxed"))
    return steps


def _distance_step(kind: str, distance_km: float, target_low: float, target_high: float, *, intensity: str, notes: str) -> WorkoutStep:
    return WorkoutStep(
        kind=kind,
        duration_type="distance",
        duration_value=float(distance_km * 1000),
        target_type="speed",
        target_low=target_low,
        target_high=target_high,
        intensity=intensity,
        notes=notes,
    )


def _target_speed_range(profile: AthleteProfile, target: str) -> tuple[float, float]:
    key = target.lower()
    if key == "easy":
        low = profile.easy_pace_min_per_km
        high = profile.easy_pace_min_per_km + (15 / 60)
    elif key == "steady":
        low = profile.threshold_pace_min_per_km + (20 / 60)
        high = profile.threshold_pace_min_per_km + (35 / 60)
    elif key == "threshold":
        low = profile.threshold_pace_min_per_km
        high = profile.threshold_pace_min_per_km + (5 / 60)
    elif key == "hard":
        low = profile.threshold_pace_min_per_km - (10 / 60)
        high = profile.threshold_pace_min_per_km - (5 / 60)
    elif key == "long":
        low = profile.long_run_pace_min_per_km
        high = profile.long_run_pace_min_per_km + (20 / 60)
    else:
        raise ValueError(f"Unsupported workout target '{target}'.")

    # Lower pace means faster speed, so low/high swap when converting to m/s.
    return pace_to_speed_mps(high), pace_to_speed_mps(low)


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value is not None else None


def _float_or_none(value: str | None) -> float | None:
    return float(value) if value is not None else None


def _legacy_warmup_text(fields: dict[str, str]) -> str:
    structure = fields.get("structure", "").lower()
    if structure in {"repeats", "simple", "long_progression"} and "warmup_distance_km" in fields:
        return f"{fields['warmup_distance_km']} km easy"
    if fields.get("type") == "Easy":
        return "10 min relaxed jog"
    return "Optional 10 min walk"


def _legacy_main_set_text(fields: dict[str, str]) -> str:
    structure = fields.get("structure", "").lower()
    workout_type = fields.get("type")

    if structure == "repeats":
        repeats = fields["repeats"]
        work = fields["work_duration_min"]
        recovery = fields["recovery_duration_min"]
        target = fields.get("target", "threshold")
        if target == "threshold":
            target_text = "threshold pace"
        elif target == "hard":
            target_text = "hard"
        else:
            target_text = target
        return f"{repeats} x {work} min @ {target_text}, {recovery} min jog recovery"

    if structure == "long_progression":
        return (
            f"{fields['easy_duration_min']} min long aerobic running, "
            f"{fields['steady_duration_min']} min steady finish"
        )

    if workout_type == "Easy":
        return f"{fields['duration_min']} min easy aerobic running"
    if workout_type == "Steady":
        return f"{fields['duration_min']} min steady aerobic running"
    if workout_type == "Long":
        return f"{fields['duration_min']} min long easy running"
    return fields.get("notes", "")


def _legacy_cooldown_text(fields: dict[str, str]) -> str:
    if "cooldown_distance_km" in fields:
        return f"{fields['cooldown_distance_km']} km easy"
    if fields.get("type") == "Easy":
        return "5 min walk and mobility"
    return "Mobility and light mobility work"

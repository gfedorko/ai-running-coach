"""FIT export adapter for structured run workouts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from coach.planner import PlannedWorkout, WeeklyPlan, render_week_markdown, weekly_plan_from_payload
from coach.zones import pace_to_speed_mps


VENDOR_ROOT = Path(__file__).resolve().parents[1] / ".vendor"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

from fit_tool.fit_file import FitFile  # type: ignore  # noqa: E402
from fit_tool.fit_file_builder import FitFileBuilder  # type: ignore  # noqa: E402
from fit_tool.profile.messages.file_id_message import FileIdMessage  # type: ignore  # noqa: E402
from fit_tool.profile.messages.workout_message import WorkoutMessage  # type: ignore  # noqa: E402
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage  # type: ignore  # noqa: E402
from fit_tool.profile.profile_type import (  # type: ignore  # noqa: E402
    FileType,
    Intensity,
    Manufacturer,
    Sport,
    WorkoutStepDuration,
    WorkoutStepTarget,
)


@dataclass(slots=True)
class FitExport:
    """A generated FIT workout ready to upload."""

    filename: str
    data: bytes


@dataclass(slots=True)
class WorkoutFitArtifact:
    """A validated FIT export paired with its source workout."""

    workout: PlannedWorkout
    fit_export: FitExport
    validation: dict[str, Any]
    checksum_sha256: str


@dataclass(slots=True)
class PlanFitBundle:
    """An in-memory weekly export bundle reusable for disk writes and uploads."""

    plan: WeeklyPlan
    output_dir: Path
    weekly_plan_markdown: str
    workout_artifacts: list[WorkoutFitArtifact]

    @property
    def fit_exports_by_external_id(self) -> dict[str, FitExport]:
        return {
            artifact.workout.external_id: artifact.fit_export
            for artifact in self.workout_artifacts
        }


@dataclass(slots=True)
class FitExportProfile:
    """Local metadata used for generated workout FIT files."""

    manufacturer: int
    product: int
    serial_number: int
    software_version: float


DEFAULT_EXPORT_PROFILE = FitExportProfile(
    manufacturer=Manufacturer.DEVELOPMENT.value,
    product=0,
    serial_number=0x12345678,
    software_version=1.0,
)


def export_workout_fit(workout: PlannedWorkout) -> FitExport:
    """Build a FIT workout file in memory from the weekly plan model."""

    profile = DEFAULT_EXPORT_PROFILE
    file_id_message = FileIdMessage()
    file_id_message.type = FileType.WORKOUT
    file_id_message.manufacturer = profile.manufacturer
    file_id_message.product = profile.product
    file_id_message.time_created = round(datetime.now().timestamp() * 1000)
    file_id_message.serial_number = profile.serial_number

    step_messages: list[WorkoutStepMessage] = []
    for step in workout.steps:
        message = WorkoutStepMessage()
        message.workout_step_name = _workout_step_title(step.name, step.target.display)
        message.intensity = _intensity_for_step(step.name)

        if step.duration.kind == "time":
            message.duration_type = WorkoutStepDuration.TIME
            _set_subfield_value(
                message,
                "duration_value",
                "duration_time",
                float(step.duration.value),
            )
        elif step.duration.kind == "distance":
            message.duration_type = WorkoutStepDuration.DISTANCE
            _set_subfield_value(
                message,
                "duration_value",
                "duration_distance",
                float(step.duration.value),
            )
        else:
            message.duration_type = WorkoutStepDuration.OPEN
            message.duration_value = 0

        if step.target.kind == "pace_range":
            message.target_type = WorkoutStepTarget.SPEED
            _set_subfield_value(
                message,
                "custom_target_value_low",
                "custom_target_speed_low",
                pace_to_speed_mps(step.target.pace_slow_min_per_km),
            )
            _set_subfield_value(
                message,
                "custom_target_value_high",
                "custom_target_speed_high",
                pace_to_speed_mps(step.target.pace_fast_min_per_km),
            )
        else:
            message.target_type = WorkoutStepTarget.OPEN
            message.target_value = 0

        if step.note:
            message.notes = step.note
        step_messages.append(message)

    workout_message = WorkoutMessage()
    workout_message.workoutName = workout.name
    workout_message.sport = Sport.RUNNING
    workout_message.num_valid_steps = len(step_messages)

    builder = FitFileBuilder(auto_define=True, min_string_size=50)
    builder.add(file_id_message)
    builder.add(workout_message)
    builder.add_all(step_messages)

    fit_file = builder.build()
    filename = build_fit_filename(workout)
    return FitExport(filename=filename, data=fit_file.to_bytes())


def export_plan_fit(
    plan_payload_or_structured_week: dict[str, Any] | WeeklyPlan,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Export a canonical weekly plan to markdown plus per-workout FIT files."""

    bundle = build_plan_fit_bundle(
        plan_payload_or_structured_week,
        output_dir=output_dir,
    )
    return write_plan_fit_bundle(bundle)


def build_plan_fit_bundle(
    plan_payload_or_structured_week: dict[str, Any] | WeeklyPlan,
    output_dir: Path | None = None,
) -> PlanFitBundle:
    """Build validated FIT exports in memory without writing files."""

    plan = (
        plan_payload_or_structured_week
        if isinstance(plan_payload_or_structured_week, WeeklyPlan)
        else _weekly_plan_from_payload(plan_payload_or_structured_week)
    )
    destination = output_dir or (
        Path(__file__).resolve().parents[1] / "output" / "plans" / plan.start_date
    )

    workout_artifacts: list[WorkoutFitArtifact] = []
    for workout in plan.workouts:
        fit_export = export_workout_fit(workout)
        validation = validate_fit_export(workout, fit_export)
        workout_artifacts.append(
            WorkoutFitArtifact(
                workout=workout,
                fit_export=fit_export,
                validation=validation,
                checksum_sha256=hashlib.sha256(fit_export.data).hexdigest(),
            )
        )

    return PlanFitBundle(
        plan=plan,
        output_dir=destination,
        weekly_plan_markdown=render_week_markdown(plan),
        workout_artifacts=workout_artifacts,
    )


def write_plan_fit_bundle(bundle: PlanFitBundle) -> dict[str, Any]:
    """Write a prepared weekly FIT export bundle to disk."""

    destination = bundle.output_dir
    destination.mkdir(parents=True, exist_ok=True)

    markdown_path = destination / "weekly_plan.md"
    markdown_path.write_text(bundle.weekly_plan_markdown, encoding="utf-8")

    fit_files: list[str] = []
    workout_artifacts: list[dict[str, Any]] = []
    for artifact in bundle.workout_artifacts:
        fit_path = destination / artifact.fit_export.filename
        fit_path.write_bytes(artifact.fit_export.data)
        fit_files.append(str(fit_path))
        workout_artifacts.append(
            {
                "scheduled_date": artifact.workout.date,
                "workout_name": artifact.workout.name,
                "workout_type": artifact.workout.workout_type,
                "template_key": artifact.workout.template_key,
                "filename": artifact.fit_export.filename,
                "step_count": len(artifact.workout.steps),
                "checksum_sha256": artifact.checksum_sha256,
                "validation": artifact.validation,
            }
        )

    validation_summary = {
        "passed": all(item["validation"]["passed"] for item in workout_artifacts),
        "validated_workouts": len(workout_artifacts),
        "failed_workouts": sum(1 for item in workout_artifacts if not item["validation"]["passed"]),
    }
    manifest = {
        "manifest_path": str(destination / "artifacts.json"),
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "planner_mode": "weekly",
        "plan_start_date": bundle.plan.start_date,
        "workout_count": len(bundle.plan.workouts),
        "output_dir": str(destination),
        "validation_summary": validation_summary,
        "workouts": workout_artifacts,
    }

    artifact_summary = {
        "output_dir": str(destination),
        "weekly_plan_markdown": str(markdown_path),
        "fit_files": fit_files,
        "validation_summary": validation_summary,
        "artifacts_manifest": manifest,
    }
    (destination / "artifacts.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return artifact_summary


def validate_fit_export(workout: PlannedWorkout, fit_export: FitExport) -> dict[str, Any]:
    """Decode a generated FIT workout and verify it matches the planned structure."""

    fit_file = load_fit_file(fit_export.data)
    data_messages = [record.message for record in fit_file.records if not record.is_definition]
    file_id_messages = [message for message in data_messages if message.name == "file_id"]
    workout_messages = [message for message in data_messages if message.name == "workout"]
    step_messages = [message for message in data_messages if message.name == "workout_step"]

    if len(file_id_messages) != 1:
        raise ValueError(f"{fit_export.filename}: expected 1 file_id message, found {len(file_id_messages)}.")
    if _enum_name(file_id_messages[0].type, FileType) != "WORKOUT":
        raise ValueError(f"{fit_export.filename}: file_id type is not WORKOUT.")
    if len(workout_messages) != 1:
        raise ValueError(f"{fit_export.filename}: expected 1 workout message, found {len(workout_messages)}.")
    if _enum_name(workout_messages[0].sport, Sport) != "RUNNING":
        raise ValueError(f"{fit_export.filename}: workout sport is not RUNNING.")
    if len(step_messages) != len(workout.steps):
        raise ValueError(
            f"{fit_export.filename}: step count mismatch, expected {len(workout.steps)} got {len(step_messages)}."
        )

    for index, (expected_step, actual_step) in enumerate(zip(workout.steps, step_messages, strict=True), start=1):
        expected_duration = _expected_duration_type(expected_step.duration.kind)
        actual_duration = _enum_name(actual_step.duration_type, WorkoutStepDuration)
        if actual_duration != expected_duration:
            raise ValueError(
                f"{fit_export.filename}: step {index} duration mismatch, expected {expected_duration} got {actual_duration}."
            )

        actual_duration_value = _decode_step_duration_value(actual_step)
        if actual_duration_value != expected_step.duration.value:
            raise ValueError(
                f"{fit_export.filename}: step {index} duration value mismatch, expected {expected_step.duration.value} got {actual_duration_value}."
            )

        expected_target = _expected_target_type(expected_step.target.kind)
        actual_target = _enum_name(actual_step.target_type, WorkoutStepTarget)
        if actual_target != expected_target:
            raise ValueError(
                f"{fit_export.filename}: step {index} target mismatch, expected {expected_target} got {actual_target}."
            )

        if expected_step.target.kind == "pace_range":
            actual_speed_low, actual_speed_high = _decode_step_speed_targets(actual_step)
            if actual_speed_low is None:
                raise ValueError(f"{fit_export.filename}: step {index} is missing custom_target_speed_low.")
            if actual_speed_high is None:
                raise ValueError(f"{fit_export.filename}: step {index} is missing custom_target_speed_high.")

    return {
        "passed": True,
        "file_type": "WORKOUT",
        "sport": "RUNNING",
        "step_count": len(step_messages),
    }


def load_fit_file(data: bytes) -> FitFile:
    """Decode a generated FIT file for tests or debugging."""

    fit_file = FitFile.from_bytes(data)
    for record in fit_file.records:
        if record.is_definition:
            continue
        message = record.message
        if message.name == "file_id" and isinstance(message.type, int):
            try:
                message.type = FileType(message.type)
            except ValueError:
                pass
        if message.name == "workout" and isinstance(message.sport, int):
            try:
                message.sport = Sport(message.sport)
            except ValueError:
                pass
        if message.name == "workout_step":
            if isinstance(message.duration_type, int):
                try:
                    message.duration_type = WorkoutStepDuration(message.duration_type)
                except ValueError:
                    pass
            if isinstance(message.target_type, int):
                try:
                    message.target_type = WorkoutStepTarget(message.target_type)
                except ValueError:
                    pass
    return fit_file


def _workout_step_title(step_name: str, target_display: str) -> str:
    if target_display == "Open":
        return step_name
    return f"{step_name} @ {target_display}"


def build_fit_filename(workout: PlannedWorkout) -> str:
    """Build a stable FIT filename from the scheduled date and workout name."""

    weekday = datetime.fromisoformat(f"{workout.date}T00:00:00").strftime("%A").lower()
    workout_slug = _slugify_filename_component(workout.name)
    if not workout_slug:
        fallback_name = workout.template_key or workout.workout_type
        workout_slug = _slugify_filename_component(fallback_name) or "workout"
    return f"{workout.date}_{weekday}_{workout_slug}.fit"


def _intensity_for_step(step_name: str) -> Intensity:
    lowered = step_name.lower()
    if "warm" in lowered:
        return Intensity.WARMUP
    if "cool" in lowered:
        return Intensity.COOLDOWN
    if "recover" in lowered:
        return Intensity.RECOVERY
    if "hard" in lowered or "rep" in lowered:
        return Intensity.INTERVAL
    return Intensity.ACTIVE


def _slugify_filename_component(value: str) -> str:
    """Normalize a label for safe ASCII filenames."""

    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized


def _set_subfield_value(message, field_name: str, subfield_name: str, value: float) -> None:
    """Write a FIT field through its specific subfield to preserve scaling."""

    field = message.get_field_by_name(field_name)
    subfield = next(
        item
        for item in field.sub_fields
        if item.name == subfield_name
    )
    field.set_value(0, value, subfield)


def _decode_step_duration_value(step_message) -> int:
    """Read a workout-step duration through the correct FIT subfield scaling."""

    if not hasattr(step_message, "get_field_by_name"):
        duration_type = _enum_name(step_message.duration_type, WorkoutStepDuration)
        if duration_type == "TIME":
            return int(round(getattr(step_message, "duration_time", 0) or 0))
        if duration_type == "DISTANCE":
            return int(round(getattr(step_message, "duration_distance", 0) or 0))
        return int(getattr(step_message, "duration_value", 0) or 0)

    field = step_message.get_field_by_name("duration_value")
    if field is None:
        raise ValueError("Workout step is missing duration_value.")

    duration_type = _enum_name(step_message.duration_type, WorkoutStepDuration)
    if duration_type == "TIME":
        subfield = field.get_sub_field(name="duration_time")
    elif duration_type == "DISTANCE":
        subfield = field.get_sub_field(name="duration_distance")
    else:
        return int(field.get_value() or 0)

    if subfield is None:
        raise ValueError(f"Workout step duration subfield is missing for {duration_type}.")
    value = field.get_value(sub_field=subfield)
    return int(round(value or 0))


def _decode_step_speed_targets(step_message) -> tuple[float | None, float | None]:
    """Read workout-step speed targets through the explicit FIT speed subfields."""

    if not hasattr(step_message, "get_field_by_name"):
        return (
            getattr(step_message, "custom_target_speed_low", None),
            getattr(step_message, "custom_target_speed_high", None),
        )

    low_field = step_message.get_field_by_name("custom_target_value_low")
    high_field = step_message.get_field_by_name("custom_target_value_high")
    if low_field is None or high_field is None:
        return None, None

    low_subfield = low_field.get_sub_field(name="custom_target_speed_low")
    high_subfield = high_field.get_sub_field(name="custom_target_speed_high")
    if low_subfield is None or high_subfield is None:
        return None, None

    return (
        low_field.get_value(sub_field=low_subfield),
        high_field.get_value(sub_field=high_subfield),
    )


def _weekly_plan_from_payload(payload: dict[str, Any]) -> WeeklyPlan:
    """Rebuild a structured weekly plan from the canonical weekly payload."""

    return weekly_plan_from_payload(payload)


def _enum_name(value: Any, enum_type) -> str:
    if hasattr(value, "name"):
        return value.name
    return enum_type(value).name


def _expected_duration_type(duration_kind: str) -> str:
    mapping = {
        "time": "TIME",
        "distance": "DISTANCE",
        "open": "OPEN",
    }
    return mapping[duration_kind]


def _expected_target_type(target_kind: str) -> str:
    mapping = {
        "pace_range": "SPEED",
        "open": "OPEN",
    }
    return mapping[target_kind]

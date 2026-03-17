"""Inspect one exported workout FIT file and print its structure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Inspect an exported workout FIT file.")
    parser.add_argument("fit_path", help="Path to the FIT file to inspect.")
    parser.add_argument(
        "--manifest",
        help="Optional path to artifacts.json for cross-checking metadata and validation.",
    )
    return parser


def main() -> None:
    """Decode the FIT file and print a plain-text summary."""

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from coach.fit_export import _decode_step_duration_value, _decode_step_speed_targets, load_fit_file
    from fit_tool.profile.profile_type import FileType, Intensity, Sport, WorkoutStepDuration, WorkoutStepTarget

    args = build_parser().parse_args()
    fit_path = Path(args.fit_path).expanduser().resolve()
    fit_file = load_fit_file(fit_path.read_bytes())
    manifest = _load_manifest(Path(args.manifest).expanduser().resolve()) if args.manifest else None

    data_messages = [record.message for record in fit_file.records if not record.is_definition]
    file_id = next((message for message in data_messages if message.name == "file_id"), None)
    workout = next((message for message in data_messages if message.name == "workout"), None)
    steps = [message for message in data_messages if message.name == "workout_step"]

    lines = [
        "FIT Inspection",
        "",
        f"File: {fit_path}",
        f"Manifest: {args.manifest or '(none)'}",
    ]
    if file_id is not None:
        lines.extend(
            [
                "",
                "File ID",
                f"Type: {_enum_or_value(getattr(file_id, 'type', None), FileType)}",
                f"Manufacturer: {getattr(file_id, 'manufacturer', '(unset)')}",
                f"Product: {getattr(file_id, 'product', '(unset)')}",
                f"Serial number: {getattr(file_id, 'serial_number', '(unset)')}",
            ]
        )

    if workout is not None:
        lines.extend(
            [
                "",
                "Workout",
                f"Name: {getattr(workout, 'workoutName', getattr(workout, 'workout_name', '(unset)'))}",
                f"Sport: {_enum_or_value(getattr(workout, 'sport', None), Sport)}",
                f"Valid steps: {getattr(workout, 'num_valid_steps', len(steps))}",
            ]
        )

    lines.extend(["", f"Steps: {len(steps)}"])
    for index, step in enumerate(steps, start=1):
        lines.extend(
            [
                f"{index}. {getattr(step, 'workout_step_name', '(unnamed step)')}",
                f"   Duration: {_step_duration_text(step, _decode_step_duration_value)}",
                f"   Target: {_step_target_text(step, _decode_step_speed_targets)}",
                f"   Intensity: {_enum_or_value(getattr(step, 'intensity', None), Intensity)}",
                f"   Notes: {getattr(step, 'notes', '(none)')}",
            ]
        )

    if manifest is not None:
        manifest_entry = _find_manifest_entry(manifest, fit_path.name)
        lines.extend(["", "Manifest"])
        if manifest_entry is None:
            lines.append("No manifest entry found for this file.")
        else:
            lines.extend(
                [
                    f"Scheduled date: {manifest_entry['scheduled_date']}",
                    f"Workout type: {manifest_entry['workout_type']}",
                    f"Template key: {manifest_entry['template_key']}",
                    f"Checksum SHA-256: {manifest_entry['checksum_sha256']}",
                    f"Validation passed: {manifest_entry['validation']['passed']}",
                    f"Validation step count: {manifest_entry['validation']['step_count']}",
                ]
            )

    print("\n".join(lines))


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_manifest_entry(manifest: dict[str, Any], filename: str) -> dict[str, Any] | None:
    for item in manifest.get("workouts", []):
        if item.get("filename") == filename:
            return item
    return None


def _step_duration_text(step, decode_step_duration_value) -> str:
    from fit_tool.profile.profile_type import WorkoutStepDuration

    duration_type = _enum_or_value(getattr(step, "duration_type", None), WorkoutStepDuration)
    if duration_type == "TIME":
        return f"{decode_step_duration_value(step)} s"
    if duration_type == "DISTANCE":
        return f"{decode_step_duration_value(step)} m"
    return duration_type


def _step_target_text(step, decode_step_speed_targets) -> str:
    from fit_tool.profile.profile_type import WorkoutStepTarget

    target_type = _enum_or_value(getattr(step, "target_type", None), WorkoutStepTarget)
    if target_type == "SPEED":
        low, high = decode_step_speed_targets(step)
        return (
            f"{low if low is not None else '(unset)'}"
            f" - {high if high is not None else '(unset)'} m/s"
        )
    return target_type


def _enum_or_value(value: Any, enum_type=None) -> str:
    if hasattr(value, "name"):
        return value.name
    if value is None:
        return "(unset)"
    if enum_type is not None:
        try:
            return enum_type(value).name
        except Exception:
            pass
    return str(value)


if __name__ == "__main__":
    main()

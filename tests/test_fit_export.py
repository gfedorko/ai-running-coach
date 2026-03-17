"""Tests for FIT workout export."""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("RUN_COACH_PROFILE", "demo")

from coach.athlete import AthleteState, load_athlete_profile
from coach.fit_export import (
    _decode_step_duration_value,
    _decode_step_speed_targets,
    build_fit_filename,
    build_plan_fit_bundle,
    export_plan_fit,
    export_workout_fit,
    load_fit_file,
    validate_fit_export,
    write_plan_fit_bundle,
)
from coach.planner import PlannedWorkout, generate_forecast_plan, plan_week, weekly_plan_to_payload
from coach.workouts import load_structured_workout_library
from fit_tool.profile.profile_type import FileType, Sport, WorkoutStepDuration, WorkoutStepTarget


class FitExportTests(unittest.TestCase):
    def setUp(self) -> None:
        profile = load_athlete_profile(REPO_ROOT / "data" / "demo" / "athlete" / "base_profile.md")
        templates = load_structured_workout_library(
            REPO_ROOT / "data" / "workouts" / "structured_workout_library.md"
        )
        state = AthleteState(
            date="2026-03-15",
            form=-10,
            fatigue="high",
            sleep="good",
            soreness="low",
            last_workout_type="long",
        )
        plan = plan_week(profile, state, templates, anchor_date=date(2026, 3, 18))
        self.threshold_workout = next(workout for workout in plan.workouts if workout.workout_type == "threshold")
        self.easy_workout = next(workout for workout in plan.workouts if workout.workout_type == "easy")

    def test_threshold_workout_exports_running_fit_steps(self) -> None:
        fit_export = export_workout_fit(self.threshold_workout)
        fit_file = load_fit_file(fit_export.data)
        data_messages = [record.message for record in fit_file.records if not record.is_definition]
        workout_messages = [message for message in data_messages if message.name == "workout"]
        step_messages = [message for message in data_messages if message.name == "workout_step"]

        self.assertEqual(len(workout_messages), 1)
        self.assertEqual(_enum_name(workout_messages[0].sport, Sport), "RUNNING")
        self.assertEqual(len(step_messages), len(self.threshold_workout.steps))

    def test_pace_ranges_map_to_custom_speed_targets(self) -> None:
        fit_export = export_workout_fit(self.threshold_workout)
        fit_file = load_fit_file(fit_export.data)
        data_messages = [record.message for record in fit_file.records if not record.is_definition]
        threshold_step = next(
            message for message in data_messages
            if message.name == "workout_step" and "Threshold rep 1" in message.workout_step_name
        )
        recovery_step = next(
            message for message in data_messages
            if message.name == "workout_step" and "Recovery 1" in message.workout_step_name
        )

        self.assertEqual(_enum_name(threshold_step.duration_type, WorkoutStepDuration), "TIME")
        self.assertEqual(_enum_name(recovery_step.target_type, WorkoutStepTarget), "OPEN")
        threshold_low, threshold_high = _decode_step_speed_targets(threshold_step)
        self.assertIsNotNone(threshold_low)
        self.assertIsNotNone(threshold_high)
        self.assertLessEqual(threshold_low, threshold_high)

    def test_duration_fields_use_scaled_fit_subfields(self) -> None:
        fit_export = export_workout_fit(self.threshold_workout)
        fit_file = load_fit_file(fit_export.data)
        data_messages = [record.message for record in fit_file.records if not record.is_definition]
        warmup_step = next(
            message for message in data_messages
            if message.name == "workout_step" and "Warm up" in message.workout_step_name
        )
        threshold_step = next(
            message for message in data_messages
            if message.name == "workout_step" and "Threshold rep 1" in message.workout_step_name
        )

        self.assertEqual(_decode_step_duration_value(warmup_step), 2000)
        self.assertEqual(_decode_step_duration_value(threshold_step), 480)

    def test_validate_fit_export_accepts_threshold_workout(self) -> None:
        fit_export = export_workout_fit(self.threshold_workout)
        validation = validate_fit_export(self.threshold_workout, fit_export)

        self.assertTrue(validation["passed"])
        self.assertEqual(validation["sport"], "RUNNING")
        self.assertEqual(validation["step_count"], len(self.threshold_workout.steps))

    def test_validate_fit_export_accepts_easy_workout(self) -> None:
        fit_export = export_workout_fit(self.easy_workout)
        validation = validate_fit_export(self.easy_workout, fit_export)

        self.assertTrue(validation["passed"])
        self.assertEqual(validation["step_count"], len(self.easy_workout.steps))

    def test_fit_filename_includes_scheduled_date_and_workout_name(self) -> None:
        filename = build_fit_filename(self.easy_workout)

        self.assertTrue(filename.startswith(f"{self.easy_workout.date}_"))
        self.assertIn("easy-aerobic-run", filename)
        self.assertTrue(filename.endswith(".fit"))

    def test_validate_fit_export_fails_for_step_count_mismatch(self) -> None:
        fit_export = export_workout_fit(self.threshold_workout)
        broken_workout = PlannedWorkout(
            date=self.threshold_workout.date,
            name=self.threshold_workout.name,
            workout_type=self.threshold_workout.workout_type,
            steps=self.threshold_workout.steps[:-1],
            notes=self.threshold_workout.notes,
            template_key=self.threshold_workout.template_key,
            source_template=self.threshold_workout.source_template,
            fit_exportable=self.threshold_workout.fit_exportable,
        )

        with self.assertRaisesRegex(ValueError, "step count mismatch"):
            validate_fit_export(broken_workout, fit_export)

    def test_validate_fit_export_fails_for_missing_speed_targets(self) -> None:
        class Message:
            def __init__(self, name: str, **values) -> None:
                self.name = name
                for key, value in values.items():
                    setattr(self, key, value)

        class Record:
            def __init__(self, message) -> None:
                self.is_definition = False
                self.message = message

        fake_file = type(
            "FakeFitFile",
            (),
            {
                "records": [
                    Record(Message("file_id", type=FileType.WORKOUT)),
                    Record(Message("workout", sport=Sport.RUNNING)),
                    *[
                        Record(
                            Message(
                                "workout_step",
                                duration_type=(
                                    WorkoutStepDuration.TIME
                                    if step.duration.kind == "time"
                                    else WorkoutStepDuration.DISTANCE
                                ),
                                duration_time=(step.duration.value if step.duration.kind == "time" else None),
                                duration_distance=(step.duration.value if step.duration.kind == "distance" else None),
                                duration_value=step.duration.value,
                                target_type=(
                                    WorkoutStepTarget.OPEN
                                    if step.target.kind == "open"
                                    else WorkoutStepTarget.SPEED
                                ),
                                custom_target_speed_low=None,
                                custom_target_speed_high=None,
                            )
                        )
                        for step in self.threshold_workout.steps
                    ],
                ]
            },
        )()

        with patch("coach.fit_export.load_fit_file", return_value=fake_file):
            with self.assertRaisesRegex(ValueError, "missing custom_target_speed_low"):
                validate_fit_export(self.threshold_workout, export_workout_fit(self.threshold_workout))

    def test_export_plan_fit_accepts_canonical_payload(self) -> None:
        profile = load_athlete_profile(REPO_ROOT / "data" / "demo" / "athlete" / "base_profile.md")
        templates = load_structured_workout_library(
            REPO_ROOT / "data" / "workouts" / "structured_workout_library.md"
        )
        state = AthleteState(
            date="2026-03-15",
            form=-10,
            fatigue="high",
            sleep="good",
            soreness="low",
            last_workout_type="long",
        )
        weekly_plan = plan_week(profile, state, templates, anchor_date=date(2026, 3, 18))
        payload = weekly_plan_to_payload(weekly_plan)

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = export_plan_fit(payload, output_dir=Path(temp_dir))

        self.assertEqual(len(summary["fit_files"]), len(weekly_plan.workouts))
        self.assertTrue(summary["validation_summary"]["passed"])
        self.assertEqual(summary["artifacts_manifest"]["workout_count"], len(weekly_plan.workouts))
        self.assertEqual(len(summary["artifacts_manifest"]["workouts"]), len(weekly_plan.workouts))
        self.assertIn("checksum_sha256", summary["artifacts_manifest"]["workouts"][0])

    def test_build_plan_fit_bundle_reuses_validated_fit_exports(self) -> None:
        profile = load_athlete_profile(REPO_ROOT / "data" / "demo" / "athlete" / "base_profile.md")
        templates = load_structured_workout_library(
            REPO_ROOT / "data" / "workouts" / "structured_workout_library.md"
        )
        state = AthleteState(
            date="2026-03-15",
            form=-10,
            fatigue="high",
            sleep="good",
            soreness="low",
            last_workout_type="long",
        )
        weekly_plan = plan_week(profile, state, templates, anchor_date=date(2026, 3, 18))

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = build_plan_fit_bundle(weekly_plan, output_dir=Path(temp_dir))
            summary = write_plan_fit_bundle(bundle)

        self.assertEqual(len(bundle.workout_artifacts), len(weekly_plan.workouts))
        self.assertEqual(len(bundle.fit_exports_by_external_id), len(weekly_plan.workouts))
        self.assertTrue(summary["validation_summary"]["passed"])

    def test_forecast_week_variants_export_valid_fit_files(self) -> None:
        forecast = generate_forecast_plan(REPO_ROOT, weeks=4)
        week_two = forecast.weeks[1]

        bundle = build_plan_fit_bundle(week_two)

        self.assertTrue(all(item.validation["passed"] for item in bundle.workout_artifacts))
        self.assertTrue(any(artifact.workout.template_key == "easy_50" for artifact in bundle.workout_artifacts))


def _enum_name(value, enum_type) -> str:
    if hasattr(value, "name"):
        return value.name
    return enum_type(value).name


if __name__ == "__main__":
    unittest.main()

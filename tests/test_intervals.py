"""Tests for the Intervals.icu sync module."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coach.athlete import AthleteState, load_athlete_state
from coach.generator import generate_today_workout
from coach.intervals import (
    IntervalsSyncError,
    classify_run_activity,
    derive_athlete_state,
    load_intervals_config,
    sync_repo_state,
)
from coach.storage import connect_database, row_count
from coach.weekly_planner import build_next_week_plan


class FakeResponse:
    """Small context manager used to mock urllib responses."""

    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def build_fake_opener(payloads: dict[str, list[dict[str, object]]]):
    """Return a fake urlopen-compatible callable."""

    def opener(request, timeout=20):  # noqa: ANN001
        url = request.full_url
        if "/activities" in url:
            return FakeResponse(json.dumps(payloads["activities"]))
        if "/wellness" in url:
            return FakeResponse(json.dumps(payloads["wellness"]))
        raise AssertionError(f"Unexpected request URL: {url}")

    return opener


class IntervalsConfigTests(unittest.TestCase):
    def test_missing_credentials_raise_clear_error(self) -> None:
        with self.assertRaisesRegex(IntervalsSyncError, "Missing INTERVALS_ICU_ATHLETE_ID"):
            load_intervals_config({})

    def test_non_integer_lookback_raises_clear_error(self) -> None:
        env = {
            "INTERVALS_ICU_ATHLETE_ID": "i123",
            "INTERVALS_ICU_API_KEY": "secret",
            "INTERVALS_LOOKBACK_DAYS": "abc",
        }
        with self.assertRaisesRegex(IntervalsSyncError, "must be an integer"):
            load_intervals_config(env)

    def test_demo_override_is_rejected_for_sync_writes(self) -> None:
        env = {
            "INTERVALS_ICU_ATHLETE_ID": "i123",
            "INTERVALS_ICU_API_KEY": "secret",
            "RUN_COACH_PROFILE": "demo",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")

            with self.assertRaisesRegex(IntervalsSyncError, "read-only"):
                sync_repo_state(temp_root, env=env, opener=build_fake_opener({"activities": [], "wellness": []}))


class IntervalsDerivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.fromisoformat("2026-03-15T08:30:00-06:00")
        self.existing_state = AthleteState(
            date="2026-03-14",
            form=4,
            fatigue="moderate",
            sleep="good",
            soreness="low",
            last_workout_type="easy",
        )

    def test_form_from_wellness_populates_state(self) -> None:
        activities = [
            {
                "type": "Run",
                "name": "Threshold Session",
                "start_date_local": "2026-03-14T07:00:00-06:00",
                "icu_training_load": 64,
                "distance": 12000,
                "moving_time": 3900,
            }
        ]
        wellness = [
            {
                "id": "2026-03-15",
                "freshness": -11.4,
                "atlLoad": 58,
                "sleepSecs": 27000,
                "soreness": 2,
            }
        ]

        result = derive_athlete_state(
            existing_state=self.existing_state,
            activities=activities,
            wellness=wellness,
            now=self.now,
            oldest="2026-03-02",
            newest="2026-03-15",
        )

        self.assertEqual(result.state.form, -11)
        self.assertEqual(result.state.fatigue, "moderate")
        self.assertEqual(result.state.sleep, "good")
        self.assertEqual(result.state.soreness, "low")
        self.assertEqual(result.state.last_workout_type, "threshold")
        self.assertIn("freshness", result.metadata.form_source)

    def test_missing_optional_wellness_fields_preserve_existing_values(self) -> None:
        activities = [
            {
                "type": "Run",
                "name": "Easy Run",
                "start_date_local": "2026-03-14T07:00:00-06:00",
                "icu_training_load": 18,
                "distance": 7000,
                "moving_time": 2500,
            }
        ]
        result = derive_athlete_state(
            existing_state=self.existing_state,
            activities=activities,
            wellness=[{"id": "2026-03-15", "freshness": -2}],
            now=self.now,
            oldest="2026-03-02",
            newest="2026-03-15",
        )

        self.assertEqual(result.state.sleep, "good")
        self.assertEqual(result.state.soreness, "low")

    def test_recent_run_is_classified_as_hard(self) -> None:
        activity = {
            "type": "Run",
            "name": "Track Intervals",
            "start_date_local": "2026-03-14T07:00:00-06:00",
            "icu_training_load": 88,
        }
        self.assertEqual(classify_run_activity(activity), "hard")

    def test_no_recent_activities_uses_conservative_fallback(self) -> None:
        result = derive_athlete_state(
            existing_state=self.existing_state,
            activities=[],
            wellness=[],
            now=self.now,
            oldest="2026-03-02",
            newest="2026-03-15",
        )

        self.assertEqual(result.state.form, 0)
        self.assertEqual(result.state.last_workout_type, "easy")
        self.assertEqual(result.metadata.activities_considered, 0)
        self.assertIn("Fallback existing state clamp", result.metadata.form_source)


class IntervalsSyncIntegrationTests(unittest.TestCase):
    def test_sync_updates_markdown_history_and_planner_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            shutil.rmtree(temp_root / "data" / "local", ignore_errors=True)
            db_path = temp_root / "data" / "local" / "training.db"
            if db_path.exists():
                db_path.unlink()

            payloads = {
                "activities": [
                    {
                        "type": "Run",
                        "name": "Tempo Run",
                        "start_date_local": "2026-03-14T07:00:00-06:00",
                        "icu_training_load": 60,
                        "distance": 11000,
                        "moving_time": 3600,
                    }
                ],
                "wellness": [
                    {
                        "id": "2026-03-15",
                        "freshness": -9.0,
                        "atlLoad": 54,
                    }
                ],
            }
            env = {
                "INTERVALS_ICU_ATHLETE_ID": "i123",
                "INTERVALS_ICU_API_KEY": "secret",
                "INTERVALS_LOOKBACK_DAYS": "14",
            }

            with patch.dict("os.environ", {}, clear=True):
                result = sync_repo_state(
                    temp_root,
                    env=env,
                    opener=build_fake_opener(payloads),
                    now=datetime.fromisoformat("2026-03-15T08:30:00-06:00"),
                )

                self.assertEqual(result.state.form, -9)

                updated_state = load_athlete_state(temp_root / "data" / "local" / "athlete" / "athlete_state.md")
                self.assertEqual(updated_state.form, -9)
                self.assertEqual(updated_state.last_workout_type, "threshold")
                self.assertEqual(
                    load_athlete_state(temp_root / "data" / "demo" / "athlete" / "athlete_state.md").form,
                    -10,
                )
                self.assertTrue((temp_root / "data" / "local" / "training.db").exists())
                self.assertTrue((temp_root / result.metadata.raw_snapshot_dir / "activities.json").exists())
                self.assertTrue((temp_root / result.metadata.raw_snapshot_dir / "wellness.json").exists())

                with connect_database(temp_root / "data" / "local" / "training.db") as connection:
                    self.assertEqual(row_count(connection, "activities"), 1)
                    self.assertEqual(row_count(connection, "wellness"), 1)
                    self.assertGreaterEqual(row_count(connection, "daily_metrics"), 1)

                recent_history_path = temp_root / "data" / "local" / "athlete" / "recent_activities.json"
                self.assertTrue(recent_history_path.exists())
                recent_history = json.loads(recent_history_path.read_text(encoding="utf-8"))
                self.assertEqual(recent_history[0]["workout_type"], "threshold")

                planned_week = build_next_week_plan(temp_root, reference_date=datetime(2026, 3, 15).date())
                self.assertEqual(planned_week.workouts[0].workout_type, "steady")

                recommendation = generate_today_workout(temp_root)
                self.assertEqual(recommendation.workout_type, "Long")

    def test_malformed_activity_payload_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            shutil.rmtree(temp_root / "data" / "local", ignore_errors=True)

            def bad_opener(request, timeout=20):  # noqa: ANN001
                if "/activities" in request.full_url:
                    return FakeResponse(json.dumps({"unexpected": "payload"}))
                return FakeResponse("[]")

            env = {
                "INTERVALS_ICU_ATHLETE_ID": "i123",
                "INTERVALS_ICU_API_KEY": "secret",
            }

            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaisesRegex(IntervalsSyncError, "expected a list"):
                    sync_repo_state(temp_root, env=env, opener=bad_opener)


if __name__ == "__main__":
    unittest.main()

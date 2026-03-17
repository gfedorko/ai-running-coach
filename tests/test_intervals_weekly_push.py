"""Tests for the weekly Intervals upload path."""

from __future__ import annotations

from datetime import date
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("RUN_COACH_PROFILE", "demo")

from coach.athlete import AthleteState, load_athlete_profile
from coach.fit_export import export_workout_fit
from coach.intervals import (
    make_event_payload,
    push_weekly_plan_to_intervals,
)
from coach.planner import plan_week
from coach.workouts import load_structured_workout_library
from scripts.push_intervals_week import main as push_intervals_week_main


class FakeResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class IntervalsWeeklyPushTests(unittest.TestCase):
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
        self.plan = plan_week(profile, state, templates, anchor_date=date(2026, 3, 18))

    def test_event_payload_contains_required_fields(self) -> None:
        workout = self.plan.workouts[0]
        fit_export = export_workout_fit(workout)
        payload = make_event_payload(workout, fit_export)

        self.assertEqual(payload["category"], "WORKOUT")
        self.assertEqual(payload["type"], "Run")
        self.assertTrue(payload["filename"].endswith(".fit"))
        self.assertTrue(payload["file_contents_base64"])
        self.assertTrue(payload["external_id"].startswith("run-coach:workout:"))

    def test_push_weekly_plan_to_intervals_replaces_stale_entries(self) -> None:
        requests: list[tuple[str, str, str]] = []
        fit_exports = {workout.external_id: export_workout_fit(workout) for workout in self.plan.workouts}

        def opener(request, timeout=20):  # noqa: ANN001
            body = request.data.decode("utf-8") if request.data else ""
            requests.append((request.get_method(), request.full_url, body))
            if request.get_method() == "GET":
                return FakeResponse(
                    json.dumps(
                        [
                            {"id": 1, "external_id": self.plan.workouts[0].external_id},
                            {"id": 2, "external_id": "run-coach:workout:2026-03-20"},
                            {"id": 3, "external_id": "other:provider:2026-03-20"},
                        ]
                    )
                )
            if request.get_method() == "PUT":
                return FakeResponse(json.dumps({"deleted": 1}))
            if request.get_method() == "POST":
                return FakeResponse(
                    json.dumps(
                        [
                            {"id": 77, "name": self.plan.workouts[0].name, "start_date_local": self.plan.workouts[0].date}
                        ]
                    )
                )
            raise AssertionError("Unexpected request")

        summary = push_weekly_plan_to_intervals(
            self.plan,
            fit_exports,
            env={
                "INTERVALS_ICU_ATHLETE_ID": "i123",
                "INTERVALS_ICU_API_KEY": "secret",
            },
            opener=opener,
        )

        self.assertTrue(summary.success)
        self.assertEqual(summary.deleted_count, 1)
        self.assertEqual(summary.upserted_count, 1)
        self.assertEqual([method for method, _, _ in requests], ["GET", "PUT", "POST"])
        self.assertIn("/events?oldest=2026-03-16&newest=2026-03-22", requests[0][1])
        self.assertIn("/events/bulk-delete", requests[1][1])
        self.assertIn("/events/bulk?upsert=true", requests[2][1])

    def test_push_weekly_plan_to_intervals_reports_missing_credentials(self) -> None:
        fit_exports = {workout.external_id: export_workout_fit(workout) for workout in self.plan.workouts}

        summary = push_weekly_plan_to_intervals(
            self.plan,
            fit_exports,
            env={},
        )

        self.assertFalse(summary.success)
        self.assertEqual(summary.deleted_count, 0)
        self.assertEqual(summary.upserted_count, 0)
        self.assertIn("Missing INTERVALS_ICU_ATHLETE_ID", summary.failure_message or "")

    def test_dry_run_does_not_require_credentials(self) -> None:
        buffer = io.StringIO()
        with patch.object(sys, "argv", ["push_intervals_week.py", "--week-of", "2026-03-18", "--dry-run"]):
            with patch("scripts.push_intervals_week.generate_weekly_plan", return_value=self.plan):
                with patch("sys.stdout", buffer):
                    push_intervals_week_main()
        output = buffer.getvalue()
        self.assertIn("Intervals Weekly Push Dry Run", output)
        self.assertIn("Workouts to upsert:", output)
        self.assertIn("Easy Aerobic Run", output)
        self.assertIn("Threshold Session", output)


if __name__ == "__main__":
    unittest.main()

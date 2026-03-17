"""Tests for the bounded coach chat router."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("RUN_COACH_PROFILE", "demo")

from coach.chat_tools import answer_chat_query
from coach.intervals import IntervalsPushSummary


class ChatCoachTests(unittest.TestCase):
    def test_plan_next_week_returns_weekly_plan(self) -> None:
        response = answer_chat_query(REPO_ROOT, "plan next week")
        self.assertIn("# Weekly Plan", response)
        self.assertIn("Why This Week", response)

    def test_how_did_last_week_go_routes_to_last_week_analysis(self) -> None:
        response = answer_chat_query(REPO_ROOT, "how did last week go?")

        self.assertIn("Last Week vs Goal", response)

    def test_readiness_query_supports_tomorrow_language(self) -> None:
        response = answer_chat_query(REPO_ROOT, "am i ready for a workout tomorrow?")

        self.assertIn("Readiness Status", response)
        self.assertIn("Date:", response)

    def test_create_intervals_tomorrow_returns_one_off_run_session(self) -> None:
        response = answer_chat_query(REPO_ROOT, "create intervals tomorrow")

        self.assertIn("One-Off Session", response)
        self.assertIn("Domain: run", response)
        self.assertIn("Type: intervals", response)
        self.assertIn("Export: fit, calendar, markdown", response)

    def test_create_strength_workout_today_returns_strength_session(self) -> None:
        response = answer_chat_query(REPO_ROOT, "create a strength workout today")

        self.assertIn("One-Off Session", response)
        self.assertIn("Domain: strength", response)
        self.assertIn("Type: strength", response)
        self.assertIn("Export: calendar, markdown", response)

    def test_create_mobility_session_tonight_returns_mobility_session(self) -> None:
        response = answer_chat_query(REPO_ROOT, "create a mobility session tonight")

        self.assertIn("One-Off Session", response)
        self.assertIn("Domain: mobility", response)
        self.assertIn("Type: mobility", response)
        self.assertIn("Export: calendar, markdown", response)

    def test_preference_prompt_is_saved_locally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")

            response = answer_chat_query(temp_root, "remember that I prefer strength on Thursdays")

            self.assertIn("Saved preference", response)
            self.assertIn("strength", response.lower())
            self.assertIn("thursday", response.lower())

    def test_generate_fit_files_reports_combined_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            with patch(
                "coach.chat_tools.push_weekly_plan_to_intervals",
                return_value=IntervalsPushSummary(
                    success=True,
                    deleted_count=1,
                    upserted_count=5,
                    upserted_events=[],
                ),
            ):
                response = answer_chat_query(temp_root, "generate fit files for next week")

            self.assertIn("FIT Export Complete", response)
            self.assertIn("Intervals push: complete", response)
            self.assertIn("Workouts upserted to Intervals: 5", response)
            self.assertTrue((temp_root / "output").exists())

    def test_generate_fit_files_reports_partial_success_when_intervals_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            response = answer_chat_query(temp_root, "generate fit files for next week")

            self.assertIn("FIT Export Partial Success", response)
            self.assertIn("FIT files written:", response)
            self.assertIn("Validation passed: True", response)
            self.assertIn("Intervals push: failed", response)
            self.assertIn("Retry with: python scripts/push_intervals_week.py", response)
            self.assertTrue((temp_root / "output").exists())

    def test_generate_fit_files_locally_skips_intervals_push(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            response = answer_chat_query(temp_root, "generate fit files locally for next week")

            self.assertIn("FIT Export Complete", response)
            self.assertIn("Intervals push: skipped (local-only export)", response)
            self.assertTrue((temp_root / "output").exists())

    def test_preview_next_four_weeks_returns_forecast(self) -> None:
        response = answer_chat_query(REPO_ROOT, "preview the next 4 weeks")

        self.assertIn("# Four-Week Forecast", response)
        self.assertIn("## Week 1", response)
        self.assertIn("## Week 4", response)

    def test_generate_next_four_weeks_locally_writes_forecast_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            response = answer_chat_query(temp_root, "generate the next 4 weeks locally")

            self.assertIn("Forecast FIT Export Complete", response)
            self.assertIn("Weeks generated: 4", response)
            self.assertTrue((temp_root / "output").exists())

    def test_unsupported_prompt_returns_supported_actions(self) -> None:
        response = answer_chat_query(REPO_ROOT, "write me a totally custom marathon block")
        self.assertIn("Supported actions", response)
        self.assertIn("plan next week", response)


if __name__ == "__main__":
    unittest.main()

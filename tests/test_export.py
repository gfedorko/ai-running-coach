"""Tests for markdown and FIT export output."""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys
import tempfile
import unittest
import json


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("RUN_COACH_PROFILE", "demo")

from coach.athlete import AthleteState, load_athlete_profile
from coach.export import export_week_plan
from coach.planner import plan_week
from coach.vendor import ensure_local_vendor_path
from coach.workouts import load_structured_workout_library

ensure_local_vendor_path()

from fit_tool.fit_file import FitFile


class ExportTests(unittest.TestCase):
    def test_export_writes_markdown_and_fit_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
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
            planned_week = plan_week(profile, state, templates, anchor_date=date(2026, 3, 18))

            output_dir = export_week_plan(temp_root, planned_week)

            self.assertTrue((output_dir / "weekly_plan.md").exists())
            manifest = json.loads((output_dir / "artifacts.json").read_text(encoding="utf-8"))
            fit_files = sorted(output_dir.glob("*.fit"))
            self.assertEqual(len(fit_files), len(planned_week.workouts))
            self.assertTrue(manifest["validation_summary"]["passed"])
            self.assertEqual(len(manifest["workouts"]), len(planned_week.workouts))

            parsed = FitFile.from_file(str(fit_files[0]))
            message_names = [
                record.message.name
                for record in parsed.records
                if hasattr(record.message, "name")
            ]
            self.assertIn("workout", message_names)
            self.assertIn("workout_step", message_names)


if __name__ == "__main__":
    unittest.main()

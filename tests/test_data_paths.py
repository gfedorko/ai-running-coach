"""Tests for demo/local runtime path resolution."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coach.data_paths import (
    ensure_local_profile_seed,
    ensure_local_write_mode,
    resolve_local_write_paths,
    resolve_runtime_paths,
)


class DataPathsTests(unittest.TestCase):
    def test_prefers_local_profile_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            self._write_profile_files(temp_root, "demo")
            self._write_profile_files(temp_root, "local")

            with patch.dict("os.environ", {}, clear=True):
                paths = resolve_runtime_paths(temp_root)

            self.assertEqual(paths.profile_name, "local")
            self.assertEqual(paths.profile_root, temp_root / "data" / "local")
            self.assertEqual(paths.athlete_profile.name, "base_profile.md")

    def test_falls_back_to_demo_when_local_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            self._write_profile_files(temp_root, "demo")

            with patch.dict("os.environ", {}, clear=True):
                paths = resolve_runtime_paths(temp_root)

            self.assertEqual(paths.profile_name, "demo")
            self.assertEqual(paths.training_db, temp_root / "data" / "demo" / "training.db")

    def test_env_override_forces_demo_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            self._write_profile_files(temp_root, "demo")
            self._write_profile_files(temp_root, "local")

            with patch.dict("os.environ", {"RUN_COACH_PROFILE": "demo"}):
                paths = resolve_runtime_paths(temp_root)

            self.assertEqual(paths.profile_name, "demo")

    def test_forcing_missing_local_profile_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            self._write_profile_files(temp_root, "demo")

            with patch.dict("os.environ", {"RUN_COACH_PROFILE": "local"}):
                with self.assertRaisesRegex(ValueError, "Local profile is missing required files"):
                    resolve_runtime_paths(temp_root)

    def test_write_paths_always_target_local_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            self._write_profile_files(temp_root, "demo")

            with patch.dict("os.environ", {"RUN_COACH_PROFILE": "demo"}):
                paths = resolve_local_write_paths(temp_root)

            self.assertEqual(paths.profile_name, "local")
            self.assertEqual(paths.profile_root, temp_root / "data" / "local")

    def test_seeding_local_profile_copies_demo_profile_and_goal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            self._write_profile_files(temp_root, "demo")

            seeded = ensure_local_profile_seed(temp_root)

            self.assertEqual(seeded.profile_name, "local")
            self.assertTrue(seeded.athlete_profile.exists())
            self.assertTrue(seeded.current_goal.exists())
            self.assertTrue(seeded.athlete_state.exists())
            self.assertTrue(seeded.recent_activities.exists())
            self.assertIn("Demo Runner", seeded.athlete_profile.read_text(encoding="utf-8"))

            with patch.dict("os.environ", {}, clear=True):
                resolved = resolve_runtime_paths(temp_root)
            self.assertEqual(resolved.profile_name, "demo")

    def test_demo_override_is_rejected_for_write_commands(self) -> None:
        with patch.dict("os.environ", {"RUN_COACH_PROFILE": "demo"}):
            with self.assertRaisesRegex(ValueError, "read-only"):
                ensure_local_write_mode()

    def _write_profile_files(self, repo_root: Path, profile_name: str) -> None:
        profile_root = repo_root / "data" / profile_name
        (profile_root / "athlete").mkdir(parents=True, exist_ok=True)
        (profile_root / "goals").mkdir(parents=True, exist_ok=True)
        (profile_root / "athlete" / "base_profile.md").write_text(
            "\n".join(
                [
                    "# Base Profile",
                    "",
                    "name: Demo Runner",
                    "experience_level: intermediate",
                    "primary_goal: Run a healthy marathon cycle",
                    "preferred_unit: km",
                    "easy_pace_min_per_km: 6.0",
                    "threshold_pace_min_per_km: 5.0",
                    "long_run_pace_min_per_km: 6.2",
                    "weekly_volume_km: 48",
                    "preferred_long_run_day: Sunday",
                    "",
                    "## Strength Profile",
                    "equipment: bodyweight",
                    "preferred_session_duration_min: 40",
                    "",
                    "## Mobility Profile",
                    "focus_area: hips",
                    "preferred_session_duration_min: 15",
                    "",
                    "## Planning Preferences",
                    "preferred_strength_placement: after run",
                    "allow_same_day_doubles: yes",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (profile_root / "athlete" / "athlete_state.md").write_text(
            "\n".join(
                [
                    "# Athlete State",
                    "",
                    "date: 2026-03-16",
                    "form: -5",
                    "fatigue: moderate",
                    "sleep: good",
                    "soreness: low",
                    "last_workout_type: easy",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (profile_root / "athlete" / "recent_activities.json").write_text("[]\n", encoding="utf-8")
        (profile_root / "goals" / "current_goal.md").write_text(
            "\n".join(
                [
                    "# Current Goal",
                    "",
                    "target_race_name: Demo Marathon",
                    "target_race_date: 2026-10-11",
                    "target_race_distance_km: 42.2",
                    "target_weekly_volume_km: 48",
                    "weekly_run_days: 5",
                    "preferred_long_run_day: Sunday",
                    "preferred_quality_days: Tuesday, Friday",
                    "current_phase: base",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (profile_root / "training.db").touch()


if __name__ == "__main__":
    unittest.main()

"""Tests for the athlete profile parser."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coach.athlete import load_athlete_profile


class AthleteProfileTests(unittest.TestCase):
    def test_legacy_flat_profile_parses(self) -> None:
        profile = self._load_profile(self._flat_profile_markdown())
        self.assertEqual(profile.name, "Legacy Runner")
        self.assertAlmostEqual(profile.easy_pace_min_per_km, 6.2)
        self.assertEqual(profile.weekly_volume_km, 40)

    def test_sectioned_profile_parses_nested_fields(self) -> None:
        profile = self._load_profile(self._sectioned_profile_markdown())
        self.assertEqual(profile.strength_profile.equipment, "dumbbells")
        self.assertEqual(profile.mobility_profile.focus_area, "hips")
        self.assertEqual(
            profile.planning_preferences.preferred_strength_placement, "after run"
        )
        self.assertIn("custom_notes", profile.extra_sections)
        self.assertEqual(
            profile.extra_sections["custom_notes"]["favorite_movement"], "hip openers"
        )

    @staticmethod
    def _load_profile(markdown: str):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "base_profile.md"
            path.write_text(markdown, encoding="utf-8")
            return load_athlete_profile(path)

    @staticmethod
    def _flat_profile_markdown() -> str:
        return "\n".join(
            [
                "# Base Profile",
                "",
                "name: Legacy Runner",
                "experience_level: beginner",
                "primary_goal: stay consistent",
                "preferred_unit: km",
                "easy_pace_min_per_km: 6.2",
                "threshold_pace_min_per_km: 5.5",
                "long_run_pace_min_per_km: 6.4",
                "weekly_volume_km: 40",
                "preferred_long_run_day: Saturday",
                "",
            ]
        )

    @staticmethod
    def _sectioned_profile_markdown() -> str:
        return "\n".join(
            [
                "# Sectioned Profile",
                "",
                "name: Section Runner",
                "experience_level: advanced",
                "primary_goal: perform across run, strength, and mobility",
                "preferred_unit: km",
                "easy_pace_min_per_km: 5.3",
                "threshold_pace_min_per_km: 4.6",
                "long_run_pace_min_per_km: 5.5",
                "weekly_volume_km: 72",
                "preferred_long_run_day: Sunday",
                "",
                "## Strength Profile",
                "equipment: dumbbells",
                "preferred_session_duration_min: 45",
                "",
                "## Mobility Profile",
                "focus_area: hips",
                "preferred_session_duration_min: 15",
                "",
                "## Planning Preferences",
                "preferred_strength_placement: after run",
                "allow_same_day_doubles: yes",
                "",
                "## Custom Notes",
                "favorite_movement: hip openers",
                "- enjoys variety",
                "",
            ]
        )


if __name__ == "__main__":
    unittest.main()

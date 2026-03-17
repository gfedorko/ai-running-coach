"""Tests for generic one-off training session generation."""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("RUN_COACH_PROFILE", "demo")

from coach.athlete import load_athlete_profile
from coach.training_sessions import build_one_off_session, render_training_session


class TrainingSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_athlete_profile(REPO_ROOT / "data" / "demo" / "athlete" / "base_profile.md")

    def test_build_one_off_run_intervals_session(self) -> None:
        session = build_one_off_session(
            self.profile,
            domain="run",
            request_type="intervals",
            scheduled_date=date(2026, 3, 17),
        )

        self.assertEqual(session.domain, "run")
        self.assertEqual(session.session_type, "intervals")
        self.assertIn("fit", session.export_capabilities)
        self.assertIn("calendar", session.export_capabilities)
        self.assertIn("markdown", session.export_capabilities)
        self.assertEqual(session.details["focus"], "speed_support")

    def test_build_one_off_strength_session_uses_calendar_only_export(self) -> None:
        session = build_one_off_session(
            self.profile,
            domain="strength",
            request_type="strength",
            scheduled_date=date(2026, 3, 16),
        )

        self.assertEqual(session.domain, "strength")
        self.assertEqual(session.session_type, "strength")
        self.assertNotIn("fit", session.export_capabilities)
        self.assertEqual(session.details["equipment"], "bodyweight, dumbbells")

    def test_build_one_off_mobility_session_uses_profile_focus(self) -> None:
        session = build_one_off_session(
            self.profile,
            domain="mobility",
            request_type="mobility",
            scheduled_date=date(2026, 3, 16),
        )

        self.assertEqual(session.domain, "mobility")
        self.assertEqual(session.session_type, "mobility")
        self.assertEqual(session.details["focus_area"], "ankles, hips")
        self.assertNotIn("fit", session.export_capabilities)

    def test_render_training_session_includes_domain_and_export_summary(self) -> None:
        session = build_one_off_session(
            self.profile,
            domain="strength",
            request_type="strength",
            scheduled_date=date(2026, 3, 16),
        )

        rendered = render_training_session(session)

        self.assertIn("One-Off Session", rendered)
        self.assertIn("Domain: strength", rendered)
        self.assertIn("Export: calendar, markdown", rendered)


if __name__ == "__main__":
    unittest.main()

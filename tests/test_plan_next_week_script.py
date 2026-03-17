"""Tests for the combined weekly planning CLI."""

from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import patch

from coach.intervals import IntervalsPushSummary
from scripts.plan_next_week import main as plan_next_week_main


class _FakePlan:
    start_date = "2026-03-16"


class _FakeBundle:
    fit_exports_by_external_id = {"run-coach:workout:2026-03-17": object()}


class PlanNextWeekScriptTests(unittest.TestCase):
    def test_default_run_exports_and_pushes_to_intervals(self) -> None:
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["plan_next_week.py"]):
            with patch("scripts.plan_next_week.generate_plan", return_value={"target_date": "2026-03-16"}) as generate_plan:
                with patch("scripts.plan_next_week.weekly_plan_from_payload", return_value=_FakePlan()):
                    with patch("scripts.plan_next_week.build_plan_fit_bundle", return_value=_FakeBundle()):
                        with patch(
                            "scripts.plan_next_week.write_plan_fit_bundle",
                            return_value={
                                "output_dir": "/tmp/output/plans/2026-03-16",
                                "fit_files": ["/tmp/output/plans/2026-03-16/2026-03-17_tuesday_easy-aerobic-run.fit"],
                                "validation_summary": {"passed": True},
                            },
                        ):
                            with patch(
                                "scripts.plan_next_week.push_weekly_plan_to_intervals",
                                return_value=IntervalsPushSummary(
                                    success=True,
                                    deleted_count=1,
                                    upserted_count=5,
                                    upserted_events=[],
                                ),
                            ) as push_weekly_plan:
                                with patch("scripts.plan_next_week.render_week_markdown", return_value="# Weekly Plan"):
                                    with patch("sys.stdout", stdout):
                                        plan_next_week_main()

        self.assertEqual(generate_plan.call_args.kwargs["target_date"], None)
        self.assertTrue(push_weekly_plan.called)
        self.assertIn("Artifacts written to: /tmp/output/plans/2026-03-16", stdout.getvalue())
        self.assertIn("Intervals push: complete", stdout.getvalue())

    def test_week_of_flag_targets_specific_week(self) -> None:
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["plan_next_week.py", "--week-of", "2026-03-18", "--local-only"]):
            with patch("scripts.plan_next_week.generate_plan", return_value={"target_date": "2026-03-16"}) as generate_plan:
                with patch("scripts.plan_next_week.weekly_plan_from_payload", return_value=_FakePlan()):
                    with patch("scripts.plan_next_week.build_plan_fit_bundle", return_value=_FakeBundle()):
                        with patch(
                            "scripts.plan_next_week.write_plan_fit_bundle",
                            return_value={
                                "output_dir": "/tmp/output/plans/2026-03-16",
                                "fit_files": ["/tmp/output/plans/2026-03-16/2026-03-17_tuesday_easy-aerobic-run.fit"],
                                "validation_summary": {"passed": True},
                            },
                        ):
                            with patch("scripts.plan_next_week.render_week_markdown", return_value="# Weekly Plan"):
                                with patch("sys.stdout", stdout):
                                    plan_next_week_main()

        self.assertEqual(generate_plan.call_args.kwargs["target_date"], "2026-03-18")
        self.assertIn("Intervals push: skipped (local-only export)", stdout.getvalue())

    def test_local_artifacts_remain_reported_when_push_fails(self) -> None:
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["plan_next_week.py"]):
            with patch("scripts.plan_next_week.generate_plan", return_value={"target_date": "2026-03-16"}):
                with patch("scripts.plan_next_week.weekly_plan_from_payload", return_value=_FakePlan()):
                    with patch("scripts.plan_next_week.build_plan_fit_bundle", return_value=_FakeBundle()):
                        with patch(
                            "scripts.plan_next_week.write_plan_fit_bundle",
                            return_value={
                                "output_dir": "/tmp/output/plans/2026-03-16",
                                "fit_files": ["/tmp/output/plans/2026-03-16/2026-03-17_tuesday_easy-aerobic-run.fit"],
                                "validation_summary": {"passed": True},
                            },
                        ) as write_plan_fit_bundle:
                            with patch(
                                "scripts.plan_next_week.push_weekly_plan_to_intervals",
                                return_value=IntervalsPushSummary(
                                    success=False,
                                    deleted_count=0,
                                    upserted_count=0,
                                    upserted_events=[],
                                    failure_message="Missing INTERVALS_ICU_ATHLETE_ID.",
                                ),
                            ):
                                with patch("scripts.plan_next_week.render_week_markdown", return_value="# Weekly Plan"):
                                    with patch("sys.stdout", stdout):
                                        plan_next_week_main()

        self.assertTrue(write_plan_fit_bundle.called)
        self.assertIn("Artifacts written to: /tmp/output/plans/2026-03-16", stdout.getvalue())
        self.assertIn("Intervals push: failed", stdout.getvalue())
        self.assertIn("Retry with: python scripts/push_intervals_week.py --week-of 2026-03-16", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

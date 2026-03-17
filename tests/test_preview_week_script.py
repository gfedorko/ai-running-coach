"""Tests for the forecast preview CLI."""

from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import patch

from scripts.preview_week import main as preview_week_main


class _FakeWeek:
    def __init__(self, start_date: str) -> None:
        self.start_date = start_date

    def render(self) -> str:
        return "Weekly Workout Preview"


class _FakeForecast:
    def __init__(self) -> None:
        self.weeks = [_FakeWeek("2026-03-23"), _FakeWeek("2026-03-30")]


class PreviewWeekScriptTests(unittest.TestCase):
    def test_multiweek_preview_renders_forecast(self) -> None:
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["preview_week.py", "--weeks", "4"]):
            with patch("scripts.preview_week.generate_forecast_plan", return_value=_FakeForecast()):
                with patch("scripts.preview_week.render_forecast_markdown", return_value="# Four-Week Forecast"):
                    with patch("sys.stdout", stdout):
                        preview_week_main()

        self.assertIn("# Four-Week Forecast", stdout.getvalue())

    def test_write_local_exports_each_forecast_week(self) -> None:
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["preview_week.py", "--weeks", "4", "--write-local"]):
            with patch("scripts.preview_week.generate_forecast_plan", return_value=_FakeForecast()):
                with patch("scripts.preview_week.render_forecast_markdown", return_value="# Four-Week Forecast"):
                    with patch("scripts.preview_week.build_plan_fit_bundle", return_value=object()):
                        with patch(
                            "scripts.preview_week.write_plan_fit_bundle",
                            side_effect=[
                                {"output_dir": "/tmp/output/plans/2026-03-23"},
                                {"output_dir": "/tmp/output/plans/2026-03-30"},
                            ],
                        ) as write_plan_fit_bundle:
                            with patch("sys.stdout", stdout):
                                preview_week_main()

        self.assertEqual(write_plan_fit_bundle.call_count, 2)
        self.assertIn("/tmp/output/plans/2026-03-23", stdout.getvalue())
        self.assertIn("/tmp/output/plans/2026-03-30", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

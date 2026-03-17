"""Tests for weekly planning."""

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

from coach.athlete import AthleteState, load_athlete_profile
from coach.planner import choose_template_key_for_role, generate_forecast_plan, plan_week
from coach.workouts import load_structured_workout_library


class WeeklyPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_athlete_profile(REPO_ROOT / "data" / "demo" / "athlete" / "base_profile.md")
        self.templates = load_structured_workout_library(
            REPO_ROOT / "data" / "workouts" / "structured_workout_library.md"
        )

    def test_calendar_week_anchor_resolves_to_monday_and_sunday(self) -> None:
        state = AthleteState(
            date="2026-03-15",
            form=-10,
            fatigue="high",
            sleep="good",
            soreness="low",
            last_workout_type="long",
        )
        plan = plan_week(self.profile, state, self.templates, anchor_date=date(2026, 3, 18))
        self.assertEqual(plan.start_date, "2026-03-16")
        self.assertEqual(plan.end_date, "2026-03-22")

    def test_threshold_week_structure(self) -> None:
        state = AthleteState(
            date="2026-03-15",
            form=-10,
            fatigue="high",
            sleep="good",
            soreness="low",
            last_workout_type="long",
        )
        plan = plan_week(self.profile, state, self.templates, anchor_date=date(2026, 3, 18))
        workouts_by_date = {workout.date: workout for workout in plan.workouts}

        self.assertEqual(plan.readiness, "threshold_allowed")
        self.assertEqual(workouts_by_date["2026-03-17"].workout_type, "threshold")
        self.assertEqual(workouts_by_date["2026-03-19"].workout_type, "steady")
        self.assertEqual(workouts_by_date["2026-03-21"].workout_type, "long")
        self.assertEqual(plan.rest_dates, ["2026-03-16", "2026-03-20"])

    def test_easy_only_suppresses_quality_sessions(self) -> None:
        state = AthleteState(
            date="2026-03-15",
            form=-25,
            fatigue="high",
            sleep="good",
            soreness="low",
            last_workout_type="long",
        )
        plan = plan_week(self.profile, state, self.templates, anchor_date=date(2026, 3, 18))
        workout_types = {workout.workout_type for workout in plan.workouts}
        workouts_by_date = {workout.date: workout for workout in plan.workouts}

        self.assertEqual(plan.readiness, "easy_only")
        self.assertNotIn("threshold", workout_types)
        self.assertNotIn("hard", workout_types)
        self.assertEqual(workouts_by_date["2026-03-21"].name, "Reduced Long Run")

    def test_generated_workouts_keep_professional_labels_and_template_identity(self) -> None:
        state = AthleteState(
            date="2026-03-15",
            form=-10,
            fatigue="high",
            sleep="good",
            soreness="low",
            last_workout_type="long",
        )
        plan = plan_week(self.profile, state, self.templates, anchor_date=date(2026, 3, 18))
        threshold = next(workout for workout in plan.workouts if workout.workout_type == "threshold")

        self.assertEqual(threshold.name, "Threshold Session")
        self.assertEqual(threshold.source_template, "Threshold Session")
        self.assertIn("Strong aerobic quality", threshold.notes)
        self.assertIn("Smooth and controlled", threshold.steps[1].note)

    def test_marathon_phase_prefers_threshold_over_hard_intervals(self) -> None:
        state = AthleteState(
            date="2026-03-15",
            form=12,
            fatigue="low",
            sleep="good",
            soreness="low",
            last_workout_type="easy",
        )
        plan = plan_week(self.profile, state, self.templates, anchor_date=date(2026, 3, 18))
        workouts_by_date = {workout.date: workout for workout in plan.workouts}

        self.assertEqual(plan.readiness, "hard_allowed")
        self.assertEqual(workouts_by_date["2026-03-17"].workout_type, "threshold")
        self.assertEqual(workouts_by_date["2026-03-19"].workout_type, "steady")

    def test_marathon_phase_requires_recent_volume_for_threshold_day(self) -> None:
        template_key, reason = choose_template_key_for_role(
            role="primary_quality",
            context={
                "readiness": "hard_allowed",
                "recovery_flag": "good",
                "current_phase": "marathon_base",
                "target_race_distance_km": 42.2,
                "target_weekly_volume_km": 65,
                "target_weekly_run_days": 5,
                "recent_total_distance_km": 44.0,
                "recent_run_days": 3,
                "recent_quality_sessions": 1,
                "conservative_week": False,
                "last_workout_type": "easy",
                "days_since_threshold": 5,
                "days_since_hard": 9,
                "days_since_long": 7,
            },
        )

        self.assertEqual(template_key, "steady")
        self.assertIn("weekly volume", reason)

    def test_marathon_phase_requires_recent_volume_for_full_long_run(self) -> None:
        template_key, reason = choose_template_key_for_role(
            role="long",
            context={
                "readiness": "threshold_allowed",
                "recovery_flag": "good",
                "current_phase": "marathon_base",
                "target_race_distance_km": 42.2,
                "target_weekly_volume_km": 65,
                "target_weekly_run_days": 5,
                "recent_total_distance_km": 48.0,
                "recent_run_days": 3,
                "recent_quality_sessions": 1,
                "conservative_week": False,
                "last_workout_type": "easy",
                "days_since_threshold": 5,
                "days_since_hard": 9,
                "days_since_long": 7,
            },
        )

        self.assertEqual(template_key, "reduced_long")
        self.assertIn("long run stays reduced", reason)

    def test_four_week_forecast_progresses_across_future_weeks(self) -> None:
        forecast = generate_forecast_plan(REPO_ROOT, weeks=4)

        self.assertEqual(len(forecast.weeks), 4)
        self.assertEqual(forecast.weeks[0].start_date, "2026-03-23")
        self.assertNotEqual(
            [workout.template_key for workout in forecast.weeks[0].workouts],
            [workout.template_key for workout in forecast.weeks[1].workouts],
        )
        self.assertEqual(forecast.weeks[3].workouts[3].template_key, "long_90")

    def test_one_week_forecast_matches_first_week_of_four_week_forecast(self) -> None:
        one_week = generate_forecast_plan(REPO_ROOT, weeks=1)
        four_week = generate_forecast_plan(REPO_ROOT, weeks=4)

        self.assertEqual(
            [workout.template_key for workout in one_week.weeks[0].workouts],
            [workout.template_key for workout in four_week.weeks[0].workouts],
        )
        self.assertEqual(one_week.summaries[0].load_target_km, four_week.summaries[0].load_target_km)

    def test_forecast_never_uses_hard_intervals_in_marathon_base(self) -> None:
        forecast = generate_forecast_plan(REPO_ROOT, weeks=4)

        workout_types = [workout.workout_type for week in forecast.weeks for workout in week.workouts]
        self.assertNotIn("hard", workout_types)

    def test_forecast_weekly_load_targets_respect_growth_cap(self) -> None:
        forecast = generate_forecast_plan(REPO_ROOT, weeks=4)

        targets = [summary.load_target_km for summary in forecast.summaries]
        for previous, current in zip(targets, targets[1:]):
            self.assertLessEqual(current, round(previous * 1.08, 1) + 0.05)


if __name__ == "__main__":
    unittest.main()

"""Tests for bounded daily metric rebuilds and storage indexes."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coach.metrics import as_dicts, rebuild_daily_metrics, rebuild_daily_metrics_range
from coach.storage import connect_database


class DailyMetricRangeTests(unittest.TestCase):
    def test_range_rebuild_matches_full_rebuild_tail(self) -> None:
        start = date(2026, 1, 1)
        activities = []
        wellness = []
        check_ins = [
            {"local_date": "2026-03-11", "energy": "okay", "sleep": "okay", "soreness": "moderate"},
            {"local_date": "2026-03-18", "energy": "good", "sleep": "good", "soreness": "low"},
        ]

        for offset in range(110):
            current = start + timedelta(days=offset)
            iso = current.isoformat()
            wellness.append(
                {
                    "local_date": iso,
                    "freshness": -8 if offset % 10 == 0 else -3,
                    "atl_load": 55 if offset % 9 == 0 else 35,
                    "sleep_secs": 25200 if offset % 7 else 21600,
                    "soreness": 3 if offset % 11 == 0 else 1,
                }
            )
            if offset % 2 == 0:
                activities.append(
                    {
                        "activity_date": iso,
                        "workout_type": "threshold" if offset % 12 == 0 else ("long" if offset % 14 == 0 else "easy"),
                        "distance_km": 14.0 if offset % 14 == 0 else 8.0,
                        "duration_minutes": 80.0 if offset % 14 == 0 else 42.0,
                        "training_load": 70.0 if offset % 12 == 0 else 38.0,
                        "name": "Run",
                        "sport": "Run",
                    }
                )

        full = rebuild_daily_metrics(
            activities,
            wellness,
            check_ins,
            end_date="2026-04-20",
            default_last_workout_type="easy",
        )
        full_by_date = {row.local_date: row for row in full}

        rebuild_start = "2026-03-10"
        prior = full_by_date["2026-03-09"]
        latest_wellness = next(
            entry for entry in reversed(wellness)
            if entry["local_date"] < rebuild_start
        )
        range_metrics = rebuild_daily_metrics_range(
            [
                item for item in activities
                if item["activity_date"] >= "2025-12-10"
            ],
            [
                item for item in wellness
                if item["local_date"] >= rebuild_start
            ],
            [
                item for item in check_ins
                if item["local_date"] >= rebuild_start
            ],
            start_date=rebuild_start,
            end_date="2026-04-20",
            default_last_workout_type=prior.last_workout_type,
            seed_form=prior.form,
            seed_sleep=prior.sleep,
            seed_soreness=prior.soreness,
            initial_latest_wellness=latest_wellness,
        )

        expected = [row for row in full if row.local_date >= rebuild_start]
        self.assertEqual(as_dicts(range_metrics), as_dicts(expected))


class StorageIndexTests(unittest.TestCase):
    def test_plan_indexes_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "training.db"
            with connect_database(db_path) as connection:
                plan_item_indexes = {
                    row["name"]
                    for row in connection.execute("PRAGMA index_list('plan_items')").fetchall()
                }
                plan_indexes = {
                    row["name"]
                    for row in connection.execute("PRAGMA index_list('plans')").fetchall()
                }

        self.assertIn("idx_plan_items_plan_position", plan_item_indexes)
        self.assertIn("idx_plan_items_scheduled_date_plan_id", plan_item_indexes)
        self.assertIn("idx_plans_mode_created_at", plan_indexes)


if __name__ == "__main__":
    unittest.main()

"""Tests for the DB-backed training planner and plan persistence."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coach.intervals import sync_repo_state
from coach.storage import CheckInRecord, connect_database, row_count, upsert_check_in
from coach.training_planner import generate_plan


class FakeResponse:
    """Small context manager used to mock urllib responses."""

    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def build_fake_opener(payloads: dict[str, list[dict[str, object]]]):
    """Return a fake urlopen-compatible callable."""

    def opener(request, timeout=20):  # noqa: ANN001
        url = request.full_url
        if "/activities" in url:
            return FakeResponse(json.dumps(payloads["activities"]))
        if "/wellness" in url:
            return FakeResponse(json.dumps(payloads["wellness"]))
        raise AssertionError(f"Unexpected request URL: {url}")

    return opener


class TrainingPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = {
            "INTERVALS_ICU_ATHLETE_ID": "i123",
            "INTERVALS_ICU_API_KEY": "secret",
            "INTERVALS_LOOKBACK_DAYS": "14",
        }

    def test_incremental_sync_is_idempotent(self) -> None:
        payloads = {
            "activities": [
                {
                    "id": "run-1",
                    "type": "Run",
                    "name": "Tempo Run",
                    "start_date_local": "2026-03-14T07:00:00-06:00",
                    "icu_training_load": 60,
                    "distance": 11000,
                    "moving_time": 3600,
                }
            ],
            "wellness": [
                {
                    "id": "2026-03-15",
                    "freshness": -9.0,
                    "atlLoad": 54,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            shutil.rmtree(temp_root / "data" / "local", ignore_errors=True)
            db_path = temp_root / "data" / "local" / "training.db"
            if db_path.exists():
                db_path.unlink()

            with patch.dict("os.environ", {}, clear=True):
                for _ in range(2):
                    sync_repo_state(
                        temp_root,
                        env=self.env,
                        opener=build_fake_opener(payloads),
                        now=datetime.fromisoformat("2026-03-15T08:30:00-06:00"),
                    )

            with connect_database(temp_root / "data" / "local" / "training.db") as connection:
                self.assertEqual(row_count(connection, "activities"), 1)
                self.assertEqual(row_count(connection, "wellness"), 1)

    def test_low_energy_check_in_downgrades_next_workout_and_persists_plan(self) -> None:
        payloads = {
            "activities": [
                {
                    "id": "run-1",
                    "type": "Run",
                    "name": "Easy Run",
                    "start_date_local": "2026-03-13T07:00:00-06:00",
                    "icu_training_load": 18,
                    "distance": 8000,
                    "moving_time": 2800,
                }
            ],
            "wellness": [
                {
                    "id": "2026-03-15",
                    "freshness": 12.0,
                    "atlLoad": 20,
                    "sleepSecs": 28800,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            shutil.rmtree(temp_root / "data" / "local", ignore_errors=True)
            db_path = temp_root / "data" / "local" / "training.db"
            if db_path.exists():
                db_path.unlink()

            with patch.dict("os.environ", {}, clear=True):
                sync_repo_state(
                    temp_root,
                    env=self.env,
                    opener=build_fake_opener(payloads),
                    now=datetime.fromisoformat("2026-03-15T08:30:00-06:00"),
                )

                with connect_database(temp_root / "data" / "local" / "training.db") as connection:
                    upsert_check_in(
                        connection,
                        CheckInRecord(
                            local_date="2026-03-15",
                            energy="low",
                            soreness="low",
                            sleep="good",
                            notes="Flat legs today.",
                            updated_at="2026-03-15T08:45:00-06:00",
                        ),
                    )
                    connection.commit()

                payload = generate_plan(
                    temp_root,
                    mode="next",
                    target_date="2026-03-15",
                    persist=True,
                    now=datetime.fromisoformat("2026-03-15T09:00:00-06:00"),
                )

                self.assertIn(payload["items"][0]["workout_type"], {"easy", "steady"})
                self.assertIn(payload["context"]["readiness"], {"easy_only", "steady_allowed"})
                self.assertIn("plan_id", payload)

                with connect_database(temp_root / "data" / "local" / "training.db") as connection:
                    self.assertEqual(row_count(connection, "plans"), 1)
                    self.assertEqual(row_count(connection, "plan_items"), 1)


if __name__ == "__main__":
    unittest.main()

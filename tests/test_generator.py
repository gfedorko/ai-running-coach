"""Compatibility tests for the legacy daily workout view."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coach.generator import determine_readiness, generate_today_workout
from coach.intervals import sync_repo_state


class FakeResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def build_fake_opener(payloads: dict[str, list[dict[str, object]]]):
    def opener(request, timeout=20):  # noqa: ANN001
        if "/activities" in request.full_url:
            import json

            return FakeResponse(json.dumps(payloads["activities"]))
        if "/wellness" in request.full_url:
            import json

            return FakeResponse(json.dumps(payloads["wellness"]))
        raise AssertionError(f"Unexpected request URL: {request.full_url}")

    return opener


class GeneratorTests(unittest.TestCase):
    def test_determine_readiness_easy_only(self) -> None:
        self.assertEqual(determine_readiness(-25), "easy_only")

    def test_determine_readiness_threshold_allowed(self) -> None:
        self.assertEqual(determine_readiness(-10), "threshold_allowed")

    def test_generate_today_workout_uses_conservative_next_workout_for_thin_history(self) -> None:
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
        env = {
            "INTERVALS_ICU_ATHLETE_ID": "i123",
            "INTERVALS_ICU_API_KEY": "secret",
            "INTERVALS_LOOKBACK_DAYS": "14",
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
                    env=env,
                    opener=build_fake_opener(payloads),
                    now=datetime.fromisoformat("2026-03-15T08:30:00-06:00"),
                )

                recommendation = generate_today_workout(temp_root)

        self.assertEqual(recommendation.workout_type, "Long")
        self.assertIn("Long easy running", recommendation.main_set)

    def test_generate_today_workout_falls_back_without_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            shutil.rmtree(temp_root / "data" / "local", ignore_errors=True)
            db_path = temp_root / "data" / "local" / "training.db"
            if db_path.exists():
                db_path.unlink()

            recommendation = generate_today_workout(temp_root)

        self.assertIn(recommendation.workout_type, {"Easy", "Steady", "Long"})
        self.assertNotEqual(recommendation.workout_type, "Hard")


if __name__ == "__main__":
    unittest.main()

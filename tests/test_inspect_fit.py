"""Tests for the FIT inspection CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("RUN_COACH_PROFILE", "demo")

from coach.chat_tools import export_fit


class InspectFitTests(unittest.TestCase):
    def test_inspect_fit_prints_workout_and_manifest_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(REPO_ROOT / "data", temp_root / "data")
            export_fit(temp_root, local_only=True)

            plans_dir = temp_root / "output" / "plans"
            plan_dir = next(plans_dir.iterdir())
            manifest_path = plan_dir / "artifacts.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            fit_path = plan_dir / manifest["workouts"][0]["filename"]

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "inspect_fit.py"),
                    str(fit_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("FIT Inspection", result.stdout)
            self.assertIn("Workout", result.stdout)
            self.assertIn("Manifest", result.stdout)
            self.assertIn("Validation passed: True", result.stdout)


if __name__ == "__main__":
    unittest.main()

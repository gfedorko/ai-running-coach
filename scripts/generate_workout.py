"""Compatibility CLI entry point for rendering the next recommended workout."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    """Add the repo root to the import path and print today's workout."""

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from coach.generator import generate_today_workout

    recommendation = generate_today_workout(repo_root)
    print(recommendation.render())


if __name__ == "__main__":
    main()

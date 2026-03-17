"""Shared readiness helpers used across metrics and planning."""

from __future__ import annotations


READINESS_ORDER = {
    "easy_only": 0,
    "steady_allowed": 1,
    "threshold_allowed": 2,
    "hard_allowed": 3,
}


def determine_readiness(form: int) -> str:
    """Map athlete form into the coaching readiness buckets."""

    if form > 10:
        return "hard_allowed"
    if -15 <= form <= -5:
        return "threshold_allowed"
    if form < -20:
        return "easy_only"
    return "steady_allowed"


def cap_readiness(readiness: str, maximum: str) -> str:
    """Clamp readiness to a more conservative level when recovery is poor."""

    if READINESS_ORDER[readiness] <= READINESS_ORDER[maximum]:
        return readiness
    return maximum

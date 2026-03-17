"""Simple pace formatting helpers for workout rendering and FIT export."""

from __future__ import annotations


def minutes_to_pace_text(minutes_per_km: float) -> str:
    """Convert decimal minutes per km into a mm:ss/km string."""

    whole_minutes = int(minutes_per_km)
    seconds = round((minutes_per_km - whole_minutes) * 60)

    if seconds == 60:
        whole_minutes += 1
        seconds = 0

    return f"{whole_minutes}:{seconds:02d}/km"


def pace_to_speed_mps(minutes_per_km: float) -> float:
    """Convert pace in minutes per km into speed in metres per second."""

    return 1000 / (minutes_per_km * 60)


def speed_to_pace_min_per_km(speed_mps: float) -> float:
    """Convert speed in metres per second into pace in minutes per km."""

    return 1000 / speed_mps / 60


def build_pace_range(fast_minutes_per_km: float, slow_minutes_per_km: float) -> str:
    """Format a fast-to-slow pace range for display."""

    return f"{minutes_to_pace_text(fast_minutes_per_km)}-{minutes_to_pace_text(slow_minutes_per_km)}"


def speed_range_text(speed_low_mps: float, speed_high_mps: float) -> str:
    """Format a speed range as a pace range for display."""

    fast = speed_to_pace_min_per_km(speed_high_mps)
    slow = speed_to_pace_min_per_km(speed_low_mps)
    return build_pace_range(fast, slow)


def threshold_range(threshold_pace_min_per_km: float, delta_seconds: int = 5) -> str:
    """Build a small threshold pace range around the athlete's threshold pace."""

    delta_minutes = delta_seconds / 60
    return build_pace_range(threshold_pace_min_per_km, threshold_pace_min_per_km + delta_minutes)


def easy_range(easy_pace_min_per_km: float, delta_seconds: int = 15) -> str:
    """Build a relaxed aerobic pace range."""

    delta_minutes = delta_seconds / 60
    return build_pace_range(easy_pace_min_per_km, easy_pace_min_per_km + delta_minutes)


def steady_range(threshold_pace_min_per_km: float) -> str:
    """Build a steady aerobic range from the threshold pace anchor."""

    return build_pace_range(
        threshold_pace_min_per_km + (20 / 60),
        threshold_pace_min_per_km + (35 / 60),
    )


def hard_range(threshold_pace_min_per_km: float) -> str:
    """Build a faster-than-threshold interval pace range."""

    return build_pace_range(
        threshold_pace_min_per_km - (10 / 60),
        threshold_pace_min_per_km - (5 / 60),
    )


def long_range(long_run_pace_min_per_km: float, delta_seconds: int = 20) -> str:
    """Build a controlled long run pace range."""

    delta_minutes = delta_seconds / 60
    return build_pace_range(long_run_pace_min_per_km, long_run_pace_min_per_km + delta_minutes)

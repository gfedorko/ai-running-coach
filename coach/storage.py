"""SQLite-backed storage helpers for imported training history and plans."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any


@dataclass(slots=True)
class ActivityRecord:
    """Normalized run activity row stored in SQLite."""

    external_id: str
    activity_date: str
    start_time: str
    name: str
    sport: str
    activity_type: str
    distance_km: float | None
    duration_minutes: float | None
    training_load: float | None
    workout_type: str
    avg_pace_min_per_km: float | None
    raw_snapshot_path: str
    last_seen_sync: str


@dataclass(slots=True)
class WellnessRecord:
    """Normalized wellness row stored in SQLite."""

    local_date: str
    freshness: float | None
    form: float | None
    tsb: float | None
    atl_load: float | None
    sleep_secs: float | None
    soreness: float | None
    fatigue: float | None
    raw_snapshot_path: str
    last_seen_sync: str


@dataclass(slots=True)
class CheckInRecord:
    """Optional manual daily check-in."""

    local_date: str
    energy: str | None
    soreness: str | None
    sleep: str | None
    notes: str
    updated_at: str


@dataclass(slots=True)
class DailyMetricRecord:
    """Date-keyed derived metrics used by summaries and planning."""

    local_date: str
    total_distance_7d: float
    total_duration_7d: float
    total_distance_14d: float
    total_duration_14d: float
    total_distance_28d: float
    total_duration_28d: float
    avg_load_7d: float | None
    avg_load_14d: float | None
    avg_load_28d: float | None
    acute_load: float | None
    chronic_load: float | None
    acute_chronic_ratio: float | None
    days_since_threshold: int | None
    days_since_hard: int | None
    days_since_long: int | None
    quality_sessions_7d: int
    quality_sessions_14d: int
    longest_run_14d: float
    longest_run_28d: float
    form: int
    form_source: str
    fatigue: str
    sleep: str
    soreness: str
    readiness: str
    recovery_flag: str
    last_workout_type: str


@dataclass(slots=True)
class TrainingSessionRecord:
    """Generic scheduled session stored in SQLite."""

    session_id: str
    created_at: str
    scheduled_date: str
    domain: str
    session_type: str
    title: str
    payload: dict[str, Any]


@dataclass(slots=True)
class PlanningRequestRecord:
    """Structured planning request persisted for chat/planner observability."""

    request_id: str
    created_at: str
    intent: str
    parameters: dict[str, Any]


@dataclass(slots=True)
class PreferenceEventRecord:
    """Preference capture event stored for planning personalization."""

    event_id: str
    created_at: str
    preference_type: str
    details: dict[str, Any]


SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    external_id TEXT PRIMARY KEY,
    activity_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    name TEXT NOT NULL,
    sport TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    distance_km REAL,
    duration_minutes REAL,
    training_load REAL,
    workout_type TEXT NOT NULL,
    avg_pace_min_per_km REAL,
    raw_snapshot_path TEXT NOT NULL,
    last_seen_sync TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activities_activity_date
ON activities(activity_date, start_time);

CREATE TABLE IF NOT EXISTS wellness (
    local_date TEXT PRIMARY KEY,
    freshness REAL,
    form REAL,
    tsb REAL,
    atl_load REAL,
    sleep_secs REAL,
    soreness REAL,
    fatigue REAL,
    raw_snapshot_path TEXT NOT NULL,
    last_seen_sync TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    local_date TEXT PRIMARY KEY,
    total_distance_7d REAL NOT NULL,
    total_duration_7d REAL NOT NULL,
    total_distance_14d REAL NOT NULL,
    total_duration_14d REAL NOT NULL,
    total_distance_28d REAL NOT NULL,
    total_duration_28d REAL NOT NULL,
    avg_load_7d REAL,
    avg_load_14d REAL,
    avg_load_28d REAL,
    acute_load REAL,
    chronic_load REAL,
    acute_chronic_ratio REAL,
    days_since_threshold INTEGER,
    days_since_hard INTEGER,
    days_since_long INTEGER,
    quality_sessions_7d INTEGER NOT NULL,
    quality_sessions_14d INTEGER NOT NULL,
    longest_run_14d REAL NOT NULL,
    longest_run_28d REAL NOT NULL,
    form INTEGER NOT NULL,
    form_source TEXT NOT NULL,
    fatigue TEXT NOT NULL,
    sleep TEXT NOT NULL,
    soreness TEXT NOT NULL,
    readiness TEXT NOT NULL,
    recovery_flag TEXT NOT NULL,
    last_workout_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS check_ins (
    local_date TEXT PRIMARY KEY,
    energy TEXT,
    soreness TEXT,
    sleep TEXT,
    notes TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    target_date TEXT NOT NULL,
    summary TEXT NOT NULL,
    rationale_json TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    output_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plans_mode_created_at
ON plans(mode, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    scheduled_date TEXT NOT NULL,
    workout_name TEXT NOT NULL,
    workout_type TEXT NOT NULL,
    warmup TEXT NOT NULL,
    main_set TEXT NOT NULL,
    cooldown TEXT NOT NULL,
    notes TEXT NOT NULL,
    rationale TEXT NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES plans(id)
);

CREATE INDEX IF NOT EXISTS idx_plan_items_plan_position
ON plan_items(plan_id, position);

CREATE INDEX IF NOT EXISTS idx_plan_items_scheduled_date_plan_id
ON plan_items(scheduled_date, plan_id);

CREATE TABLE IF NOT EXISTS training_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    scheduled_date TEXT NOT NULL,
    domain TEXT NOT NULL,
    session_type TEXT NOT NULL,
    title TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_training_sessions_scheduled_date
ON training_sessions(scheduled_date);

CREATE TABLE IF NOT EXISTS planning_requests (
    request_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    intent TEXT NOT NULL,
    parameters_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_planning_requests_created_at
ON planning_requests(created_at DESC, request_id DESC);

CREATE TABLE IF NOT EXISTS preference_events (
    event_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    preference_type TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_preference_events_created_at
ON preference_events(created_at DESC, event_id DESC);
"""


def connect_database(path: Path) -> sqlite3.Connection:
    """Open the SQLite database and ensure the schema exists."""

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def upsert_activities(connection: sqlite3.Connection, activities: list[ActivityRecord]) -> None:
    """Insert or update normalized activities by external id."""

    if not activities:
        return

    connection.executemany(
        """
        INSERT INTO activities (
            external_id, activity_date, start_time, name, sport, activity_type,
            distance_km, duration_minutes, training_load, workout_type,
            avg_pace_min_per_km, raw_snapshot_path, last_seen_sync
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
            activity_date = excluded.activity_date,
            start_time = excluded.start_time,
            name = excluded.name,
            sport = excluded.sport,
            activity_type = excluded.activity_type,
            distance_km = excluded.distance_km,
            duration_minutes = excluded.duration_minutes,
            training_load = excluded.training_load,
            workout_type = excluded.workout_type,
            avg_pace_min_per_km = excluded.avg_pace_min_per_km,
            raw_snapshot_path = excluded.raw_snapshot_path,
            last_seen_sync = excluded.last_seen_sync
        """,
        [
            (
                record.external_id,
                record.activity_date,
                record.start_time,
                record.name,
                record.sport,
                record.activity_type,
                record.distance_km,
                record.duration_minutes,
                record.training_load,
                record.workout_type,
                record.avg_pace_min_per_km,
                record.raw_snapshot_path,
                record.last_seen_sync,
            )
            for record in activities
        ],
    )


def upsert_wellness(connection: sqlite3.Connection, wellness_rows: list[WellnessRecord]) -> None:
    """Insert or update normalized wellness rows by local date."""

    if not wellness_rows:
        return

    connection.executemany(
        """
        INSERT INTO wellness (
            local_date, freshness, form, tsb, atl_load, sleep_secs,
            soreness, fatigue, raw_snapshot_path, last_seen_sync
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(local_date) DO UPDATE SET
            freshness = excluded.freshness,
            form = excluded.form,
            tsb = excluded.tsb,
            atl_load = excluded.atl_load,
            sleep_secs = excluded.sleep_secs,
            soreness = excluded.soreness,
            fatigue = excluded.fatigue,
            raw_snapshot_path = excluded.raw_snapshot_path,
            last_seen_sync = excluded.last_seen_sync
        """,
        [
            (
                record.local_date,
                record.freshness,
                record.form,
                record.tsb,
                record.atl_load,
                record.sleep_secs,
                record.soreness,
                record.fatigue,
                record.raw_snapshot_path,
                record.last_seen_sync,
            )
            for record in wellness_rows
        ],
    )


def replace_daily_metrics(
    connection: sqlite3.Connection,
    metrics: list[DailyMetricRecord],
) -> None:
    """Replace the derived daily metrics snapshot."""

    connection.execute("DELETE FROM daily_metrics")
    if not metrics:
        return

    _insert_daily_metrics(connection, metrics)


def replace_daily_metrics_from(
    connection: sqlite3.Connection,
    *,
    start_date: str,
    metrics: list[DailyMetricRecord],
) -> None:
    """Replace derived metrics for one date range while keeping older rows intact."""

    connection.execute(
        "DELETE FROM daily_metrics WHERE local_date >= ?",
        (start_date,),
    )
    if not metrics:
        return

    _insert_daily_metrics(connection, metrics)


def _insert_daily_metrics(
    connection: sqlite3.Connection,
    metrics: list[DailyMetricRecord],
) -> None:
    """Insert a prepared batch of derived daily metrics rows."""

    connection.executemany(
        """
        INSERT INTO daily_metrics (
            local_date, total_distance_7d, total_duration_7d, total_distance_14d,
            total_duration_14d, total_distance_28d, total_duration_28d,
            avg_load_7d, avg_load_14d, avg_load_28d, acute_load, chronic_load,
            acute_chronic_ratio, days_since_threshold, days_since_hard,
            days_since_long, quality_sessions_7d, quality_sessions_14d,
            longest_run_14d, longest_run_28d, form, form_source, fatigue,
            sleep, soreness, readiness, recovery_flag, last_workout_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.local_date,
                row.total_distance_7d,
                row.total_duration_7d,
                row.total_distance_14d,
                row.total_duration_14d,
                row.total_distance_28d,
                row.total_duration_28d,
                row.avg_load_7d,
                row.avg_load_14d,
                row.avg_load_28d,
                row.acute_load,
                row.chronic_load,
                row.acute_chronic_ratio,
                row.days_since_threshold,
                row.days_since_hard,
                row.days_since_long,
                row.quality_sessions_7d,
                row.quality_sessions_14d,
                row.longest_run_14d,
                row.longest_run_28d,
                row.form,
                row.form_source,
                row.fatigue,
                row.sleep,
                row.soreness,
                row.readiness,
                row.recovery_flag,
                row.last_workout_type,
            )
            for row in metrics
        ],
    )


def upsert_check_in(connection: sqlite3.Connection, check_in: CheckInRecord) -> None:
    """Insert or update a manual daily check-in."""

    connection.execute(
        """
        INSERT INTO check_ins (local_date, energy, soreness, sleep, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(local_date) DO UPDATE SET
            energy = excluded.energy,
            soreness = excluded.soreness,
            sleep = excluded.sleep,
            notes = excluded.notes,
            updated_at = excluded.updated_at
        """,
        (
            check_in.local_date,
            check_in.energy,
            check_in.soreness,
            check_in.sleep,
            check_in.notes,
            check_in.updated_at,
        ),
    )


def insert_training_session(
    connection: sqlite3.Connection,
    session: TrainingSessionRecord,
) -> None:
    """Persist or update a scheduled training session."""

    connection.execute(
        """
        INSERT INTO training_sessions (
            session_id, created_at, scheduled_date, domain,
            session_type, title, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            created_at = excluded.created_at,
            scheduled_date = excluded.scheduled_date,
            domain = excluded.domain,
            session_type = excluded.session_type,
            title = excluded.title,
            payload_json = excluded.payload_json
        """,
        (
            session.session_id,
            session.created_at,
            session.scheduled_date,
            session.domain,
            session.session_type,
            session.title,
            json.dumps(session.payload, sort_keys=True),
        ),
    )


def fetch_training_session(
    connection: sqlite3.Connection,
    session_id: str,
) -> sqlite3.Row | None:
    """Fetch one scheduled training session by id."""

    return connection.execute(
        "SELECT * FROM training_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()


def insert_planning_request(
    connection: sqlite3.Connection,
    request: PlanningRequestRecord,
) -> None:
    """Persist or update a structured planning request."""

    connection.execute(
        """
        INSERT INTO planning_requests (
            request_id, created_at, intent, parameters_json
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(request_id) DO UPDATE SET
            created_at = excluded.created_at,
            intent = excluded.intent,
            parameters_json = excluded.parameters_json
        """,
        (
            request.request_id,
            request.created_at,
            request.intent,
            json.dumps(request.parameters, sort_keys=True),
        ),
    )


def fetch_planning_request(
    connection: sqlite3.Connection,
    request_id: str,
) -> sqlite3.Row | None:
    """Fetch one persisted planning request."""

    return connection.execute(
        "SELECT * FROM planning_requests WHERE request_id = ?",
        (request_id,),
    ).fetchone()


def insert_preference_event(
    connection: sqlite3.Connection,
    event: PreferenceEventRecord,
) -> None:
    """Persist or update a captured preference event."""

    connection.execute(
        """
        INSERT INTO preference_events (
            event_id, created_at, preference_type, details_json
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            created_at = excluded.created_at,
            preference_type = excluded.preference_type,
            details_json = excluded.details_json
        """,
        (
            event.event_id,
            event.created_at,
            event.preference_type,
            json.dumps(event.details, sort_keys=True),
        ),
    )


def fetch_preference_event(
    connection: sqlite3.Connection,
    event_id: str,
) -> sqlite3.Row | None:
    """Fetch one persisted preference event."""

    return connection.execute(
        "SELECT * FROM preference_events WHERE event_id = ?",
        (event_id,),
    ).fetchone()


def insert_plan(
    connection: sqlite3.Connection,
    *,
    created_at: str,
    mode: str,
    target_date: str,
    summary: str,
    rationale: dict[str, Any],
    inputs: dict[str, Any],
    output: dict[str, Any],
    items: list[dict[str, Any]],
) -> int:
    """Persist a generated plan and its individual suggested workouts."""

    cursor = connection.execute(
        """
        INSERT INTO plans (created_at, mode, target_date, summary, rationale_json, inputs_json, output_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            created_at,
            mode,
            target_date,
            summary,
            json.dumps(rationale, sort_keys=True),
            json.dumps(inputs, sort_keys=True),
            json.dumps(output, sort_keys=True),
        ),
    )
    plan_id = int(cursor.lastrowid)
    connection.executemany(
        """
        INSERT INTO plan_items (
            plan_id, position, scheduled_date, workout_name, workout_type,
            warmup, main_set, cooldown, notes, rationale
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                plan_id,
                index,
                item["scheduled_date"],
                item["workout_name"],
                item["workout_type"],
                item["warmup"],
                item["main_set"],
                item["cooldown"],
                item["notes"],
                item["rationale"],
            )
            for index, item in enumerate(items, start=1)
        ],
    )
    return plan_id


def fetch_plan_items(connection: sqlite3.Connection, plan_id: int) -> list[sqlite3.Row]:
    """Fetch plan items for one persisted plan in order."""

    return connection.execute(
        """
        SELECT * FROM plan_items
        WHERE plan_id = ?
        ORDER BY position ASC
        """,
        (plan_id,),
    ).fetchall()


def fetch_latest_weekly_plan_id_for_range(
    connection: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
) -> int | None:
    """Return the newest weekly plan with items inside a target date range."""

    row = connection.execute(
        """
        SELECT plans.id AS plan_id
        FROM plans
        WHERE plans.mode = 'weekly'
          AND EXISTS (
              SELECT 1
              FROM plan_items
              WHERE plan_items.plan_id = plans.id
                AND plan_items.scheduled_date BETWEEN ? AND ?
          )
        ORDER BY plans.created_at DESC, plans.id DESC
        LIMIT 1
        """,
        (start_date, end_date),
    ).fetchone()
    if row is None:
        return None
    return int(row["plan_id"])


def fetch_activities(
    connection: sqlite3.Connection,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Fetch normalized activities ordered from newest to oldest."""

    clauses: list[str] = []
    parameters: list[Any] = []
    if start_date is not None:
        clauses.append("activity_date >= ?")
        parameters.append(start_date)
    if end_date is not None:
        clauses.append("activity_date <= ?")
        parameters.append(end_date)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
    query = (
        "SELECT * FROM activities "
        f"{where_clause} "
        "ORDER BY activity_date DESC, start_time DESC "
        f"{limit_clause}"
    )
    return connection.execute(query, parameters).fetchall()


def fetch_all_activities(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch all activities ordered from oldest to newest."""

    return connection.execute(
        "SELECT * FROM activities ORDER BY activity_date ASC, start_time ASC"
    ).fetchall()


def fetch_activities_between_ascending(
    connection: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
) -> list[sqlite3.Row]:
    """Fetch activities for one date range in chronological order."""

    return connection.execute(
        """
        SELECT * FROM activities
        WHERE activity_date BETWEEN ? AND ?
        ORDER BY activity_date ASC, start_time ASC
        """,
        (start_date, end_date),
    ).fetchall()


def fetch_all_wellness(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch all wellness rows ordered from oldest to newest."""

    return connection.execute(
        "SELECT * FROM wellness ORDER BY local_date ASC"
    ).fetchall()


def fetch_wellness_between(
    connection: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
) -> list[sqlite3.Row]:
    """Fetch wellness rows for one date range in chronological order."""

    return connection.execute(
        """
        SELECT * FROM wellness
        WHERE local_date BETWEEN ? AND ?
        ORDER BY local_date ASC
        """,
        (start_date, end_date),
    ).fetchall()


def fetch_all_check_ins(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch all check-ins ordered from oldest to newest."""

    return connection.execute(
        "SELECT * FROM check_ins ORDER BY local_date ASC"
    ).fetchall()


def fetch_check_ins_between(
    connection: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
) -> list[sqlite3.Row]:
    """Fetch check-ins for one date range in chronological order."""

    return connection.execute(
        """
        SELECT * FROM check_ins
        WHERE local_date BETWEEN ? AND ?
        ORDER BY local_date ASC
        """,
        (start_date, end_date),
    ).fetchall()


def fetch_latest_daily_metric(
    connection: sqlite3.Connection,
    on_or_before: str | None = None,
) -> sqlite3.Row | None:
    """Fetch the latest derived metrics row on or before a date."""

    if on_or_before is None:
        return connection.execute(
            "SELECT * FROM daily_metrics ORDER BY local_date DESC LIMIT 1"
        ).fetchone()
    return connection.execute(
        """
        SELECT * FROM daily_metrics
        WHERE local_date <= ?
        ORDER BY local_date DESC
        LIMIT 1
        """,
        (on_or_before,),
    ).fetchone()


def fetch_daily_metrics_between(
    connection: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> list[sqlite3.Row]:
    """Fetch daily metrics for a date range."""

    return connection.execute(
        """
        SELECT * FROM daily_metrics
        WHERE local_date BETWEEN ? AND ?
        ORDER BY local_date ASC
        """,
        (start_date, end_date),
    ).fetchall()


def fetch_latest_wellness(
    connection: sqlite3.Connection,
    on_or_before: str | None = None,
) -> sqlite3.Row | None:
    """Fetch the latest wellness row on or before a date."""

    if on_or_before is None:
        return connection.execute(
            "SELECT * FROM wellness ORDER BY local_date DESC LIMIT 1"
        ).fetchone()
    return connection.execute(
        """
        SELECT * FROM wellness
        WHERE local_date <= ?
        ORDER BY local_date DESC
        LIMIT 1
        """,
        (on_or_before,),
    ).fetchone()


def fetch_latest_check_in(
    connection: sqlite3.Connection,
    on_or_before: str | None = None,
) -> sqlite3.Row | None:
    """Fetch the latest check-in row on or before a date."""

    if on_or_before is None:
        return connection.execute(
            "SELECT * FROM check_ins ORDER BY local_date DESC LIMIT 1"
        ).fetchone()
    return connection.execute(
        """
        SELECT * FROM check_ins
        WHERE local_date <= ?
        ORDER BY local_date DESC
        LIMIT 1
        """,
        (on_or_before,),
    ).fetchone()


def fetch_daily_metric(
    connection: sqlite3.Connection,
    local_date: str,
) -> sqlite3.Row | None:
    """Fetch one derived metrics row."""

    return connection.execute(
        "SELECT * FROM daily_metrics WHERE local_date = ?",
        (local_date,),
    ).fetchone()


def latest_history_date(connection: sqlite3.Connection) -> str | None:
    """Return the most recent date stored in activities or wellness."""

    row = connection.execute(
        """
        SELECT MAX(stored_date) AS latest_date
        FROM (
            SELECT MAX(activity_date) AS stored_date FROM activities
            UNION ALL
            SELECT MAX(local_date) AS stored_date FROM wellness
            UNION ALL
            SELECT MAX(local_date) AS stored_date FROM check_ins
        )
        """
    ).fetchone()
    if row is None:
        return None
    return row["latest_date"]


def row_count(connection: sqlite3.Connection, table_name: str) -> int:
    """Return a table row count for tests and lightweight summaries."""

    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"])

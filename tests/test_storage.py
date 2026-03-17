import json
import tempfile
import unittest
from pathlib import Path

from coach import storage


class StorageGenericPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "storage.db"
        self.connection = storage.connect_database(self.db_path)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def test_schema_includes_generic_tables(self) -> None:
        required_tables = [
            "training_sessions",
            "planning_requests",
            "preference_events",
        ]
        cursor = self.connection.cursor()
        for table_name in required_tables:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (table_name,),
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row, f"{table_name} table should exist")
            self.assertEqual(row[0], table_name)

    def test_insert_and_fetch_training_session(self) -> None:
        session = storage.TrainingSessionRecord(
            session_id="session-1",
            created_at="2026-03-16T08:00:00Z",
            scheduled_date="2026-03-17",
            domain="run",
            session_type="intervals",
            title="Test intervals",
            payload={"duration": 45, "goal_tags": ["VO2"], "notes": "test"},
        )
        storage.insert_training_session(self.connection, session)
        fetched = storage.fetch_training_session(self.connection, session.session_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["session_id"], session.session_id)
        self.assertEqual(fetched["domain"], session.domain)
        stored_payload = json.loads(fetched["payload_json"])
        self.assertEqual(stored_payload, session.payload)

    def test_insert_and_fetch_planning_request(self) -> None:
        request = storage.PlanningRequestRecord(
            request_id="plan-req",
            created_at="2026-03-16T09:00:00Z",
            intent="weekly",
            parameters={"target_date": "2026-03-23", "focus": "run"},
        )
        storage.insert_planning_request(self.connection, request)
        fetched = storage.fetch_planning_request(self.connection, request.request_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["request_id"], request.request_id)
        self.assertEqual(fetched["intent"], request.intent)
        self.assertEqual(json.loads(fetched["parameters_json"]), request.parameters)

    def test_insert_and_fetch_preference_event(self) -> None:
        event = storage.PreferenceEventRecord(
            event_id="pref-1",
            created_at="2026-03-16T10:00:00Z",
            preference_type="strength_placement",
            details={"day": "Thursday", "type": "strength"},
        )
        storage.insert_preference_event(self.connection, event)
        fetched = storage.fetch_preference_event(self.connection, event.event_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["event_id"], event.event_id)
        self.assertEqual(fetched["preference_type"], event.preference_type)
        self.assertEqual(json.loads(fetched["details_json"]), event.details)

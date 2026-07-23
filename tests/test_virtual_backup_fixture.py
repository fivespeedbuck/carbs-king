import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from app_defaults import DEFAULT_FOODS, DEFAULT_SUPPLEMENTS  # noqa: E402
from training_models import TRAINING_SCHEMA_VERSION, TrainingSession  # noqa: E402
from tools.generate_virtual_100_day_backup import (  # noqa: E402
    END_DATE,
    EXPECTED_DAYS,
    OUTPUT_PATH,
    START_DATE,
    generate_payload,
    summarize_payload,
    verify_with_backup_service,
    write_backup,
)


class VirtualBackupFixtureTests(unittest.TestCase):
    def test_payload_is_deterministic_complete_and_continuous(self):
        first = generate_payload()
        second = generate_payload()

        self.assertEqual(first, second)
        self.assertEqual(first["format"], "carbs_king_backup")
        self.assertEqual(first["backup_version"], 2)
        self.assertEqual(first["food_library"], DEFAULT_FOODS)
        self.assertEqual(first["supplement_library"], DEFAULT_SUPPLEMENTS)

        stats = summarize_payload(first)
        self.assertEqual(stats.record_days, EXPECTED_DAYS)
        self.assertEqual(stats.first_date, START_DATE.isoformat())
        self.assertEqual(stats.last_date, END_DATE.isoformat())
        self.assertEqual(stats.training_days, 72)
        self.assertEqual(stats.strength_days, 58)
        self.assertEqual(stats.cardio_days, 14)
        self.assertEqual(stats.rest_days, 28)
        self.assertEqual(stats.diet_days, EXPECTED_DAYS)
        self.assertEqual(stats.circumference_days, 16)
        self.assertEqual(stats.day_types, {"中碳日": 28, "低碳日": 28, "高碳日": 44})

    def test_every_day_has_body_diet_recovery_and_canonical_training(self):
        payload = generate_payload()
        records = payload["daily_records"]
        strength_sessions = []
        for record_date, record in records.items():
            self.assertIn(record["profile"]["day_type"], {"高碳日", "中碳日", "低碳日"})
            self.assertTrue(any(record["meals"].values()))
            self.assertGreater(record["daily_total"]["kcal"], 0)
            self.assertGreater(record["water"]["total_ml"], 0)
            self.assertGreater(record["sleep"]["total_minutes"], 0)
            self.assertIsNone(record["training"]["session"])
            for raw_session in record["training"]["sessions"]:
                session = TrainingSession.from_dict(raw_session)
                self.assertEqual(session.date, record_date)
                self.assertEqual(session.status, "completed")
                self.assertTrue(session.started_at)
                self.assertTrue(session.ended_at)
                self.assertGreater(session.total_duration_min or 0, 0)
                if all(exercise.recording_mode == "strength" for exercise in session.exercises):
                    strength_sessions.append(session)
                    self.assertTrue(all(training_set.completed for exercise in session.exercises for training_set in exercise.sets))
                else:
                    self.assertTrue(all(exercise.completed for exercise in session.exercises))

        self.assertTrue(strength_sessions)
        self.assertLess(records[END_DATE.isoformat()]["profile"]["weight_kg"], records[START_DATE.isoformat()]["profile"]["weight_kg"])
        self.assertLess(records[END_DATE.isoformat()]["profile"]["bodyfat_percent"], records[START_DATE.isoformat()]["profile"]["bodyfat_percent"])
        self.assertEqual(payload["training_data"]["schema_version"], TRAINING_SCHEMA_VERSION)
        self.assertEqual(payload["training_data"]["sessions"], [])

    def test_current_backup_service_validates_and_replace_imports_fixture(self):
        stats = verify_with_backup_service(generate_payload())

        self.assertEqual(stats.record_days, EXPECTED_DAYS)
        self.assertEqual(stats.training_days, 72)
        self.assertEqual(stats.rest_days, 28)
        self.assertEqual(stats.diet_days, EXPECTED_DAYS)

    def test_final_fixture_matches_generator_and_also_round_trips(self):
        with tempfile.TemporaryDirectory() as temp:
            output, stats = write_backup(Path(temp) / "virtual-backup.json")
            written = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(written, generate_payload())
        self.assertEqual(stats.record_days, EXPECTED_DAYS)
        if OUTPUT_PATH.exists():
            self.assertEqual(json.loads(OUTPUT_PATH.read_text(encoding="utf-8")), written)


if __name__ == "__main__":
    unittest.main()

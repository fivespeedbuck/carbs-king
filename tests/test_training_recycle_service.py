import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import training_recycle_service as recycle  # noqa: E402


class TrainingRecycleServiceTests(unittest.TestCase):
    def test_load_purges_entries_after_15_days_and_keeps_recent_ones(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "training_recycle_bin.json"
            with patch.object(recycle, "TRAINING_RECYCLE_BIN_FILE", path):
                recycle.save_json(path, [
                    {"id": "old", "deleted_at": "2026-07-16T11:59:59+08:00"},
                    {"id": "recent", "deleted_at": "2026-07-17T12:00:01+08:00"},
                ])

                items = recycle.load_recycled_training_sessions(
                    now=dt.datetime.fromisoformat("2026-08-01T12:00:00+08:00")
                )

                self.assertEqual([item["id"] for item in items], ["recent"])
                self.assertEqual(recycle.load_json(path, []), items)

    def test_recycle_then_remove_preserves_original_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "training_recycle_bin.json"
            with patch.object(recycle, "TRAINING_RECYCLE_BIN_FILE", path):
                entry = recycle.recycle_training_session(
                    {"id": "session-1", "status": "completed"},
                    original_date="2026-07-31",
                    deleted_at=dt.datetime.now().astimezone().isoformat(),
                )
                removed = recycle.remove_recycled_training_session(entry["id"])

                self.assertEqual(removed["original_date"], "2026-07-31")
                self.assertEqual(removed["session"]["id"], "session-1")
                self.assertEqual(recycle.load_json(path, []), [])

    def test_expiry_label_uses_the_entry_deleted_time(self):
        label = recycle.recycle_expiry_label(
            "2026-08-01T15:20:00+08:00",
            now=dt.datetime.fromisoformat("2026-08-11T15:58:00+08:00"),
        )

        self.assertEqual(label, "4 天后自动清除")


if __name__ == "__main__":
    unittest.main()

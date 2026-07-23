import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_state import AppState
from repositories import JsonRepository


class AppStateTests(unittest.TestCase):
    def test_typed_and_legacy_access_share_one_state(self):
        state = AppState.default(["早餐", "午餐"])
        state["weight"] = "80"
        state.navigation.current_view = "training"
        state["meals"]["早餐"].append({"food": "燕麦"})

        self.assertEqual(state.profile.weight, "80")
        self.assertEqual(state["current_view"], "training")
        self.assertEqual(state.daily.meals["早餐"][0]["food"], "燕麦")

    def test_feature_state_has_explicit_owners(self):
        state = AppState.default([])
        self.assertIs(state["training"], state.daily.training)
        self.assertIs(state["data_page"], state.data_page)
        self.assertIs(state["macro_multipliers"], state.profile.macro_multipliers)


class JsonRepositoryTests(unittest.TestCase):
    def test_repository_preserves_atomic_storage_format(self):
        from storage_service import load_json

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.json"
            repo = JsonRepository(path, dict, lambda value: dict(value) if isinstance(value, dict) else {})
            repo.save({"2026-07-22": {"value": 1}})
            self.assertEqual(repo.load(), {"2026-07-22": {"value": 1}})
            self.assertEqual(load_json(path, {}), repo.load())


if __name__ == "__main__":
    unittest.main()

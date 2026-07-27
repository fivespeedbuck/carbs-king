# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exercise_library import (  # noqa: E402
    EXERCISE_CATEGORIES, EXERCISE_LIBRARY, delete_custom_exercise,
    exercise_catalog, get_exercise, load_custom_exercises, save_custom_exercise,
    search_exercises,
)
from storage_service import load_json, save_json  # noqa: E402


class ExerciseLibraryTests(unittest.TestCase):
    def test_offline_library_has_1324_unique_source_ids(self):
        self.assertEqual(len(EXERCISE_LIBRARY), 1324)
        self.assertEqual(len({item["id"] for item in EXERCISE_LIBRARY}), 1324)
        self.assertTrue(all(str(item["name"]).strip() for item in EXERCISE_LIBRARY))
        self.assertFalse(
            [item["name"] for item in EXERCISE_LIBRARY if re.search(r"[A-Za-z]{3,}", item["name"])],
            "动作正式名称不得残留英文词",
        )
        self.assertFalse([item["name"] for item in EXERCISE_LIBRARY if re.search(r"\s", item["name"])])
        self.assertFalse([item["name"] for item in EXERCISE_LIBRARY if re.search(r"\b(?:bosu|up|to)\b", item["name"], re.I)])

    def test_exercises_have_media_and_complete_core_fields(self):
        required = {"id", "name", "category", "subgroup", "equipment", "target_muscles", "cues", "mistakes", "image", "gif", "default_sets", "recording_mode"}
        for item in EXERCISE_LIBRARY:
            self.assertTrue(required.issubset(item), item["name"])
            self.assertIn(item["category"], EXERCISE_CATEGORIES)
            self.assertTrue(item["target_muscles"])
            self.assertTrue(item["cues"])
            self.assertIn(item["recording_mode"], {"strength", "timed", "cardio"})
        root = Path(__file__).resolve().parents[1]
        for item in (EXERCISE_LIBRARY[0], EXERCISE_LIBRARY[len(EXERCISE_LIBRARY) // 2], EXERCISE_LIBRARY[-1]):
            self.assertTrue(item["image"].startswith("exercises/images/"))
            self.assertTrue(item["gif"].startswith("exercises/gifs/"))
            self.assertTrue((root / "assets" / item["image"]).exists())
            self.assertTrue((root / "assets" / item["gif"]).exists())

    def test_categories_and_search_use_new_offline_catalog(self):
        self.assertEqual(EXERCISE_CATEGORIES[:4], ("胸", "背", "腿", "肩"))
        self.assertIn("臀部", EXERCISE_CATEGORIES)
        chest = search_exercises("", category="胸")
        self.assertTrue(chest)
        self.assertTrue(all(item["category"] == "胸" for item in chest))
        self.assertTrue(search_exercises("仰卧起坐"))

    def test_custom_exercise_keeps_selected_category_equipment_and_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "training_data.json"
            save_json(path, {"active_session": {"keep_until_personal_clear": True}})
            saved = save_custom_exercise({
                "name": "自定义壶铃推举", "category": "肩", "equipment": "壶铃",
                "target_muscles": ["三角肌前束"], "recording_mode": "strength",
                "default_weight_kg": 12, "default_reps": 10, "default_sets": 4,
                "cues": ["躯干稳定"], "mistakes": ["腰部代偿"],
            }, path)
            loaded = load_custom_exercises(path)
            self.assertEqual(saved["category"], "肩")
            self.assertEqual(saved["equipment"], "壶铃")
            self.assertEqual(search_exercises("自定义壶铃", exercises=exercise_catalog(loaded))[0]["name"], "自定义壶铃推举")
            self.assertTrue(load_json(path, {})["active_session"]["keep_until_personal_clear"])
            self.assertTrue(delete_custom_exercise("自定义壶铃推举", path))

    def test_custom_action_form_uses_selectors(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "training_controller.py").read_text(encoding="utf-8-sig")
        self.assertIn('"训练部位"', source)
        self.assertIn('"目标肌群"', source)
        self.assertIn('"器械"', source)
        self.assertIn('"category": str(body_part.value', source)
        self.assertIn('"equipment": str(equipment.value', source)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exercise_library import (  # noqa: E402
    EXERCISE_CATEGORIES,
    EXERCISE_LIBRARY,
    get_exercise,
    search_exercises,
)


class ExerciseLibraryTests(unittest.TestCase):
    def test_library_has_exactly_106_unique_exercises(self):
        names = [exercise["name"] for exercise in EXERCISE_LIBRARY]

        self.assertEqual(len(names), 106)
        self.assertEqual(len(set(names)), 106)

    def test_every_exercise_has_complete_valid_fields(self):
        required = {
            "name", "category", "equipment", "target_muscles", "cues", "mistakes",
            "default_weight_kg", "default_reps", "default_sets",
        }
        allowed_equipment = {"杠铃", "哑铃", "器械", "绳索", "自重", "其他"}

        for exercise in EXERCISE_LIBRARY:
            self.assertEqual(set(exercise), required, exercise["name"])
            self.assertIn(exercise["category"], EXERCISE_CATEGORIES)
            self.assertIn(exercise["equipment"], allowed_equipment)
            self.assertTrue(exercise["target_muscles"])
            self.assertEqual(len(exercise["cues"]), 3, exercise["name"])
            self.assertEqual(len(exercise["mistakes"]), 3, exercise["name"])
            self.assertTrue(all(item.strip() for item in exercise["cues"]))
            self.assertTrue(all(item.strip() for item in exercise["mistakes"]))
            self.assertGreater(exercise["default_sets"], 0)

    def test_categories_are_complete_and_category_filter_works(self):
        self.assertEqual(EXERCISE_CATEGORIES, ("胸", "背", "肩", "腿", "二头", "三头", "腹", "有氧"))

        chest_results = search_exercises("", category="胸")
        self.assertEqual(len(chest_results), 13)
        self.assertTrue(all(exercise["category"] == "胸" for exercise in chest_results))
        self.assertEqual(search_exercises("杠铃卧推", category="背"), [])

    def test_searches_name_and_target_muscles(self):
        self.assertEqual(search_exercises(" 杠铃 卧推 ")[0]["name"], "杠铃卧推")

        lat_results = search_exercises("背阔肌")
        self.assertIn("高位下拉", {exercise["name"] for exercise in lat_results})
        self.assertTrue(all("背阔肌" in exercise["target_muscles"] for exercise in lat_results))

        shoulder_results = search_exercises("三角肌后束", category="肩")
        self.assertIn("反向蝴蝶机飞鸟", {exercise["name"] for exercise in shoulder_results})

    def test_get_exercise_returns_exact_match_or_none(self):
        exercise = get_exercise("  EZ杠弯举  ")

        self.assertIsNotNone(exercise)
        self.assertEqual(exercise["category"], "二头")
        self.assertIsNone(get_exercise("不存在的动作"))


if __name__ == "__main__":
    unittest.main()

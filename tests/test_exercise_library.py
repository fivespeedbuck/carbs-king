# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exercise_library import (  # noqa: E402
    EXERCISE_CATEGORIES,
    EXERCISE_LIBRARY,
    delete_custom_exercise,
    exercise_catalog,
    get_exercise,
    load_custom_exercises,
    save_custom_exercise,
    search_exercises,
)
from storage_service import load_json, save_json  # noqa: E402


class ExerciseLibraryTests(unittest.TestCase):
    def test_library_has_exactly_106_unique_exercises(self):
        names = [exercise["name"] for exercise in EXERCISE_LIBRARY]

        self.assertEqual(len(names), 106)
        self.assertEqual(len(set(names)), 106)

    def test_every_exercise_has_complete_valid_fields(self):
        required = {
            "name", "category", "equipment", "target_muscles", "cues", "mistakes",
            "default_weight_kg", "default_reps", "default_sets", "recording_mode",
            "distance_enabled", "cardio_metric_fields", "aliases",
            "default_duration_seconds",
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
            self.assertIn(exercise["recording_mode"], {"strength", "timed", "cardio"})

    def test_builtin_modes_and_machine_specific_cardio_fields_are_explicit(self):
        treadmill = get_exercise("跑步机爬坡")
        bike = get_exercise("动感单车")
        elliptical = get_exercise("椭圆机")
        stair = get_exercise("登阶机")
        plank = get_exercise("平板支撑")

        self.assertEqual(treadmill["recording_mode"], "cardio")
        self.assertEqual(treadmill["cardio_metric_fields"], ["speed_kph", "incline_percent"])
        self.assertEqual(bike["cardio_metric_fields"], ["resistance_level", "cadence_rpm"])
        self.assertEqual(elliptical["cardio_metric_fields"], ["resistance_level", "strides_per_minute"])
        self.assertEqual(stair["cardio_metric_fields"], ["resistance_level", "steps_per_minute"])
        self.assertEqual(plank["recording_mode"], "timed")
        self.assertEqual(plank["default_duration_seconds"], 45)
        self.assertEqual(search_exercises("爬楼机")[0]["name"], "登阶机")

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

    def test_custom_exercise_guidance_persists_and_is_searchable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "training_data.json"
            save_json(path, {"active_session": {"keep_until_personal_clear": True}})
            saved = save_custom_exercise({
                "name": "地雷管侧向推",
                "recording_mode": "strength",
                "default_weight_kg": 20,
                "default_reps": 12,
                "default_sets": 4,
                "cues": ["髋部保持稳定", "沿斜上方推出"],
                "mistakes": ["腰部旋转代偿"],
            }, path)

            loaded = load_custom_exercises(path)
            catalog = exercise_catalog(loaded)

            self.assertEqual(saved["cues"], ["髋部保持稳定", "沿斜上方推出"])
            self.assertEqual(loaded[0]["mistakes"], ["腰部旋转代偿"])
            self.assertEqual(search_exercises("地雷管", exercises=catalog)[0]["name"], "地雷管侧向推")
            self.assertEqual(search_exercises("", category="自定义", exercises=catalog), loaded)
            self.assertTrue(load_json(path, {})["active_session"]["keep_until_personal_clear"])

            with self.assertRaisesRegex(ValueError, "动作名称已存在"):
                save_custom_exercise({"name": "地雷管侧向推"}, path)

    def test_custom_action_form_collects_guidance_and_saves_to_library(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "training_controller.py").read_text(encoding="utf-8-sig")

        self.assertIn('"动作诀窍（每行一条）"', source)
        self.assertIn('"注意点（每行一条）"', source)
        self.assertIn("save_custom_exercise(custom_spec)", source)
        self.assertIn('save_label="保存并加入训练" if is_new_custom else "加入训练"', source)

    def test_deleting_custom_definition_keeps_session_payload_and_rejects_builtin(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "training_data.json"
            save_json(path, {"active_session": {"exercises": [{"name": "自定义跑步"}]}})
            save_custom_exercise({"name": "自定义跑步"}, path)

            self.assertTrue(delete_custom_exercise("自定义跑步", path))
            self.assertFalse(load_custom_exercises(path))
            self.assertEqual(load_json(path, {})["active_session"]["exercises"][0]["name"], "自定义跑步")
            self.assertFalse(delete_custom_exercise(EXERCISE_LIBRARY[0]["name"], path))


if __name__ == "__main__":
    unittest.main()

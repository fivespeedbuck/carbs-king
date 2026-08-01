# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from assemble_exercise_catalog import category_for, normalize_equipment_display_name, subgroup_for  # noqa: E402
from exercise_library import (  # noqa: E402
    EXERCISE_CATEGORIES, EXERCISE_LIBRARY, delete_custom_exercise,
    exercise_catalog, get_exercise, load_custom_exercises, save_custom_exercise,
    search_exercises, search_exercises_with_fallback,
)
from storage_service import load_json, save_json  # noqa: E402


class ExerciseLibraryTests(unittest.TestCase):
    def test_offline_library_keeps_1324_source_ids_and_curated_additions(self):
        self.assertEqual(len(EXERCISE_LIBRARY), 1326)
        self.assertEqual(len({item["id"] for item in EXERCISE_LIBRARY}), 1326)
        self.assertEqual(len({item["id"] for item in EXERCISE_LIBRARY if item["id"].startswith("dataset:")}), 1324)
        self.assertEqual(len({item["name"] for item in EXERCISE_LIBRARY}), 1326)
        self.assertTrue(all(str(item["name"]).strip() for item in EXERCISE_LIBRARY))
        self.assertFalse(
            [item["name"] for item in EXERCISE_LIBRARY if re.search(r"[A-Za-z]{3,}", item["name"])],
            "动作正式名称不得残留英文词",
        )
        self.assertFalse([item["name"] for item in EXERCISE_LIBRARY if re.search(r"\s", item["name"])])
        self.assertFalse([item["name"] for item in EXERCISE_LIBRARY if re.search(r"\b(?:bosu|up|to)\b", item["name"], re.I)])
        self.assertFalse(
            [item["name"] for item in EXERCISE_LIBRARY if any(term in item["name"] for term in ("杠杆式", "雪橇", "侧to侧", "仰卧仰卧", "小腿小腿"))]
        )
        self.assertFalse(
            [alias for item in EXERCISE_LIBRARY for alias in item.get("aliases", []) if re.search(r"[A-Za-z]{3,}", alias)],
            "搜索关联只保留中文常用叫法",
        )

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

    def test_standard_barbell_squat_keeps_upstream_record_and_common_search_names(self):
        squat = get_exercise("杠铃深蹲")
        self.assertIsNotNone(squat)
        self.assertEqual(squat["id"], "dataset:0043")
        self.assertEqual(squat["category"], "腿")
        self.assertEqual(squat["equipment"], "杠铃")
        self.assertEqual(squat["gif"], "exercises/gifs/0043-qXTaZnJ.gif")
        for query in ("杠铃深蹲", "标准杠铃深蹲", "杠铃全程深蹲", "杠铃后蹲"):
            self.assertEqual(search_exercises(query, category="腿")[0]["id"], "dataset:0043")

    def test_compound_leg_actions_are_not_classified_as_glute_actions(self):
        by_id = {item["id"]: item for item in EXERCISE_LIBRARY}
        for item_id in ("dataset:0043", "dataset:0739", "dataset:0760", "dataset:0032"):
            self.assertEqual(by_id[item_id]["category"], "腿", item_id)
        self.assertEqual(by_id["dataset:0739"]["subgroup"], "股四头肌")
        self.assertEqual(by_id["dataset:0032"]["subgroup"], "腘绳肌")
        for item_id in ("dataset:1409", "dataset:3236"):
            self.assertEqual(by_id[item_id]["category"], "臀部", item_id)

    def test_import_rule_uses_movement_pattern_before_glute_target(self):
        leg_press = {"category": "upper legs", "target": "glutes", "name": "sled 45 leg press"}
        glute_bridge = {"category": "upper legs", "target": "glutes", "name": "barbell glute bridge"}
        self.assertEqual(category_for(leg_press), "腿")
        self.assertEqual(subgroup_for(leg_press, "腿"), "股四头肌")
        self.assertEqual(category_for(glute_bridge), "臀部")

    def test_generated_catalog_uses_familiar_machine_names(self):
        self.assertEqual(normalize_equipment_display_name("杠杆式胸推", "悍马机"), "悍马机胸推")
        self.assertEqual(normalize_equipment_display_name("雪橇45度腿举", "倒蹬机"), "倒蹬机45度腿举")

    def test_common_gym_terms_find_reviewed_actions(self):
        expected = {
            "倒蹬": "dataset:0739",
            "腿推": "dataset:0739",
            "坐姿腿屈伸": "dataset:0585",
            "哑铃推肩": "dataset:0405",
            "杠铃实力推": "dataset:1456",
            "哑铃上斜推胸": "dataset:0314",
            "站姿下夹": "dataset:0155",
            "蝴蝶机夹胸": "dataset:0596",
            "反向蝴蝶机飞鸟": "dataset:0602",
            "大剪刀": "dataset:0579",
            "鹦鹉螺": "dataset:2285",
        }
        for query, expected_id in expected.items():
            with self.subTest(query=query):
                self.assertIn(expected_id, {item["id"] for item in search_exercises(query)})
        self.assertIn("dataset:0251", {item["id"] for item in search_exercises("双杠臂屈伸", category="胸")})

        first_results = {
            "倒蹬": "dataset:0739",
            "腿推": "dataset:0739",
            "哑铃推肩": "dataset:0405",
            "双杠臂屈伸": "dataset:0251",
            "大剪刀": "dataset:0579",
        }
        for query, expected_id in first_results.items():
            with self.subTest(first_result=query):
                self.assertEqual(search_exercises(query)[0]["id"], expected_id)

        self.assertEqual(search_exercises("站姿器械下夹胸")[0]["id"], "curated:standing-machine-lower-chest-fly")
        self.assertEqual(search_exercises("站姿器械侧平举")[0]["id"], "curated:standing-machine-lateral-raise")

    def test_common_machine_titles_and_filters_are_user_facing(self):
        by_id = {item["id"]: item for item in EXERCISE_LIBRARY}
        self.assertEqual(by_id["dataset:0739"]["name"], "45度倒蹬")
        self.assertEqual(by_id["dataset:0739"]["equipment"], "倒蹬机")
        self.assertEqual(by_id["dataset:0585"]["name"], "坐姿腿屈伸")
        self.assertEqual(by_id["dataset:0596"]["equipment"], "蝴蝶机")
        self.assertEqual(by_id["dataset:0602"]["name"], "反向蝴蝶机飞鸟")
        self.assertEqual(by_id["dataset:0579"]["equipment"], "大剪刀")
        self.assertEqual(by_id["dataset:2285"]["equipment"], "鹦鹉螺机")
        self.assertEqual(by_id["dataset:0251"]["subgroup"], "下胸")
        self.assertEqual(by_id["curated:standing-machine-lower-chest-fly"]["equipment"], "固定轨迹器械")
        self.assertEqual(by_id["curated:standing-machine-lateral-raise"]["subgroup"], "中束")

    def test_search_relaxes_over_specific_filters_instead_of_showing_blank(self):
        matches, scope = search_exercises_with_fallback("双杠臂屈伸", "胸", "中胸", "杠铃")
        self.assertEqual(scope, "filters")
        self.assertIn("dataset:0251", {item["id"] for item in matches})

        matches, scope = search_exercises_with_fallback("哑铃推肩", "背")
        self.assertEqual(scope, "category")
        self.assertIn("dataset:0405", {item["id"] for item in matches})

        matches, scope = search_exercises_with_fallback("", "腿", "股四头肌", "杠铃")
        self.assertEqual(scope, "")
        self.assertTrue(matches)
        self.assertTrue(all(item["category"] == "腿" and item["subgroup"] == "股四头肌" and item["equipment"] == "杠铃" for item in matches))

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

# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from food_library import FOOD_CATEGORIES, FOOD_LIBRARY, food_catalog, search_foods  # noqa: E402


class FoodLibraryTests(unittest.TestCase):
    def test_offline_food_library_has_complete_macro_data(self):
        self.assertGreaterEqual(len(FOOD_LIBRARY), 1689)
        required = {"id", "food_code", "name", "category", "unit", "base_qty", "kcal", "carb", "protein", "fat"}
        for item in (FOOD_LIBRARY[0], FOOD_LIBRARY[len(FOOD_LIBRARY) // 2], FOOD_LIBRARY[-1]):
            self.assertTrue(required.issubset(item))
            self.assertEqual(item["unit"], "g")
            self.assertEqual(item["base_qty"], 100)
            self.assertIn(item["category"], FOOD_CATEGORIES)

    def test_search_filters_by_name_and_category(self):
        milk = search_foods("炼乳")
        self.assertTrue(milk)
        self.assertTrue(all("炼乳" in item["name"] for item in milk))
        dairy = search_foods(category="乳类及其制品")
        self.assertTrue(dairy)
        self.assertTrue(all(item["category"] == "乳类及其制品" for item in dairy))
        dishes = search_foods(category="外卖/地方菜")
        self.assertTrue(any(item["name"] == "小炒黄牛肉" for item in dishes))
        self.assertTrue(any(item["name"] == "黄焖鸡" for item in dishes))
        self.assertTrue(any(item["subgroup"] == "粤菜" for item in dishes))
        self.assertTrue(any(item["subgroup"] == "新疆菜" for item in dishes))
        breakfast = search_foods(category="早餐/小吃")
        self.assertTrue(any(item["name"] == "杂粮煎饼" for item in breakfast))
        self.assertTrue(any(item["name"] == "皮蛋瘦肉粥" for item in breakfast))
        self.assertTrue(any(item["name"] == "宁波汤圆" for item in dishes))
        self.assertEqual(search_foods("黄焖鸡米饭")[0]["name"], "黄焖鸡")
        self.assertEqual(search_foods("肉包子")[0]["name"], "鲜肉包")
        self.assertEqual(search_foods("荷包蛋")[0]["name"], "荷包蛋")
        self.assertEqual(search_foods("蛋炒饭")[0]["name"], "蛋炒饭")

    def test_user_food_overrides_bundled_name_without_losing_catalog(self):
        first = FOOD_LIBRARY[0]
        customized = {**first, "kcal": 999, "category": "我的食物"}
        catalog = food_catalog([customized, {"name": "自定义食物", "category": "我的食物"}])
        resolved = next(item for item in catalog if item["name"] == first["name"])
        self.assertEqual(resolved["kcal"], 999)
        self.assertEqual(len(catalog), len(FOOD_LIBRARY) + 1)


if __name__ == "__main__":
    unittest.main()

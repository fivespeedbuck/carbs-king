"""Pure nutrition and body-composition calculations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app_defaults import DAY_TYPES, DEFAULT_MACRO_MULTIPLIERS
from app_state import AppState
from app_utils import to_float


@dataclass
class NutritionService:
    body_composition: Callable[[], dict[str, Any]]
    multipliers: Callable[..., dict[str, dict[str, float]]]
    targets: Callable[[], dict[str, float]]
    daily_total: Callable[[], dict[str, float]]
    evaluate: Callable[..., dict[str, Any]]


def create_nutrition_service(state: AppState) -> NutritionService:
    def body_composition():
        weight = to_float(state["weight"], 62.5)
        bodyfat = to_float(state["bodyfat"], 13)
        height = to_float(state.get("height"), 170)
        age = to_float(state.get("age"), 30)
        sex = state.get("sex", "男")

        if bodyfat < 3 or bodyfat > 60:
            bodyfat = 13
        if height < 120 or height > 230:
            height = 170
        if age < 10 or age > 90:
            age = 30

        lean_mass = round(weight * (1 - bodyfat / 100), 1)
        fat_mass = round(weight - lean_mass, 1)

        # Mifflin-St Jeor BMR
        bmr = 10 * weight + 6.25 * height - 5 * age + (5 if sex == "男" else -161)
        bmr = round(bmr, 0)

        activity_habit = state.get("activity_habit", "规律训练")
        activity_factor_map = {
            "久坐少动": 1.25,
            "偶尔运动": 1.35,
            "规律训练": 1.45,
            "高频训练": 1.60,
        }
        activity_factor = activity_factor_map.get(activity_habit, 1.45)
        tdee = round(bmr * activity_factor, 0)

        return {
            "weight": round(weight, 1),
            "bodyfat": round(bodyfat, 1),
            "height": round(height, 1),
            "age": round(age, 0),
            "sex": sex,
            "lean_mass": lean_mass,
            "fat_mass": fat_mass,
            "bmr": bmr,
            "tdee": tdee,
            "activity_habit": activity_habit,
            "activity_factor": activity_factor,
        }

    def automatic_multipliers(comp=None):
        comp = comp or body_composition()
        result = {}
        for day_type, cfg in DAY_TYPES.items():
            carb_gkg = cfg["carb_gkg"]
            if comp["sex"] == "男":
                if comp["bodyfat"] >= 18:
                    carb_gkg -= 0.15
                elif comp["bodyfat"] <= 12:
                    carb_gkg += 0.10
            else:
                if comp["bodyfat"] >= 28:
                    carb_gkg -= 0.15
                elif comp["bodyfat"] <= 20:
                    carb_gkg += 0.10
            if comp["age"] >= 45:
                carb_gkg -= 0.10
            elif comp["age"] <= 25:
                carb_gkg += 0.05
            result[day_type] = {
                "carb": round(carb_gkg, 2),
                "protein": 2.15,
                "fat": round((cfg["fat_gkg_min"] + cfg["fat_gkg_max"]) / 2, 2),
            }
        return result

    def get_multipliers(mode=None):
        selected_mode = mode or state.get("macro_mode", "auto")
        if selected_mode == "auto":
            return automatic_multipliers()
        stored = state.get("macro_multipliers", {})
        stored = stored if isinstance(stored, dict) else {}
        result = {}
        for day_type, defaults in DEFAULT_MACRO_MULTIPLIERS.items():
            values = stored.get(day_type, {})
            values = values if isinstance(values, dict) else {}
            result[day_type] = {
                key: to_float(values.get(key), default)
                for key, default in defaults.items()
            }
        return result

    def get_targets():
        comp = body_composition()
        weight = comp["weight"]
        lean_mass = comp["lean_mass"]
        day_type = state.get("day_type")
        if day_type not in DAY_TYPES:
            day_type = "高碳日"
        cfg = DAY_TYPES[day_type]

        calorie_target = round(comp["tdee"] * cfg["calorie_factor"], 0)

        macro_mode = state.get("macro_mode", "auto")
        if macro_mode == "custom":
            macro_multipliers = get_multipliers("custom")
            day_multipliers = macro_multipliers.get(day_type, {}) if isinstance(macro_multipliers, dict) else {}
            day_multipliers = day_multipliers if isinstance(day_multipliers, dict) else {}
            defaults = DEFAULT_MACRO_MULTIPLIERS.get(day_type, DEFAULT_MACRO_MULTIPLIERS["高碳日"])
            carb_gkg = to_float(day_multipliers.get("carb"), defaults["carb"])
            protein_gkg = to_float(day_multipliers.get("protein"), defaults["protein"])
            fat_gkg = to_float(day_multipliers.get("fat"), defaults["fat"])

            # 自定义值是区间中心：蛋白按去脂体重，其余按当前体重。
            protein_center = lean_mass * protein_gkg
            protein_min = round(max(0, protein_center - lean_mass * 0.15), 1)
            protein_max = round(protein_center + lean_mass * 0.15, 1)
            fat_center = weight * fat_gkg
            fat_min = round(max(0, fat_center - weight * 0.075), 1)
            fat_max = round(fat_center + weight * 0.075, 1)
            carb_center = max(30, round(weight * carb_gkg, 1))
            carb_interval = cfg["carb_interval"]
            carb_min = max(30, round(carb_center - carb_interval, 1))
            carb_max = round(carb_center + carb_interval, 1)
        else:
            # 蛋白：按去脂体重区间估算，2.0-2.3g/kg LBM。
            protein_min = round(lean_mass * 2.0, 1)
            protein_max = round(lean_mass * 2.3, 1)

            # 脂肪：高碳低脂，低碳略高脂；按体重估算。
            fat_min = round(weight * cfg["fat_gkg_min"], 1)
            fat_max = round(weight * cfg["fat_gkg_max"], 1)

            # 碳水：高/中/低碳日 g/kg 核心值 + 体脂、年龄修正。
            carb_gkg = automatic_multipliers(comp)[day_type]["carb"]

            carb_center = max(30, round(weight * carb_gkg, 1))
            carb_interval = cfg["carb_interval"]
            carb_min = max(30, round(carb_center - carb_interval, 1))
            carb_max = round(carb_center + carb_interval, 1)

            if day_type == "高碳日":
                carb_min = max(carb_min, round(weight * 2.5, 1))
                carb_max = min(carb_max, round(weight * 3.4, 1))
            elif day_type == "中碳日":
                carb_min = max(carb_min, round(weight * 1.8, 1))
                carb_max = min(carb_max, round(weight * 2.7, 1))
            else:
                carb_min = max(carb_min, round(weight * 0.9, 1))
                carb_max = min(carb_max, round(weight * 1.7, 1))

        if carb_max < carb_min:
            carb_max = carb_min + 10

        return {
            "carb_min": round(carb_min, 1),
            "carb_max": round(carb_max, 1),
            "carb": round((carb_min + carb_max) / 2, 1),
            "protein_min": protein_min,
            "protein_max": protein_max,
            "protein": round((protein_min + protein_max) / 2, 1),
            "fat_min": fat_min,
            "fat_max": fat_max,
            "lean_mass": lean_mass,
            "fat_mass": comp["fat_mass"],
            "bodyfat": comp["bodyfat"],
            "height": comp["height"],
            "age": comp["age"],
            "sex": comp["sex"],
            "bmr": comp["bmr"],
            "tdee": comp["tdee"],
            "calorie_target": calorie_target,
            "activity_habit": comp["activity_habit"],
            "activity_factor": comp["activity_factor"],
            "macro_mode": macro_mode,
        }

    def daily_total():
        total = {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}
        meals = state.get("meals", {})
        if not isinstance(meals, dict):
            meals = {}
        for items in meals.values():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                for k in total:
                    total[k] += to_float(item.get(k))
        return {k: round(v, 1) for k, v in total.items()}


    def evaluate(total=None):
        if total is None:
            total = daily_total()
        targets = get_targets()
        carb = to_float(total.get("carb"))
        protein = to_float(total.get("protein"))
        fat = to_float(total.get("fat"))
        kcal = to_float(total.get("kcal"))

        def range_msg(value, low, high):
            if low <= value <= high:
                return "达标"
            return "偏高" if value > high else "偏低"

        carb_ok = targets["carb_min"] <= carb <= targets["carb_max"]
        protein_ok = targets["protein_min"] <= protein <= targets["protein_max"]
        fat_ok = targets["fat_min"] <= fat <= targets["fat_max"]

        kcal_target = targets["calorie_target"]
        kcal_diff = round(kcal - kcal_target, 1)

        warnings = []
        if carb < targets["carb_min"] - 10:
            warnings.append(f"碳水不足 {round(targets['carb_min'] - carb, 1):g}g")
        if carb > targets["carb_max"] + 10:
            warnings.append(f"碳水超出 {round(carb - targets['carb_max'], 1):g}g")
        if protein < targets["protein_min"] - 5:
            warnings.append(f"蛋白不足 {round(targets['protein_min'] - protein, 1):g}g")
        if protein > targets["protein_max"] + 15:
            warnings.append(f"蛋白超出 {round(protein - targets['protein_max'], 1):g}g")
        if fat < targets["fat_min"] - 5:
            warnings.append(f"脂肪不足 {round(targets['fat_min'] - fat, 1):g}g")
        if fat > targets["fat_max"] + 5:
            warnings.append(f"脂肪超出 {round(fat - targets['fat_max'], 1):g}g")
        if kcal_diff > 150:
            warnings.append(f"热量超出约 {kcal_diff:g} kcal")

        return {
            "status": "达标" if carb_ok and protein_ok and fat_ok else "未达标",
            "carb_msg": range_msg(carb, targets["carb_min"], targets["carb_max"]),
            "protein_msg": range_msg(protein, targets["protein_min"], targets["protein_max"]),
            "fat_msg": range_msg(fat, targets["fat_min"], targets["fat_max"]),
            "kcal_target": kcal_target,
            "warning_text": "；".join(warnings) if warnings else "无明显超出/不足项",
        }

    return NutritionService(
        body_composition=body_composition,
        multipliers=get_multipliers,
        targets=get_targets,
        daily_total=daily_total,
        evaluate=evaluate,
    )


__all__ = ["NutritionService", "create_nutrition_service"]

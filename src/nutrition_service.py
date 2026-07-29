"""Pure nutrition and body-composition calculations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app_defaults import DAY_TYPES, DEFAULT_MACRO_MULTIPLIERS
from app_state import AppState
from app_utils import to_float


PROFILE_REQUIRED_FIELDS = {
    "weight": "体重",
    "bodyfat": "体脂",
    "height": "身高",
    "age": "年龄",
    "sex": "性别",
    "activity_habit": "运动习惯",
}

CARB_CYCLE_GOALS = ("减脂", "保持", "增肌")

GOAL_CONFIG = {
    "减脂": {
        "calorie_factor": {"高碳日": 0.90, "中碳日": 0.80, "低碳日": 0.70},
        "protein_lbm_gkg": 2.20,
    },
    "保持": {
        "calorie_factor": {"高碳日": 1.10, "中碳日": 1.00, "低碳日": 0.90},
        "protein_lbm_gkg": 2.00,
    },
    "增肌": {
        "calorie_factor": {"高碳日": 1.15, "中碳日": 1.05, "低碳日": 0.95},
        "protein_lbm_gkg": 2.00,
    },
}

# Fat receives a transparent share of each day's target calories.  Carbs close
# the remaining energy, so no hidden upper limit or discarded calories exist.
FAT_CALORIE_SHARE = {"高碳日": 0.25, "中碳日": 0.30, "低碳日": 0.35}


@dataclass
class NutritionService:
    body_composition: Callable[[], dict[str, Any]]
    multipliers: Callable[..., dict[str, dict[str, float]]]
    targets: Callable[[], dict[str, float]]
    daily_total: Callable[[], dict[str, float]]
    evaluate: Callable[..., dict[str, Any]]


def create_nutrition_service(state: AppState) -> NutritionService:
    def normalize_goal(goal: Any) -> str:
        value = str(goal or "").strip()
        return value if value in CARB_CYCLE_GOALS else "减脂"

    def automatic_targets(comp: dict[str, Any], goal: str, day_type: str) -> dict[str, float]:
        config = GOAL_CONFIG[goal]
        calorie_factor = float(config["calorie_factor"][day_type])
        protein_lbm_gkg = float(config["protein_lbm_gkg"])
        fat_calorie_share = FAT_CALORIE_SHARE[day_type]
        calorie_target = round(comp["tdee"] * calorie_factor, 0)
        protein_target = comp["lean_mass"] * protein_lbm_gkg
        fat_target = calorie_target * fat_calorie_share / 9
        carb_target = (calorie_target - protein_target * 4 - fat_target * 9) / 4
        if carb_target <= 0:
            raise ValueError("automatic macro configuration leaves no calories for carbohydrates")
        return {
            "calorie_factor": calorie_factor,
            "calorie_target": calorie_target,
            "protein_lbm_gkg": protein_lbm_gkg,
            "fat_calorie_share": fat_calorie_share,
            "protein": protein_target,
            "fat": fat_target,
            "carb": carb_target,
        }

    def body_composition():
        raw = {key: str(state.get(key, "") or "").strip() for key in PROFILE_REQUIRED_FIELDS}
        missing = [label for key, label in PROFILE_REQUIRED_FIELDS.items() if not raw[key]]
        weight = to_float(raw["weight"], -1)
        bodyfat = to_float(raw["bodyfat"], -1)
        height = to_float(raw["height"], -1)
        age = to_float(raw["age"], -1)
        sex = raw["sex"]
        activity_habit = raw["activity_habit"]
        if weight <= 0 or weight > 500:
            missing.append("体重")
        if not 3 <= bodyfat <= 60:
            missing.append("体脂")
        if not 120 <= height <= 230:
            missing.append("身高")
        if not 10 <= age <= 90:
            missing.append("年龄")
        if sex not in {"男", "女"}:
            missing.append("性别")
        activity_factor_map = {
            "久坐少动": 1.25,
            "偶尔运动": 1.35,
            "规律训练": 1.45,
            "高频训练": 1.60,
        }
        if activity_habit not in activity_factor_map:
            missing.append("运动习惯")
        if missing:
            return {
                "is_ready": False,
                "missing_fields": list(dict.fromkeys(missing)),
                "weight": None, "bodyfat": None, "height": None, "age": None,
                "sex": sex, "lean_mass": None, "fat_mass": None, "bmr": None,
                "tdee": None, "activity_habit": activity_habit, "activity_factor": None,
            }

        lean_mass = round(weight * (1 - bodyfat / 100), 1)
        fat_mass = round(weight - lean_mass, 1)

        # Mifflin-St Jeor BMR
        bmr = 10 * weight + 6.25 * height - 5 * age + (5 if sex == "男" else -161)
        bmr = round(bmr, 0)

        activity_factor = activity_factor_map[activity_habit]
        tdee = round(bmr * activity_factor, 0)

        return {
            "is_ready": True,
            "missing_fields": [],
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
        if not comp["is_ready"]:
            return {}

        goal = normalize_goal(state.get("macro_goal", "减脂"))
        result = {}
        for day_type in DAY_TYPES:
            target = automatic_targets(comp, goal, day_type)
            result[day_type] = {
                "carb": round(target["carb"] / comp["weight"], 2),
                "protein": round(target["protein"] / comp["lean_mass"], 2),
                "fat": round(target["fat"] / comp["weight"], 2),
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
        if not comp["is_ready"]:
            return {
                "is_ready": False,
                "profile_message": f"请完善个人资料：{'、'.join(comp['missing_fields'])}",
                "carb_min": None, "carb_max": None, "carb": None,
                "protein_min": None, "protein_max": None, "protein": None,
                "fat_min": None, "fat_max": None, "fat": None,
                "lean_mass": None, "fat_mass": None, "bodyfat": None,
                "height": None, "age": None, "sex": comp["sex"], "bmr": None,
                "tdee": None, "calorie_target": None,
                "activity_habit": comp["activity_habit"], "activity_factor": None,
                "macro_mode": state.get("macro_mode", "auto"),
                "macro_goal": normalize_goal(state.get("macro_goal", "减脂")),
            }

        weight = comp["weight"]
        lean_mass = comp["lean_mass"]
        day_type = state.get("day_type")
        if day_type not in DAY_TYPES:
            day_type = "高碳日"
        cfg = DAY_TYPES[day_type]

        macro_mode = state.get("macro_mode", "auto")
        macro_goal = normalize_goal(state.get("macro_goal", "减脂"))
        if macro_mode == "custom":
            macro_multipliers = get_multipliers("custom")
            day_multipliers = macro_multipliers.get(day_type, {}) if isinstance(macro_multipliers, dict) else {}
            day_multipliers = day_multipliers if isinstance(day_multipliers, dict) else {}
            defaults = DEFAULT_MACRO_MULTIPLIERS.get(day_type, DEFAULT_MACRO_MULTIPLIERS["高碳日"])
            carb_gkg = to_float(day_multipliers.get("carb"), defaults["carb"])
            protein_gkg = to_float(day_multipliers.get("protein"), defaults["protein"])
            fat_gkg = to_float(day_multipliers.get("fat"), defaults["fat"])

            protein_center = lean_mass * protein_gkg
            protein_min = round(max(0, protein_center - lean_mass * 0.15), 1)
            protein_max = round(protein_center + lean_mass * 0.15, 1)
            fat_center = weight * fat_gkg
            fat_min = round(max(0, fat_center - weight * 0.075), 1)
            fat_max = round(fat_center + weight * 0.075, 1)
            carb_center = max(30, round(weight * carb_gkg, 1))
            calorie_target = round(carb_center * 4 + protein_center * 4 + fat_center * 9, 0)
            calorie_factor = calorie_target / comp["tdee"]
            fat_calorie_share = fat_center * 9 / calorie_target
            carb_interval = cfg["carb_interval"]
            carb_min = max(30, round(carb_center - carb_interval, 1))
            carb_max = round(carb_center + carb_interval, 1)
        else:
            automatic = automatic_targets(comp, macro_goal, day_type)
            calorie_factor = automatic["calorie_factor"]
            calorie_target = automatic["calorie_target"]
            fat_calorie_share = automatic["fat_calorie_share"]
            protein_center = automatic["protein"]
            fat_center = automatic["fat"]
            carb_center = automatic["carb"]
            carb_interval = cfg["carb_interval"]

            protein_spread = 0.15 if macro_goal == "减脂" else 0.10
            fat_spread = 0.05 if macro_goal != "增肌" else 0.04
            protein_min = round(max(0, protein_center - lean_mass * protein_spread), 1)
            protein_max = round(protein_center + lean_mass * protein_spread, 1)
            fat_min = round(max(0, fat_center - weight * fat_spread), 1)
            fat_max = round(fat_center + weight * fat_spread, 1)
            carb_min = max(30, round(carb_center - carb_interval, 1))
            carb_max = round(carb_center + carb_interval, 1)

        if carb_max < carb_min:
            carb_max = carb_min + 10

        return {
            "is_ready": True,
            "carb_min": round(carb_min, 1),
            "carb_max": round(carb_max, 1),
            "carb": round((carb_min + carb_max) / 2, 1),
            "protein_min": protein_min,
            "protein_max": protein_max,
            "protein": round((protein_min + protein_max) / 2, 1),
            "fat_min": fat_min,
            "fat_max": fat_max,
            "fat": round((fat_min + fat_max) / 2, 1),
            "lean_mass": lean_mass,
            "fat_mass": comp["fat_mass"],
            "bodyfat": comp["bodyfat"],
            "height": comp["height"],
            "age": comp["age"],
            "sex": comp["sex"],
            "bmr": comp["bmr"],
            "tdee": comp["tdee"],
            "calorie_target": calorie_target,
            "calorie_factor": round(calorie_factor, 4),
            "fat_calorie_share": round(fat_calorie_share, 4),
            "protein_basis": "lean_mass",
            "activity_habit": comp["activity_habit"],
            "activity_factor": comp["activity_factor"],
            "macro_mode": macro_mode,
            "macro_goal": macro_goal,
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
        if not targets["is_ready"]:
            return {
                "status": "待完善资料",
                "carb_msg": "待完善资料",
                "protein_msg": "待完善资料",
                "fat_msg": "待完善资料",
                "kcal_target": None,
                "warning_text": targets["profile_message"],
            }
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

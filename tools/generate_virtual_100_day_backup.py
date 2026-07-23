"""Generate and verify a deterministic 100-day Carbs King full backup."""

from __future__ import annotations

import argparse
import copy
import json
import math
import random
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app_defaults import DEFAULT_FOODS, DEFAULT_MACRO_MULTIPLIERS, DEFAULT_SUPPLEMENTS  # noqa: E402
from app_state import AppState  # noqa: E402
from backup_service import BackupServiceDependencies, create_backup_service  # noqa: E402
from repositories import AppRepositories, JsonRepository  # noqa: E402
from storage_service import load_json, save_json  # noqa: E402
from training_models import TRAINING_SCHEMA_VERSION, TrainingSession  # noqa: E402


START_DATE = date(2026, 4, 15)
END_DATE = date(2026, 7, 23)
EXPECTED_DAYS = 100
SEED = 20260415
TZ = timezone(timedelta(hours=8))
OUTPUT_PATH = ROOT / "release_candidates" / "carbs-king-virtual-100-days-20260415-20260723.json"
MEALS = ("早餐", "午餐", "晚餐", "练前", "练后", "偷吃")
SCHEDULE = ("胸+三头", "背+二头", "休息", "腿", "肩+腹", "有氧", "休息")
DAY_TYPE_BY_WORKOUT = {
    "胸+三头": "高碳日",
    "背+二头": "高碳日",
    "腿": "高碳日",
    "肩+腹": "中碳日",
    "有氧": "中碳日",
    "休息": "低碳日",
}


STRENGTH_PLANS: dict[str, tuple[tuple[str, str, float, int, int], ...]] = {
    "胸+三头": (
        ("杠铃卧推", "胸", 62.5, 8, 4),
        ("上斜哑铃卧推", "胸", 22.5, 10, 4),
        ("绳索下压", "三头", 22.5, 12, 3),
    ),
    "背+二头": (
        ("高位下拉", "背", 50.0, 10, 4),
        ("坐姿划船", "背", 47.5, 10, 4),
        ("杠铃弯举", "二头", 22.5, 10, 3),
    ),
    "腿": (
        ("杠铃深蹲", "腿", 80.0, 8, 4),
        ("腿举", "腿", 140.0, 10, 4),
        ("罗马尼亚硬拉", "腿", 70.0, 10, 3),
    ),
    "肩+腹": (
        ("哑铃推举", "肩", 17.5, 10, 4),
        ("哑铃侧平举", "肩", 7.5, 12, 4),
        ("绳索卷腹", "腹", 30.0, 15, 3),
    ),
}


@dataclass(frozen=True)
class BackupStats:
    record_days: int
    first_date: str
    last_date: str
    training_days: int
    strength_days: int
    cardio_days: int
    rest_days: int
    diet_days: int
    circumference_days: int
    day_types: dict[str, int]
    food_items: int
    supplement_items: int


def _slug(value: str) -> str:
    return "".join(character if character.isascii() and character.isalnum() else f"{ord(character):x}" for character in value)


def _iso_at(current: date, hour: int, minute: int) -> str:
    return datetime.combine(current, time(hour, minute), TZ).isoformat(timespec="seconds")


def _round_plate(value: float) -> float:
    return round(value / 1.25) * 1.25


def _trend(start: float, end: float, index: int, rng: random.Random, noise: float) -> float:
    if index == 0:
        return start
    if index == EXPECTED_DAYS - 1:
        return end
    progress = index / (EXPECTED_DAYS - 1)
    wave = math.sin(index * 0.61) * noise * 0.55
    jitter = rng.uniform(-noise, noise)
    return start + (end - start) * progress + wave + jitter


def _scaled_food(food: Mapping[str, Any], quantity: float) -> dict[str, Any]:
    base = float(food.get("base_qty") or 1)
    factor = quantity / base
    qty: int | float = int(quantity) if float(quantity).is_integer() else round(quantity, 1)
    return {
        "food": str(food["name"]),
        "qty": qty,
        "unit": str(food.get("unit") or "g"),
        "method": str(food.get("method") or ""),
        "kcal": round(float(food.get("kcal") or 0) * factor, 1),
        "carb": round(float(food.get("carb") or 0) * factor, 1),
        "protein": round(float(food.get("protein") or 0) * factor, 1),
        "fat": round(float(food.get("fat") or 0) * factor, 1),
    }


def _daily_meals(day_type: str, index: int, rng: random.Random) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, float]], dict[str, float]]:
    foods = {str(item["name"]): item for item in DEFAULT_FOODS}
    variation = 1 + rng.choice((-0.04, -0.02, 0.0, 0.02, 0.04))

    def grams(value: float) -> int:
        return max(1, int(round(value * variation / 5) * 5))

    meals: dict[str, list[dict[str, Any]]] = {meal: [] for meal in MEALS}
    meals["早餐"] = [
        _scaled_food(foods["燕麦"], grams(65 if day_type == "高碳日" else 55 if day_type == "中碳日" else 45)),
        _scaled_food(foods["鸡蛋"], 2 if day_type != "低碳日" else 3),
        _scaled_food(foods["无糖酸奶"], grams(180)),
    ]
    rice_lunch = {"高碳日": 300, "中碳日": 220, "低碳日": 100}[day_type]
    rice_dinner = {"高碳日": 250, "中碳日": 160, "低碳日": 80}[day_type]
    meals["午餐"] = [
        _scaled_food(foods["米饭"], grams(rice_lunch)),
        _scaled_food(foods["鸡胸肉"], grams(190 if day_type != "低碳日" else 220)),
        _scaled_food(foods["西兰花"], grams(180)),
        _scaled_food(foods["橄榄油"], 10 if day_type != "低碳日" else 15),
    ]
    dinner_protein = "瘦牛肉" if index % 3 else "三文鱼"
    meals["晚餐"] = [
        _scaled_food(foods["米饭"], grams(rice_dinner)),
        _scaled_food(foods[dinner_protein], grams(170)),
        _scaled_food(foods["生菜"], grams(180)),
    ]
    if day_type != "低碳日":
        meals["练前"] = [_scaled_food(foods["香蕉"], grams(120))]
        meals["练后"] = [_scaled_food(foods["乳清蛋白粉"], 1)]
    else:
        meals["练后"] = [_scaled_food(foods["乳清蛋白粉"], 1)]
    if index % 14 == 12:
        meals["偷吃"] = [_scaled_food(foods["苹果"], grams(150))]

    totals = {meal: {key: 0.0 for key in ("kcal", "carb", "protein", "fat")} for meal in MEALS}
    daily = {key: 0.0 for key in ("kcal", "carb", "protein", "fat")}
    for meal, items in meals.items():
        for item in items:
            for key in daily:
                totals[meal][key] += float(item[key])
                daily[key] += float(item[key])
        totals[meal] = {key: round(value, 1) for key, value in totals[meal].items()}
    return meals, totals, {key: round(value, 1) for key, value in daily.items()}


def _targets(day_type: str, weight: float, bodyfat: float) -> dict[str, float | str]:
    carb_center = {"高碳日": 2.9, "中碳日": 2.3, "低碳日": 1.4}[day_type] * weight
    protein_center = weight * (1 - bodyfat / 100) * 2.15
    fat_center = {"高碳日": 0.78, "中碳日": 0.88, "低碳日": 1.02}[day_type] * weight
    calorie_target = {"高碳日": 2050, "中碳日": 1900, "低碳日": 1750}[day_type]
    return {
        "carb_min": round(carb_center - 15, 1),
        "carb_max": round(carb_center + 15, 1),
        "carb": round(carb_center, 1),
        "protein_min": round(protein_center - 8, 1),
        "protein_max": round(protein_center + 8, 1),
        "protein": round(protein_center, 1),
        "fat_min": round(fat_center - 6, 1),
        "fat_max": round(fat_center + 6, 1),
        "calorie_target": float(calorie_target),
        "macro_mode": "auto",
    }


def _strength_session(current: date, index: int, workout: str, rng: random.Random) -> dict[str, Any]:
    duration = 58 + (index % 5) * 3 + rng.randint(-2, 2)
    start_minute = 20 + (index % 4) * 5
    started = datetime.combine(current, time(18, start_minute), TZ)
    ended = started + timedelta(minutes=duration)
    progression = 1 + 0.12 * index / (EXPECTED_DAYS - 1)
    exercises = []
    for exercise_order, (name, body_part, base_weight, base_reps, set_count) in enumerate(STRENGTH_PLANS[workout], 1):
        exercise_id = f"exercise_{_slug(name)}"
        sets = []
        for set_order in range(1, set_count + 1):
            fatigue_drop = 0 if set_order <= 2 else 1
            weight = _round_plate(base_weight * progression)
            completed_at = started + timedelta(minutes=exercise_order * 12 + set_order * 2)
            sets.append({
                "id": f"set_{current.isoformat()}_{exercise_order}_{set_order}",
                "order": set_order,
                "weight_kg": weight,
                "reps": max(5, base_reps - fatigue_drop),
                "completed": True,
                "warmup": False,
                "rir": 2.0 if set_order < set_count else 1.0,
                "rpe": 8.0 if set_order < set_count else 9.0,
                "note": "",
                "completed_at": completed_at.isoformat(timespec="seconds"),
            })
        exercises.append({
            "id": f"session_exercise_{current.isoformat()}_{exercise_order}",
            "exercise_id": exercise_id,
            "name": name,
            "body_part": body_part,
            "order": exercise_order,
            "sets": sets,
            "recording_mode": "strength",
            "duration_seconds": None,
            "distance_km": None,
            "cardio_metrics": {},
            "cardio_metric_fields": [],
            "completed": True,
            "completed_at": ended.isoformat(timespec="seconds"),
            "group_id": "",
            "group_order": None,
            "note": "",
            "legacy_detail": "",
            "legacy_intensity": "",
        })
    raw = {
        "id": f"session_{current.isoformat()}",
        "date": current.isoformat(),
        "status": "completed",
        "started_at": started.isoformat(timespec="seconds"),
        "ended_at": ended.isoformat(timespec="seconds"),
        "total_duration_min": duration,
        "exercises": exercises,
        "exercise_groups": [],
        "summary_note": f"完成{workout}训练",
        "fatigue_status": "状态好" if index % 4 else "状态一般",
        "legacy_calories_kcal": None,
    }
    return TrainingSession.from_dict(raw).to_dict()


def _cardio_session(current: date, index: int, rng: random.Random) -> dict[str, Any]:
    duration = 38 + index % 9 + rng.randint(-2, 2)
    distance = round(duration * (8.2 + 0.5 * index / (EXPECTED_DAYS - 1)) / 60, 2)
    started = datetime.combine(current, time(9, 10 + index % 10), TZ)
    ended = started + timedelta(minutes=duration)
    raw = {
        "id": f"session_{current.isoformat()}",
        "date": current.isoformat(),
        "status": "completed",
        "started_at": started.isoformat(timespec="seconds"),
        "ended_at": ended.isoformat(timespec="seconds"),
        "total_duration_min": duration,
        "exercises": [{
            "id": f"session_exercise_{current.isoformat()}_1",
            "exercise_id": "exercise_run",
            "name": "跑步",
            "body_part": "有氧",
            "order": 1,
            "sets": [],
            "recording_mode": "cardio",
            "duration_seconds": duration * 60,
            "distance_km": distance,
            "cardio_metrics": {"speed_kph": round(distance / duration * 60, 1), "incline_percent": 1.0},
            "cardio_metric_fields": ["speed_kph", "incline_percent"],
            "completed": True,
            "completed_at": ended.isoformat(timespec="seconds"),
            "group_id": "",
            "group_order": None,
            "note": "轻松有氧",
            "legacy_detail": "",
            "legacy_intensity": "",
        }],
        "exercise_groups": [],
        "summary_note": "完成有氧训练",
        "fatigue_status": "状态好",
        "legacy_calories_kcal": None,
    }
    return TrainingSession.from_dict(raw).to_dict()


def _circumference(index: int, current: date) -> dict[str, Any] | None:
    if index % 7 and index != EXPECTED_DAYS - 1:
        return None
    progress = index / (EXPECTED_DAYS - 1)
    return {
        "measured_at": _iso_at(current, 7, 20),
        "chest_cm": round(103.5 - 1.2 * progress, 1),
        "waist_cm": round(88.5 - 6.0 * progress, 1),
        "hip_cm": round(100.0 - 2.5 * progress, 1),
        "arm_cm": round(36.2 + 0.5 * progress, 1),
        "thigh_cm": round(59.0 - 0.8 * progress, 1),
        "calf_cm": round(38.0 - 0.2 * progress, 1),
    }


def _record(current: date, index: int, rng: random.Random) -> dict[str, Any]:
    workout = SCHEDULE[index % len(SCHEDULE)]
    day_type = DAY_TYPE_BY_WORKOUT[workout]
    weight = round(_trend(78.4, 74.7, index, rng, 0.18), 1)
    bodyfat = round(_trend(20.8, 18.2, index, rng, 0.10), 1)
    measured_at = _iso_at(current, 7, 15)
    circumference = _circumference(index, current)
    meals, meal_totals, daily_total = _daily_meals(day_type, index, rng)
    targets = _targets(day_type, weight, bodyfat)
    compliance = {
        "status": "达标" if abs(float(daily_total["kcal"]) - float(targets["calorie_target"])) <= 250 else "未达标",
        "kcal_target": targets["calorie_target"],
        "warning_text": "虚拟数据：用于功能测试",
    }

    if workout in STRENGTH_PLANS:
        session = _strength_session(current, index, workout, rng)
    elif workout == "有氧":
        session = _cardio_session(current, index, rng)
    else:
        session = None
    training = {
        "total_duration_min": "" if session is None else f"{float(session['total_duration_min']):g}",
        "total_calories_kcal": "" if session is None else str(260 + index % 7 * 15),
        "fatigue_status": "状态好" if session is not None else "恢复",
        "summary_note": "休息与恢复" if session is None else str(session["summary_note"]),
        "targets": [] if session is None else [{"target": part, "detail": workout, "note": ""} for part in workout.split("+")],
        "carb_reminder_dismissed_signature": "",
        "session": None,
        "sessions": [] if session is None else [session],
    }

    water_total = 2300 + (index % 6) * 150 + rng.choice((-100, 0, 100))
    water_records = [500, 500, 600, 500, water_total - 2100]
    sleep_minutes = 430 + (index * 17) % 61 + rng.randint(-8, 8)
    bed_minutes = 23 * 60 + 5 + (index * 7) % 36
    wake_minutes = (bed_minutes + sleep_minutes) % (24 * 60)
    bed_time = f"{bed_minutes // 60:02d}:{bed_minutes % 60:02d}"
    wake_time = f"{wake_minutes // 60:02d}:{wake_minutes % 60:02d}"

    profile: dict[str, Any] = {
        "weight_kg": weight,
        "bodyfat_percent": bodyfat,
        "height_cm": 175,
        "age": 30,
        "sex": "男",
        "activity_habit": "高频训练",
        "waist_cm": "",
        "arm_cm": "",
        "chest_cm": "",
        "hip_cm": "",
        "thigh_cm": "",
        "calf_cm": "",
        "macro_mode": "auto",
        "macro_multipliers": copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS),
        "custom_macro_multipliers": copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS),
        "auto_macro_multipliers": copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS),
        "day_type": day_type,
        "targets": targets,
        "compliance": compliance,
        "measurement": {
            "measured_at": measured_at,
            "weight_kg": weight,
            "weight_measured": True,
            "bodyfat_percent": bodyfat,
            "bodyfat_measured": True,
        },
    }
    if circumference is not None:
        profile["circumference"] = circumference

    record = {
        "date": current.isoformat(),
        "profile": profile,
        "meals": meals,
        "meal_totals": meal_totals,
        "daily_total": daily_total,
        "training": training,
        "water": {
            "records_ml": water_records,
            "total_ml": sum(water_records),
            "target_ml": 2500,
            "status": "达标" if sum(water_records) >= 2500 else "未达标",
        },
        "supplements": [
            {"name": "肌酸", "amount": "5", "unit": "g"},
            {"name": "鱼油", "amount": "2", "unit": "粒"},
            {"name": "复合维生素", "amount": "1", "unit": "片"},
        ],
        "sleep": {
            "bed_time": bed_time,
            "wake_time": wake_time,
            "naps": [{"start": "13:10", "end": "13:30", "minutes": 20}] if index % 11 == 5 else [],
            "total_minutes": sleep_minutes,
            "total_text": f"{sleep_minutes // 60}小时{sleep_minutes % 60}分",
        },
    }
    if session is None:
        record["calendar_event"] = {"type": "rest", "text": "休息"}
    return record


def generate_payload() -> dict[str, Any]:
    if (END_DATE - START_DATE).days + 1 != EXPECTED_DAYS:
        raise AssertionError("configured date range must contain exactly 100 days")
    rng = random.Random(SEED)
    records = {}
    for index in range(EXPECTED_DAYS):
        current = START_DATE + timedelta(days=index)
        records[current.isoformat()] = _record(current, index, rng)
    final_record = records[END_DATE.isoformat()]
    final_profile = final_record["profile"]
    final_circumference = final_profile["circumference"]
    return {
        "format": "carbs_king_backup",
        "backup_version": 2,
        "app_version": "1.2.2",
        "exported_at": "2026-07-23T23:59:59+08:00",
        "daily_records": records,
        "food_library": copy.deepcopy(DEFAULT_FOODS),
        "supplement_library": copy.deepcopy(DEFAULT_SUPPLEMENTS),
        "user_profile": {
            "weight": f"{float(final_profile['weight_kg']):g}",
            "bodyfat": f"{float(final_profile['bodyfat_percent']):g}",
            "height": "175",
            "age": "30",
            "sex": "男",
            "activity_habit": "高频训练",
            "chest_cm": f"{float(final_circumference['chest_cm']):g}",
            "waist_cm": f"{float(final_circumference['waist_cm']):g}",
            "hip_cm": f"{float(final_circumference['hip_cm']):g}",
            "arm_cm": f"{float(final_circumference['arm_cm']):g}",
            "thigh_cm": f"{float(final_circumference['thigh_cm']):g}",
            "calf_cm": f"{float(final_circumference['calf_cm']):g}",
            "macro_mode": "auto",
            "macro_multipliers": copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS),
            "custom_macro_multipliers": copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS),
            "auto_macro_multipliers": copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS),
            "body_updated_at": _iso_at(END_DATE, 7, 15),
            "profile_inited": True,
        },
        "achievement_unlocks": {},
        "training_data": {
            "schema_version": TRAINING_SCHEMA_VERSION,
            "custom_exercises": [],
            "exercises": [],
            "templates": [],
            "sessions": [],
        },
    }


def summarize_payload(payload: Mapping[str, Any]) -> BackupStats:
    records = payload.get("daily_records", {})
    if not isinstance(records, Mapping):
        raise AssertionError("daily_records must be a mapping")
    dates = sorted(str(key) for key in records)
    training_days = strength_days = cardio_days = rest_days = diet_days = circumference_days = 0
    day_types: Counter[str] = Counter()
    for key in dates:
        record = records[key]
        if not isinstance(record, Mapping):
            continue
        profile = record.get("profile", {})
        if isinstance(profile, Mapping):
            day_types[str(profile.get("day_type") or "")] += 1
            if isinstance(profile.get("circumference"), Mapping):
                circumference_days += 1
        daily_total = record.get("daily_total", {})
        if isinstance(daily_total, Mapping) and float(daily_total.get("kcal") or 0) > 0:
            diet_days += 1
        training = record.get("training", {})
        sessions = training.get("sessions", []) if isinstance(training, Mapping) else []
        if isinstance(sessions, list) and sessions:
            training_days += 1
            modes = {
                str(exercise.get("recording_mode") or "strength")
                for session in sessions if isinstance(session, Mapping)
                for exercise in session.get("exercises", []) if isinstance(exercise, Mapping)
            }
            if "cardio" in modes:
                cardio_days += 1
            else:
                strength_days += 1
        else:
            rest_days += 1
    return BackupStats(
        record_days=len(dates),
        first_date=dates[0] if dates else "",
        last_date=dates[-1] if dates else "",
        training_days=training_days,
        strength_days=strength_days,
        cardio_days=cardio_days,
        rest_days=rest_days,
        diet_days=diet_days,
        circumference_days=circumference_days,
        day_types=dict(sorted(day_types.items())),
        food_items=len(payload.get("food_library", [])),
        supplement_items=len(payload.get("supplement_library", [])),
    )


def _assert_no_unfinished_sessions(value: Any) -> None:
    if isinstance(value, Mapping):
        if "status" in value and value.get("status") in {"active", "planned"}:
            raise AssertionError(f"unfinished session found: {value.get('id', '')}")
        if "active_session" in value:
            raise AssertionError("active_session must not exist")
        for child in value.values():
            _assert_no_unfinished_sessions(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_unfinished_sessions(child)


def _dict_normalizer(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list_normalizer(value: Any) -> list[dict[str, Any]]:
    return [copy.deepcopy(dict(item)) for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def verify_with_backup_service(payload: Mapping[str, Any]) -> BackupStats:
    """Normalize, validate, and actually replace-import into isolated disk repositories."""
    with tempfile.TemporaryDirectory(prefix="carbs-king-virtual-backup-") as temp:
        root = Path(temp)
        repositories = AppRepositories(
            records=JsonRepository(root / "daily_records.json", dict, _dict_normalizer),
            foods=JsonRepository(root / "food_library.json", list, _list_normalizer),
            supplements=JsonRepository(root / "supplement_library.json", list, _list_normalizer),
            profile=JsonRepository(root / "user_profile.json", dict, _dict_normalizer),
            achievements=JsonRepository(root / "achievement_unlocks.json", dict, _dict_normalizer),
        )
        repositories.records.save({"1999-01-01": {"sentinel": True}})
        repositories.foods.save([{"name": "replace sentinel", "base_qty": 1}])
        repositories.supplements.save([{"name": "replace sentinel", "default_amount": 1}])
        repositories.profile.save({"weight": "1"})
        repositories.achievements.save({"sentinel": "replace"})
        save_json(root / "training_data.json", {"active_session": {"status": "active"}})

        records = repositories.records.load()
        foods = repositories.foods.load()
        supplements = repositories.supplements.load()
        state = AppState.default(MEALS)
        state["date"] = END_DATE.isoformat()
        reloads: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        service = create_backup_service(BackupServiceDependencies(
            state=state,
            repositories=repositories,
            records=records,
            foods=foods,
            supplements=supplements,
            app_dir=root,
            app_version="1.2.2",
            load_profile=repositories.profile.load,
            save_profile=repositories.profile.save,
            reload_date=lambda *args, **kwargs: reloads.append((args, kwargs)),
        ))
        normalized = service.normalize_payload(copy.deepcopy(dict(payload)))
        service.validate_full(normalized)
        service.apply(normalized, "replace")

        restored = {
            **copy.deepcopy(dict(payload)),
            "daily_records": repositories.records.load(),
            "food_library": repositories.foods.load(),
            "supplement_library": repositories.supplements.load(),
            "user_profile": repositories.profile.load(),
            "achievement_unlocks": repositories.achievements.load(),
            "training_data": load_json(root / "training_data.json", {}),
        }
        stats = summarize_payload(restored)
        if stats.record_days != EXPECTED_DAYS:
            raise AssertionError(f"expected {EXPECTED_DAYS} days, got {stats.record_days}")
        if (stats.first_date, stats.last_date) != (START_DATE.isoformat(), END_DATE.isoformat()):
            raise AssertionError("restored date range does not match")
        if stats.training_days + stats.rest_days != EXPECTED_DAYS or stats.diet_days != EXPECTED_DAYS:
            raise AssertionError("restored day counts are inconsistent")
        if restored["food_library"] != DEFAULT_FOODS or restored["supplement_library"] != DEFAULT_SUPPLEMENTS:
            raise AssertionError("default libraries were not preserved")
        if len(reloads) != 1:
            raise AssertionError("replace import did not reload exactly once")
        _assert_no_unfinished_sessions(restored)
        return stats


def write_backup(output_path: Path = OUTPUT_PATH) -> tuple[Path, BackupStats]:
    payload = generate_payload()
    stats = verify_with_backup_service(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    if loaded != payload:
        raise AssertionError("written backup does not round-trip")
    return output_path, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    output, stats = write_backup(args.output)
    print(json.dumps({"output": str(output), "bytes": output.stat().st_size, **stats.__dict__}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

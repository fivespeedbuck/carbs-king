"""Update-safe JSON storage and profile persistence."""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

from app_defaults import DEFAULT_MACRO_MULTIPLIERS
from app_utils import to_float

SCRIPT_DIR = Path(__file__).resolve().parent

DATA_FILENAMES = [
    "food_library.json",
    "supplement_library.json",
    "daily_records.json",
    "user_profile.json",
    "training_data.json",
    "training_recycle_bin.json",
    "achievement_unlocks.json",
    "goal_challenges.json",
]

def get_app_dir() -> Path:
    """Use Flet's update-safe data directory, with source-run fallbacks."""
    explicit_data_dir = os.environ.get("CARBS_KING_DATA_DIR", "").strip()
    if explicit_data_dir:
        app_dir = Path(explicit_data_dir)
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir

    candidates = []
    flet_storage = os.environ.get("FLET_APP_STORAGE_DATA", "").strip()
    if flet_storage:
        candidates.append(Path(flet_storage))
    if sys.platform.startswith("win"):
        candidates.append(Path(os.environ.get("APPDATA", str(Path.home()))) / "CarbCycleRecorderMobile")
    else:
        candidates.append(Path.home() / ".carb_cycle_recorder_mobile")

    for app_dir in candidates:
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
            return app_dir
        except Exception:
            continue
    return SCRIPT_DIR

APP_DIR = get_app_dir()
FOOD_FILE = APP_DIR / "food_library.json"
SUPP_FILE = APP_DIR / "supplement_library.json"
RECORD_FILE = APP_DIR / "daily_records.json"
PROFILE_FILE = APP_DIR / "user_profile.json"
ACHIEVEMENT_FILE = APP_DIR / "achievement_unlocks.json"
GOAL_CHALLENGE_FILE = APP_DIR / "goal_challenges.json"
TRAINING_FILE = APP_DIR / "training_data.json"
TRAINING_RECYCLE_BIN_FILE = APP_DIR / "training_recycle_bin.json"

def migrate_legacy_data():
    """Move older-build data into Flet's persistent directory once."""
    if os.environ.get("CARBS_KING_DATA_DIR", "").strip():
        return

    legacy_dirs = [SCRIPT_DIR]
    try:
        legacy_dirs.append(Path.home() / ".carb_cycle_recorder_mobile")
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:
            legacy_dirs.append(Path(os.environ.get("APPDATA", str(Path.home()))) / "CarbCycleRecorderMobile")
        except Exception:
            pass

    seen = set()
    for old_dir in legacy_dirs:
        try:
            old_dir = old_dir.resolve()
        except Exception:
            pass
        if old_dir == APP_DIR or str(old_dir) in seen:
            continue
        seen.add(str(old_dir))
        for filename in DATA_FILENAMES:
            old_path = old_dir / filename
            new_path = APP_DIR / filename
            try:
                if old_path.exists() and not new_path.exists():
                    shutil.copy2(old_path, new_path)
            except Exception:
                pass

migrate_legacy_data()

def load_json(path: Path, default):
    if not path.exists():
        save_json(path, default)
        return default
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if data else default
    except Exception:
        return default

def save_json(path: Path, data):
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8-sig") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    temp_path.replace(path)


def normalize_profile_age(data: dict, *, today: date | None = None) -> bool:
    """Advance a stored age once per New Year without requiring a birthday."""
    today_year = (today or date.today()).year
    previous_age = data.get("age")
    previous_reference_year = data.get("age_reference_year")
    try:
        reference_year = int(previous_reference_year or today_year)
    except (TypeError, ValueError):
        reference_year = today_year
    age_raw = str(previous_age or "").strip()
    try:
        age_value = int(float(age_raw))
    except (TypeError, ValueError):
        age_value = None
    if reference_year > today_year:
        reference_year = today_year
    if age_value is not None and today_year > reference_year:
        data["age"] = str(age_value + today_year - reference_year)
    data["age_reference_year"] = today_year
    return data.get("age") != previous_age or data.get("age_reference_year") != previous_reference_year


def load_user_profile():
    default = {
        "weight": "",
        "bodyfat": "",
        "bodyfat_measured_at": "",
        "height": "",
        "age": "",
        "age_reference_year": 0,
        "theme_color": "green",
        "sex": "",
        "activity_habit": "",
        "waist_cm": "",
        "arm_cm": "",
        "chest_cm": "",
        "hip_cm": "",
        "thigh_cm": "",
        "calf_cm": "",
        "macro_mode": "auto",
        "macro_goal": "减脂",
        "carb_phase": {},
        "macro_multipliers": DEFAULT_MACRO_MULTIPLIERS,
        "custom_macro_multipliers": DEFAULT_MACRO_MULTIPLIERS,
        "auto_macro_multipliers": DEFAULT_MACRO_MULTIPLIERS,
        "body_updated_at": "",
        "profile_inited": False,
    }
    data = load_json(PROFILE_FILE, default)
    if not isinstance(data, dict):
        data = default
    for k, v in default.items():
        data.setdefault(k, v)
    normalized = {}
    stored_multipliers = data.get("custom_macro_multipliers", data.get("macro_multipliers", {}))
    if not isinstance(stored_multipliers, dict):
        stored_multipliers = {}
    for day_type, defaults in DEFAULT_MACRO_MULTIPLIERS.items():
        saved_day = stored_multipliers.get(day_type, {})
        if not isinstance(saved_day, dict):
            saved_day = {}
        normalized[day_type] = {
            macro: to_float(saved_day.get(macro), default_value)
            for macro, default_value in defaults.items()
        }
    data["macro_multipliers"] = normalized
    data["custom_macro_multipliers"] = json.loads(json.dumps(normalized))
    stored_auto = data.get("auto_macro_multipliers", {})
    if not isinstance(stored_auto, dict):
        stored_auto = {}
    normalized_auto = {}
    for day_type, defaults in DEFAULT_MACRO_MULTIPLIERS.items():
        saved_day = stored_auto.get(day_type, {})
        if not isinstance(saved_day, dict):
            saved_day = {}
        normalized_auto[day_type] = {
            macro: to_float(saved_day.get(macro), default_value)
            for macro, default_value in defaults.items()
        }
    data["auto_macro_multipliers"] = normalized_auto
    if data.get("macro_mode") not in ["auto", "custom"]:
        data["macro_mode"] = "auto"
    if data.get("macro_goal") not in ["减脂", "保持", "增肌"]:
        data["macro_goal"] = "减脂"
    if not isinstance(data.get("carb_phase"), dict):
        data["carb_phase"] = {}
    # 年龄不保存生日，按每年元旦递增。旧版本没有参考年份时从首次读取年份开始计算，
    # 避免在升级当天凭空补算多年年龄；之后每次跨年只会递增一次并写回。
    if normalize_profile_age(data):
        save_json(PROFILE_FILE, data)
    return data

def save_user_profile(data):
    save_json(PROFILE_FILE, data)

__all__ = [
    "ACHIEVEMENT_FILE", "APP_DIR", "FOOD_FILE", "GOAL_CHALLENGE_FILE",
    "PROFILE_FILE", "RECORD_FILE", "SUPP_FILE", "TRAINING_FILE", "TRAINING_RECYCLE_BIN_FILE", "load_json",
    "load_user_profile", "normalize_profile_age", "save_json", "save_user_profile",
]

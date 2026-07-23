"""Update-safe JSON storage and profile persistence."""

from __future__ import annotations

import json
import os
import shutil
import sys
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
    "achievement_unlocks.json",
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
TRAINING_FILE = APP_DIR / "training_data.json"

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


def load_user_profile():
    default = {
        "weight": "62.5",
        "bodyfat": "13",
        "height": "170",
        "age": "30",
        "sex": "男",
        "activity_habit": "规律训练",
        "waist_cm": "",
        "arm_cm": "",
        "chest_cm": "",
        "hip_cm": "",
        "thigh_cm": "",
        "calf_cm": "",
        "macro_mode": "auto",
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
    return data

def save_user_profile(data):
    save_json(PROFILE_FILE, data)

__all__ = [
    "ACHIEVEMENT_FILE", "APP_DIR", "FOOD_FILE", "PROFILE_FILE", "RECORD_FILE",
    "SUPP_FILE", "TRAINING_FILE", "load_json", "load_user_profile", "save_json",
    "save_user_profile",
]

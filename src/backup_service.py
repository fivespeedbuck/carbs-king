"""Full backup validation, snapshots, restore, and rollback."""

from __future__ import annotations

import copy
import datetime
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app_defaults import DEFAULT_MACRO_MULTIPLIERS
from app_state import AppState
from repositories import AppRepositories
from storage_service import load_json, save_json


CORE_BACKUP_KEYS = (
    "daily_records",
    "food_library",
    "supplement_library",
    "user_profile",
)


@dataclass(frozen=True)
class BackupServiceDependencies:
    state: AppState
    repositories: AppRepositories
    records: dict[str, Any]
    foods: list[dict[str, Any]]
    supplements: list[dict[str, Any]]
    app_dir: Path
    app_version: str
    load_profile: Callable[[], dict[str, Any]]
    save_profile: Callable[[dict[str, Any]], None]
    reload_date: Callable[..., None]


@dataclass
class BackupService:
    build_payload: Callable[[], dict[str, Any]]
    normalize_payload: Callable[[Any], dict[str, Any]]
    validate_full: Callable[[dict[str, Any]], None]
    summarize: Callable[[dict[str, Any]], str]
    merge_named_items: Callable[..., list[dict[str, Any]]]
    snapshot: Callable[[], Path]
    apply: Callable[[dict[str, Any], str], None]
    clear_personal_data: Callable[[], dict[str, int]]


def create_backup_service(deps: BackupServiceDependencies) -> BackupService:
    state = deps.state
    repositories = deps.repositories
    records = deps.records
    foods = deps.foods
    supplements = deps.supplements
    app_dir = deps.app_dir
    app_version = deps.app_version
    load_profile = deps.load_profile
    save_profile = deps.save_profile
    reload_date = deps.reload_date
    training_path = app_dir / "training_data.json"

    def make_full_backup_payload() -> dict[str, Any]:
        return {
            "format": "carbs_king_backup",
            "backup_version": 2,
            "app_version": app_version,
            "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "daily_records": copy.deepcopy(repositories.records.load()),
            "food_library": copy.deepcopy(repositories.foods.load()),
            "supplement_library": copy.deepcopy(repositories.supplements.load()),
            "user_profile": copy.deepcopy(load_profile()),
            "achievement_unlocks": copy.deepcopy(repositories.achievements.load()),
            "training_data": copy.deepcopy(load_json(training_path, {})),
        }

    def _validate_section(key: str, value: Any, expected_type: type) -> None:
        if not isinstance(value, expected_type):
            raise ValueError(f"{key} 数据格式不正确")
        if key == "daily_records":
            invalid = [
                item_key for item_key, item_value in value.items()
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(item_key))
                or not isinstance(item_value, dict)
            ]
            if invalid:
                raise ValueError("每日记录包含无效日期或记录内容")
        if key in {"food_library", "supplement_library"} and not all(
            isinstance(item, dict) for item in value
        ):
            raise ValueError(f"{key} 中包含无效条目")

    def normalize_import_payload(payload: Any) -> dict[str, Any]:
        """Accept full legacy backups while retaining hidden category parsing."""
        normalized: dict[str, Any] = {}
        if isinstance(payload, dict):
            expected_types = {
                "daily_records": dict,
                "food_library": list,
                "supplement_library": list,
                "user_profile": dict,
                "achievement_unlocks": dict,
                "training_data": dict,
            }
            for key, expected_type in expected_types.items():
                if key in payload:
                    _validate_section(key, payload[key], expected_type)
                    normalized[key] = copy.deepcopy(payload[key])

            # Older exports occasionally used this shorter key.
            if "achievements" in payload and "achievement_unlocks" not in normalized:
                _validate_section("achievement_unlocks", payload["achievements"], dict)
                normalized["achievement_unlocks"] = copy.deepcopy(payload["achievements"])

            if not normalized:
                date_keys = [key for key in payload if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(key))]
                if date_keys and len(date_keys) == len(payload):
                    _validate_section("daily_records", payload, dict)
                    normalized["daily_records"] = copy.deepcopy(payload)
                elif any(key in payload for key in ("profile_inited", "height", "activity_habit", "macro_mode")):
                    normalized["user_profile"] = copy.deepcopy(payload)
        elif isinstance(payload, list):
            if not payload:
                raise ValueError("空列表无法判断是食物库还是补剂库")
            if all(isinstance(item, dict) and "base_qty" in item for item in payload):
                normalized["food_library"] = copy.deepcopy(payload)
            elif all(isinstance(item, dict) and "default_amount" in item for item in payload):
                normalized["supplement_library"] = copy.deepcopy(payload)

        if not normalized:
            raise ValueError("未识别到可导入的碳水大王备份数据")
        return normalized

    def validate_full_backup(import_data: dict[str, Any]) -> None:
        missing = [key for key in CORE_BACKUP_KEYS if key not in import_data]
        if missing:
            raise ValueError("请选择由“全量导出”生成的完整备份文件")
        for key, expected in (
            ("daily_records", dict),
            ("food_library", list),
            ("supplement_library", list),
            ("user_profile", dict),
        ):
            _validate_section(key, import_data[key], expected)

    def import_summary(import_data: dict[str, Any]) -> str:
        return " · ".join((
            f"每日记录 {len(import_data.get('daily_records', {}))} 天",
            f"食物 {len(import_data.get('food_library', []))} 项",
            f"补剂 {len(import_data.get('supplement_library', []))} 项",
            "个人资料",
        ))

    def merge_named_items(current_items, imported_items):
        result = [dict(item) for item in current_items if isinstance(item, dict)]
        positions = {
            str(item.get("name", "")).strip(): index
            for index, item in enumerate(result)
            if str(item.get("name", "")).strip()
        }
        for item in imported_items:
            if not isinstance(item, dict):
                continue
            copied = dict(item)
            name = str(copied.get("name", "")).strip()
            if name and name in positions:
                result[positions[name]] = copied
            else:
                if name:
                    positions[name] = len(result)
                result.append(copied)
        return result

    def save_pre_import_snapshot() -> Path:
        backup_dir = app_dir / "import_safety_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        snapshot_path = backup_dir / f"before_import_{stamp}.json"
        save_json(snapshot_path, make_full_backup_payload())
        return snapshot_path

    def _sync_profile_state(profile: dict[str, Any]) -> None:
        state["weight"] = str(profile.get("weight", state.get("weight", "62.5")))
        state["bodyfat"] = str(profile.get("bodyfat", state.get("bodyfat", "13")))
        state["height"] = str(profile.get("height", state.get("height", "170")))
        state["age"] = str(profile.get("age", state.get("age", "30")))
        state["sex"] = str(profile.get("sex", state.get("sex", "男")))
        state["activity_habit"] = str(profile.get("activity_habit", state.get("activity_habit", "规律训练")))
        state["waist_cm"] = str(profile.get("waist_cm", state.get("waist_cm", "")))
        state["arm_cm"] = str(profile.get("arm_cm", state.get("arm_cm", "")))
        state["chest_cm"] = str(profile.get("chest_cm", state.get("chest_cm", "")))
        state["hip_cm"] = str(profile.get("hip_cm", state.get("hip_cm", "")))
        state["thigh_cm"] = str(profile.get("thigh_cm", state.get("thigh_cm", "")))
        state["calf_cm"] = str(profile.get("calf_cm", state.get("calf_cm", "")))
        state["macro_mode"] = profile.get("macro_mode", state.get("macro_mode", "auto"))
        state["macro_multipliers"] = copy.deepcopy(
            profile.get("custom_macro_multipliers", profile.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))
        )
        state["auto_macro_multipliers"] = copy.deepcopy(
            profile.get("auto_macro_multipliers", DEFAULT_MACRO_MULTIPLIERS)
        )
        state["profile_inited"] = bool(profile.get("profile_inited", state.get("profile_inited", False)))

    def _write_all(payload: dict[str, Any]) -> None:
        repositories.records.save(payload["daily_records"])
        repositories.foods.save(payload["food_library"])
        repositories.supplements.save(payload["supplement_library"])
        save_profile(payload["user_profile"])
        repositories.achievements.save(payload["achievement_unlocks"])
        save_json(training_path, payload["training_data"])

    def _replace_runtime(payload: dict[str, Any]) -> None:
        records.clear()
        records.update(copy.deepcopy(payload["daily_records"]))
        foods.clear()
        foods.extend(copy.deepcopy(payload["food_library"]))
        supplements.clear()
        supplements.extend(copy.deepcopy(payload["supplement_library"]))
        _sync_profile_state(payload["user_profile"])

    def apply_import_data(import_data: dict[str, Any], mode: str = "replace") -> None:
        """Apply all sections as one logical transaction and roll back on failure."""
        if mode not in {"merge", "replace"}:
            raise ValueError("不支持的导入方式")

        before = make_full_backup_payload()
        target = copy.deepcopy(before)
        if mode == "merge":
            if "daily_records" in import_data:
                target["daily_records"].update(copy.deepcopy(import_data["daily_records"]))
            if "food_library" in import_data:
                target["food_library"] = merge_named_items(target["food_library"], import_data["food_library"])
            if "supplement_library" in import_data:
                target["supplement_library"] = merge_named_items(
                    target["supplement_library"], import_data["supplement_library"]
                )
            if "user_profile" in import_data:
                target["user_profile"].update(copy.deepcopy(import_data["user_profile"]))
        else:
            for key in (
                "daily_records", "food_library", "supplement_library", "user_profile",
                "achievement_unlocks", "training_data",
            ):
                if key in import_data:
                    target[key] = copy.deepcopy(import_data[key])

        # Legacy full backups did not contain these two sections; preserving the
        # current values avoids deleting data that the old format could not carry.
        target.setdefault("achievement_unlocks", copy.deepcopy(before["achievement_unlocks"]))
        target.setdefault("training_data", copy.deepcopy(before["training_data"]))

        save_pre_import_snapshot()
        try:
            _write_all(target)
            _replace_runtime(target)
            reload_date(state.get("date", date.today().isoformat()), autosave=False, show=False)
        except Exception as import_error:
            try:
                _write_all(before)
                _replace_runtime(before)
                reload_date(state.get("date", date.today().isoformat()), autosave=False, show=False)
            except Exception as rollback_error:
                raise RuntimeError(f"导入失败，自动回滚也未完成：{rollback_error}") from import_error
            raise RuntimeError("导入失败，已自动恢复导入前的数据") from import_error

    def clear_personal_data() -> dict[str, int]:
        """Delete personal records while preserving all three reusable libraries."""
        before = make_full_backup_payload()
        default_state = AppState.default(())
        cleared_profile = {
            "weight": default_state["weight"],
            "bodyfat": default_state["bodyfat"],
            "height": default_state["height"],
            "age": default_state["age"],
            "sex": default_state["sex"],
            "activity_habit": default_state["activity_habit"],
            "waist_cm": "",
            "arm_cm": "",
            "chest_cm": "",
            "hip_cm": "",
            "thigh_cm": "",
            "calf_cm": "",
            "macro_mode": "auto",
            "custom_macro_multipliers": copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS),
            "auto_macro_multipliers": copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS),
            "profile_inited": False,
        }
        training_data = before.get("training_data", {})
        custom_exercises = copy.deepcopy(
            training_data.get("custom_exercises", []) if isinstance(training_data, dict) else []
        )
        if not isinstance(custom_exercises, list):
            custom_exercises = []

        try:
            repositories.records.save({})
            save_profile({})
            repositories.achievements.save({})
            save_json(training_path, {"custom_exercises": custom_exercises})

            records.clear()
            _sync_profile_state(cleared_profile)
            reload_date(state.get("date", date.today().isoformat()), autosave=False, show=False)
        except Exception as clear_error:
            try:
                repositories.records.save(before["daily_records"])
                save_profile(before["user_profile"])
                repositories.achievements.save(before["achievement_unlocks"])
                save_json(training_path, before["training_data"])
                records.clear()
                records.update(copy.deepcopy(before["daily_records"]))
                _sync_profile_state(before["user_profile"])
                reload_date(state.get("date", date.today().isoformat()), autosave=False, show=False)
            except Exception as rollback_error:
                raise RuntimeError(f"清除失败，自动回滚也未完成：{rollback_error}") from clear_error
            raise RuntimeError("清除失败，已自动恢复清除前的数据") from clear_error

        return {
            "record_days": len(before.get("daily_records", {})),
            "custom_exercises_kept": len(custom_exercises),
        }

    return BackupService(
        build_payload=make_full_backup_payload,
        normalize_payload=normalize_import_payload,
        validate_full=validate_full_backup,
        summarize=import_summary,
        merge_named_items=merge_named_items,
        snapshot=save_pre_import_snapshot,
        apply=apply_import_data,
        clear_personal_data=clear_personal_data,
    )


__all__ = ["BackupService", "BackupServiceDependencies", "create_backup_service"]

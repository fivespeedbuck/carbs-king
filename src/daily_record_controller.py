"""Daily record serialization and date-loading lifecycle.

The controller preserves the on-disk v50.1 record shape while keeping JSON
and migration details out of the app shell and feature views.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
import json
from typing import Any

from analytics_service import normalize_body_measurement
from app_defaults import CIRCUMFERENCE_FIELDS, DAY_TYPES, DEFAULT_MACRO_MULTIPLIERS
from app_utils import to_float
from repositories import AppRepositories
from training_clock_service import active_session_with_start
from training_service import migrate_legacy_training, normalize_session_payload


@dataclass(frozen=True)
class DailyRecordDependencies:
    state: MutableMapping[str, Any]
    repositories: AppRepositories
    records: MutableMapping[str, Any]
    nutrition: Any
    meals: Sequence[str]
    load_profile: Callable[[], dict[str, Any]]
    sleep_total_minutes: Callable[[], int]
    format_minutes: Callable[[int], str]
    restore_training_cursor: Callable[[], None]
    refresh: Callable[[], None]
    snack: Callable[..., None]
    now: Callable[[], datetime] = datetime.now
    today: Callable[[], date] = date.today


class DailyRecordController:
    def __init__(self, deps: DailyRecordDependencies):
        self.deps = deps

    def latest_body(self, target_date: str | None = None) -> dict[str, Any] | None:
        candidates = []
        for record_date, record in self.deps.records.items():
            if target_date and record_date > target_date:
                continue
            measurement = normalize_body_measurement(record, record_date)
            if not measurement["is_measured"]:
                continue
            weight = measurement.get("weight_kg")
            bodyfat = measurement.get("bodyfat_percent")
            if weight is not None or bodyfat is not None:
                candidates.append((record_date, weight, bodyfat))
        if not candidates and target_date:
            return self.latest_body()
        if not candidates:
            return None
        record_date, weight, bodyfat = sorted(candidates, key=lambda item: item[0])[-1]
        return {"date": record_date, "weight": weight, "bodyfat": bodyfat}

    def payload(self) -> dict[str, Any]:
        state = self.deps.state
        total = self.deps.nutrition.daily_total()
        evaluation = self.deps.nutrition.evaluate(total)
        targets = self.deps.nutrition.targets()
        meal_totals = {}
        for meal in self.deps.meals:
            values = {"kcal": 0.0, "carb": 0.0, "protein": 0.0, "fat": 0.0}
            items = state.get("meals", {}).get(meal, []) if isinstance(state.get("meals"), dict) else []
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict):
                    for key in values:
                        values[key] += to_float(item.get(key))
            meal_totals[meal] = {key: round(value, 1) for key, value in values.items()}

        sleep_minutes = self.deps.sleep_total_minutes()
        training = state["training"]
        water = list(state["water"])
        return {
            "date": state["date"],
            "profile": {
                "weight_kg": state["weight"],
                "bodyfat_percent": state["bodyfat"],
                "height_cm": state.get("height", "170"),
                "age": state.get("age", "30"),
                "sex": state.get("sex", "男"),
                "activity_habit": state.get("activity_habit", "规律训练"),
                "waist_cm": state.get("waist_cm", ""),
                "arm_cm": state.get("arm_cm", ""),
                "chest_cm": state.get("chest_cm", ""),
                "hip_cm": state.get("hip_cm", ""),
                "thigh_cm": state.get("thigh_cm", ""),
                "calf_cm": state.get("calf_cm", ""),
                "macro_mode": state.get("macro_mode", "auto"),
                "macro_multipliers": json.loads(json.dumps(state.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))),
                "custom_macro_multipliers": json.loads(json.dumps(state.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))),
                "auto_macro_multipliers": json.loads(json.dumps(state.get("auto_macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))),
                "day_type": state["day_type"],
                "targets": targets,
                "compliance": evaluation,
                "measurement": state.get("measurement"),
                "circumference": state.get("circumference"),
            },
            "meals": {meal: list(items) for meal, items in state["meals"].items()},
            "meal_totals": meal_totals,
            "daily_total": total,
            "training": {
                "total_duration_min": training.get("total_duration_min", ""),
                "total_calories_kcal": training.get("total_calories_kcal", ""),
                "fatigue_status": training.get("fatigue_status", "状态一般"),
                "summary_note": training.get("summary_note", ""),
                "targets": list(training.get("targets", [])),
                "carb_reminder_dismissed_signature": training.get("carb_reminder_dismissed_signature", ""),
                "session": training.get("session"),
                "sessions": list(training.get("sessions", [])),
            },
            "water": {
                "records_ml": water,
                "total_ml": int(sum(water)),
                "target_ml": 2000,
                "status": "达标" if sum(water) >= 2000 else "未达标",
            },
            "supplements": list(state["supplements"]),
            "sleep": {
                "bed_time": state.get("sleep", {}).get("bed_time", ""),
                "wake_time": state.get("sleep", {}).get("wake_time", ""),
                "naps": list(state.get("sleep", {}).get("naps", [])),
                "total_minutes": sleep_minutes,
                "total_text": self.deps.format_minutes(sleep_minutes),
            },
        }

    @staticmethod
    def _merged_payload(existing: Any, payload: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(dict(existing)) if isinstance(existing, Mapping) else {}
        previous_profile = merged.get("profile", {})
        previous_profile = dict(previous_profile) if isinstance(previous_profile, Mapping) else {}
        next_profile = dict(previous_profile)
        payload_profile = payload.get("profile", {})
        if isinstance(payload_profile, Mapping):
            next_profile.update(copy.deepcopy(dict(payload_profile)))
        for key in ("measurement", "circumference"):
            if not isinstance(next_profile.get(key), Mapping) and isinstance(previous_profile.get(key), Mapping):
                next_profile[key] = copy.deepcopy(dict(previous_profile[key]))
        merged.update(copy.deepcopy(payload))
        merged["profile"] = next_profile
        return merged

    def persist_records(self) -> None:
        self.deps.repositories.records.save(self.deps.records)

    def save(self, show: bool = False) -> None:
        state = self.deps.state
        target_date = state["date"]
        self.deps.records[target_date] = self._merged_payload(
            self.deps.records.get(target_date),
            self.payload(),
        )
        self.persist_records()
        if show:
            self.deps.snack("已保存")

    def update_calendar_event(self, target_date: str, event: dict[str, Any] | None) -> None:
        current = self.deps.records.get(target_date, {})
        current = copy.deepcopy(dict(current)) if isinstance(current, Mapping) else {}
        if event is None:
            current.pop("calendar_event", None)
            if current:
                self.deps.records[target_date] = current
            else:
                self.deps.records.pop(target_date, None)
        else:
            current["calendar_event"] = copy.deepcopy(event)
            self.deps.records[target_date] = current
        self.persist_records()

    def update_circumference(
        self,
        target_date: str,
        metric_key: str,
        metric_value: float,
        *,
        measured_at: str,
        note: str = "",
    ) -> dict[str, Any]:
        current = self.deps.records.get(target_date, {})
        current = copy.deepcopy(dict(current)) if isinstance(current, Mapping) else {}
        profile = current.get("profile", {})
        profile = dict(profile) if isinstance(profile, Mapping) else {}
        circumference = profile.get("circumference", {})
        circumference = dict(circumference) if isinstance(circumference, Mapping) else {}
        circumference["measured_at"] = measured_at
        circumference[metric_key] = round(float(metric_value), 2)
        notes = circumference.get("notes", {})
        notes = dict(notes) if isinstance(notes, Mapping) else {}
        if note:
            notes[metric_key] = note
        else:
            notes.pop(metric_key, None)
        if notes:
            circumference["notes"] = notes
        else:
            circumference.pop("notes", None)
        profile["circumference"] = circumference
        current["profile"] = profile
        self.deps.records[target_date] = current
        if target_date == self.deps.state.get("date"):
            self.deps.state["circumference"] = copy.deepcopy(circumference)
        self.persist_records()
        return copy.deepcopy(circumference)

    def delete_circumference(self, target_date: str, metric_key: str) -> bool:
        allowed_keys = {key for key, _ in CIRCUMFERENCE_FIELDS}
        if metric_key not in allowed_keys:
            return False
        current = self.deps.records.get(target_date, {})
        current = copy.deepcopy(dict(current)) if isinstance(current, Mapping) else {}
        profile = current.get("profile", {})
        profile = dict(profile) if isinstance(profile, Mapping) else {}
        circumference = profile.get("circumference", {})
        circumference = dict(circumference) if isinstance(circumference, Mapping) else {}
        if metric_key not in circumference:
            return False

        circumference.pop(metric_key, None)
        notes = circumference.get("notes", {})
        notes = dict(notes) if isinstance(notes, Mapping) else {}
        notes.pop(metric_key, None)
        if notes:
            circumference["notes"] = notes
        else:
            circumference.pop("notes", None)

        if any(key in circumference for key in allowed_keys):
            profile["circumference"] = circumference
            current["profile"] = profile
        else:
            profile.pop("circumference", None)
            if profile:
                current["profile"] = profile
            else:
                current.pop("profile", None)
        if current:
            self.deps.records[target_date] = current
        else:
            self.deps.records.pop(target_date, None)
        if target_date == self.deps.state.get("date"):
            self.deps.state["circumference"] = copy.deepcopy(profile.get("circumference"))
        self.persist_records()
        return True

    @staticmethod
    def _replace_training_session(training: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
        updated = copy.deepcopy(training)
        session_copy = copy.deepcopy(session)
        session_id = str(session_copy.get("id") or "")

        def matches(candidate: Any) -> bool:
            if not isinstance(candidate, Mapping):
                return False
            if session_id:
                return str(candidate.get("id") or "") == session_id
            return (
                candidate.get("status") == "active"
                and candidate.get("started_at") == session_copy.get("started_at")
            )

        matched = False
        if matches(updated.get("session")):
            updated["session"] = copy.deepcopy(session_copy)
            matched = True
        archived = updated.get("sessions", [])
        if isinstance(archived, list):
            replaced = []
            for item in archived:
                if matches(item):
                    replaced.append(copy.deepcopy(session_copy))
                    matched = True
                else:
                    replaced.append(copy.deepcopy(item))
            updated["sessions"] = replaced
        if not matched:
            updated["session"] = session_copy
        return updated

    def persist_training_session(self, target_date: str, session: dict[str, Any]) -> None:
        if target_date == self.deps.state.get("date"):
            training = self.deps.state["training"]
            updated = self._replace_training_session(dict(training), session)
            training.clear()
            training.update(updated)
            self.save()
            return

        current = self.deps.records.get(target_date, {})
        current = copy.deepcopy(dict(current)) if isinstance(current, Mapping) else {}
        training = current.get("training", {})
        training = dict(training) if isinstance(training, Mapping) else {}
        current["training"] = self._replace_training_session(training, session)
        self.deps.records[target_date] = current
        self.persist_records()

    def clear_training(self, target_date: str) -> None:
        """Clear only the selected day's training source data and persist immediately."""
        blank = self._blank_training()
        if target_date == self.deps.state.get("date"):
            training = self.deps.state["training"]
            training.clear()
            training.update(copy.deepcopy(blank))
            self.save()
            self.deps.restore_training_cursor()
            self.deps.refresh()
            return

        current = self.deps.records.get(target_date)
        if not isinstance(current, Mapping):
            return
        updated = copy.deepcopy(dict(current))
        updated["training"] = copy.deepcopy(blank)
        self.deps.records[target_date] = updated
        self.persist_records()

    @staticmethod
    def _blank_training() -> dict[str, Any]:
        return {
            "total_duration_min": "",
            "total_calories_kcal": "",
            "fatigue_status": "状态一般",
            "summary_note": "",
            "targets": [],
            "carb_reminder_dismissed_signature": "",
            "session": None,
            "sessions": [],
        }

    def _load_training(self, raw: Any, target_date: str) -> tuple[dict[str, Any], bool]:
        if isinstance(raw, dict):
            targets = raw.get("targets", []) if isinstance(raw.get("targets", []), list) else []
            archived = [item for item in raw.get("sessions", []) if isinstance(item, dict)] if isinstance(raw.get("sessions", []), list) else []
            normalized_archived = []
            sessions_migrated = False
            for archived_session in archived:
                normalized, migrated = normalize_session_payload(archived_session)
                normalized_archived.append(normalized)
                sessions_migrated = sessions_migrated or migrated
            archived = normalized_archived
            session = raw.get("session") if isinstance(raw.get("session"), dict) else None
            if session is None and archived:
                session = next((item for item in reversed(archived) if item.get("status") == "active"), archived[-1])
            if session is None:
                migrated = migrate_legacy_training(raw, target_date)
                session = migrated.to_dict() if migrated else None
            clock_migrated = sessions_migrated
            if isinstance(session, dict):
                session, session_migrated = normalize_session_payload(session)
                clock_migrated = clock_migrated or session_migrated
            if isinstance(session, dict) and session.get("status") == "active":
                session, active_clock_migrated = active_session_with_start(session, self.deps.now())
                clock_migrated = clock_migrated or active_clock_migrated
            return {
                "total_duration_min": str(raw.get("total_duration_min", "")),
                "total_calories_kcal": str(raw.get("total_calories_kcal", "")),
                "fatigue_status": raw.get("fatigue_status", "状态一般"),
                "summary_note": str(raw.get("summary_note", "")),
                "targets": [dict(item, intensity=item.get("intensity", "中等")) for item in targets if isinstance(item, dict)],
                "carb_reminder_dismissed_signature": str(raw.get("carb_reminder_dismissed_signature", "")),
                "session": session,
                "sessions": archived,
            }, clock_migrated
        if isinstance(raw, list):
            migrated = migrate_legacy_training(raw, target_date)
            training = self._blank_training()
            training["targets"] = [dict(item, intensity=item.get("intensity", "中等")) for item in raw if isinstance(item, dict)]
            training["session"] = migrated.to_dict() if migrated else None
            return training, False
        return self._blank_training(), False

    def load(self, target_date: str, autosave: bool = False, show: bool = False) -> None:
        state = self.deps.state
        state["date"] = target_date
        record = self.deps.records.get(target_date)
        record = record if isinstance(record, dict) else None
        clock_migrated = False
        if record:
            profile = record.get("profile", {}) if isinstance(record.get("profile", {}), dict) else {}
            current_profile = self.deps.load_profile()
            if target_date == self.deps.today().isoformat() and current_profile.get("body_updated_at"):
                state["weight"] = str(current_profile.get("weight", profile.get("weight_kg", state["weight"])))
                state["bodyfat"] = str(current_profile.get("bodyfat", profile.get("bodyfat_percent", state["bodyfat"])))
            else:
                state["weight"] = str(profile.get("weight_kg", state["weight"]))
                state["bodyfat"] = str(profile.get("bodyfat_percent", state["bodyfat"]))
            measurement = normalize_body_measurement(record, target_date)
            state["measurement"] = profile.get("measurement") if measurement["is_measured"] else None
            state["circumference"] = profile.get("circumference") if isinstance(profile.get("circumference"), dict) else None
            if not state.get("profile_inited"):
                for state_key, record_key, fallback in (
                    ("height", "height_cm", "170"), ("age", "age", "30"), ("sex", "sex", "男"),
                    ("activity_habit", "activity_habit", "规律训练"), ("waist_cm", "waist_cm", ""), ("arm_cm", "arm_cm", ""),
                    ("chest_cm", "chest_cm", ""), ("hip_cm", "hip_cm", ""),
                    ("thigh_cm", "thigh_cm", ""), ("calf_cm", "calf_cm", ""),
                ):
                    state[state_key] = str(profile.get(record_key, state.get(state_key, fallback)))
            day_type = profile.get("day_type")
            state["day_type"] = day_type if day_type in DAY_TYPES else "高碳日"
            saved_meals = record.get("meals", {}) if isinstance(record.get("meals", {}), dict) else {}
            state["meals"] = {
                meal: [item for item in saved_meals.get(meal, []) if isinstance(item, dict)]
                if isinstance(saved_meals.get(meal, []), list) else []
                for meal in self.deps.meals
            }
            state["training"], clock_migrated = self._load_training(record.get("training", {}), target_date)
            water = record.get("water", {})
            values = water.get("records_ml", []) if isinstance(water, dict) else []
            state["water"] = [to_float(item) for item in values] if isinstance(values, list) else []
            supplements = record.get("supplements", [])
            state["supplements"] = [item for item in supplements if isinstance(item, dict)] if isinstance(supplements, list) else []
            sleep = record.get("sleep", {})
            state["sleep"] = {
                "bed_time": str(sleep.get("bed_time", "")),
                "wake_time": str(sleep.get("wake_time", "")),
                "naps": [item for item in sleep.get("naps", []) if isinstance(item, dict)] if isinstance(sleep.get("naps", []), list) else [],
            } if isinstance(sleep, dict) else {"bed_time": "", "wake_time": "", "naps": []}
        else:
            previous_body = self.latest_body(target_date)
            current_profile = self.deps.load_profile()
            if current_profile.get("body_updated_at"):
                state["weight"] = str(current_profile.get("weight", state["weight"]))
                state["bodyfat"] = str(current_profile.get("bodyfat", state["bodyfat"]))
            elif previous_body:
                if previous_body.get("weight") is not None:
                    state["weight"] = f"{previous_body['weight']:g}"
                if previous_body.get("bodyfat") is not None:
                    state["bodyfat"] = f"{previous_body['bodyfat']:g}"
            state["day_type"] = "高碳日"
            state["measurement"] = None
            state["circumference"] = None
            state["meals"] = {meal: [] for meal in self.deps.meals}
            state["training"] = self._blank_training()
            state["water"] = []
            state["supplements"] = []
            state["sleep"] = {"bed_time": "", "wake_time": "", "naps": []}
        self.deps.restore_training_cursor()
        if autosave or clock_migrated:
            self.save()
        self.deps.refresh()
        if show:
            self.deps.snack(f"已加载 {target_date}")


__all__ = ["DailyRecordController", "DailyRecordDependencies"]

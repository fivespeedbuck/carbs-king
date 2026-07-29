"""Durable, date-aware goal challenge state and progress calculations."""

from __future__ import annotations

import copy
import datetime as _dt
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from analytics_service import normalize_body_measurement
from goal_challenge_definitions import (
    ChallengeTemplate,
    LANES,
    TYPE_LANES,
    challenge_type_label,
    level_info,
    recommended_templates,
    repeatable_template,
)
from training_models import TrainingSession
from training_service import raw_training_sessions, session_volume


KG_TO_LBS = 2.2046226218


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _date(value: Any) -> str:
    return str(value or "")[:10]


def _valid_date(value: str) -> bool:
    try:
        _dt.date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def _in_window(record_date: str, start: str, end: str) -> bool:
    return bool(record_date and (not start or record_date >= start) and (not end or record_date <= end))


def _config(challenge: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = challenge.get(key)
    if value not in (None, ""):
        return value
    nested = challenge.get("config", {})
    return nested.get(key, default) if isinstance(nested, Mapping) else default


def _sessions(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    training = record.get("training", {})
    return [item for item in raw_training_sessions(training) if isinstance(item, Mapping)]


def _completed_session(session: Mapping[str, Any]) -> bool:
    if session.get("status") == "completed":
        return True
    exercises = session.get("exercises", [])
    return any(
        isinstance(exercise, Mapping)
        and any(isinstance(item, Mapping) and item.get("completed") for item in exercise.get("sets", []))
        for exercise in exercises if isinstance(exercises, list)
    )


def _exercise_identity(exercise: Mapping[str, Any]) -> set[str]:
    return {
        str(exercise.get("id") or "").strip(),
        str(exercise.get("exercise_id") or "").strip(),
        str(exercise.get("name") or exercise.get("exercise") or "").strip(),
    } - {""}


def _exercise_matches(exercise: Mapping[str, Any], action_id: str = "", body_part: str = "") -> bool:
    if action_id and action_id not in _exercise_identity(exercise):
        return False
    return not body_part or str(exercise.get("body_part") or "") == body_part


def _exercise_stats(
    session: Mapping[str, Any], action_id: str = "", body_part: str = "", min_weight: float = 0.0
) -> tuple[float, float, int, int]:
    volume = max_weight = reps = 0.0
    formal_sets = 0
    exercises = session.get("exercises", [])
    for exercise in exercises if isinstance(exercises, list) else []:
        if not isinstance(exercise, Mapping) or not _exercise_matches(exercise, action_id, body_part):
            continue
        raw_sets = exercise.get("sets", [])
        for item in raw_sets if isinstance(raw_sets, list) else []:
            if not isinstance(item, Mapping) or not item.get("completed") or item.get("warmup") or item.get("is_warmup"):
                continue
            weight = max(0.0, _number(item.get("weight_kg", item.get("weight"))))
            count = max(0.0, _number(item.get("reps", item.get("count"))))
            if weight < min_weight:
                continue
            volume += weight * count
            max_weight = max(max_weight, weight)
            reps += count
            formal_sets += 1
    return round(volume, 2), round(max_weight, 2), int(reps), formal_sets


def _session_duration_minutes(session: Mapping[str, Any]) -> float:
    explicit = _number(session.get("total_duration_min"), -1)
    if explicit >= 0:
        return explicit
    try:
        started = _dt.datetime.fromisoformat(str(session.get("started_at") or ""))
        ended = _dt.datetime.fromisoformat(str(session.get("ended_at") or ""))
        return max(0.0, (ended - started).total_seconds() / 60)
    except (TypeError, ValueError):
        return 0.0


def _cardio_duration_minutes(session: Mapping[str, Any]) -> float:
    total = 0.0
    for exercise in session.get("exercises", []) if isinstance(session.get("exercises", []), list) else []:
        if not isinstance(exercise, Mapping) or str(exercise.get("recording_mode") or "") != "cardio":
            continue
        if exercise.get("completed") or any(
            isinstance(item, Mapping) and item.get("completed")
            for item in exercise.get("sets", []) if isinstance(exercise.get("sets", []), list)
        ):
            total += max(0.0, _number(exercise.get("duration_seconds"))) / 60
    return total


def _has_food(record: Mapping[str, Any]) -> bool:
    meals = record.get("meals", {})
    if isinstance(meals, Mapping) and any(
        isinstance(items, list) and any(isinstance(item, Mapping) for item in items)
        for items in meals.values()
    ):
        return True
    total = record.get("daily_total", {})
    return isinstance(total, Mapping) and any(_number(total.get(key)) > 0 for key in ("kcal", "carb", "protein", "fat"))


def _nutrition_met(record: Mapping[str, Any], challenge: Mapping[str, Any]) -> bool:
    if not _has_food(record):
        return False
    indicator = str(_config(challenge, "indicator", "protein"))
    if indicator == "carb_cycle":
        profile = record.get("profile", {})
        compliance = profile.get("compliance", {}) if isinstance(profile, Mapping) else {}
        return isinstance(compliance, Mapping) and compliance.get("status") == "达标"

    total = record.get("daily_total", {})
    if not isinstance(total, Mapping):
        return False
    value = _number(total.get("protein"), -1)
    explicit_target = _number(_config(challenge, "daily_target"), 0)
    if explicit_target > 0:
        return value >= explicit_target
    profile = record.get("profile", {})
    targets = profile.get("targets", {}) if isinstance(profile, Mapping) else {}
    if not isinstance(targets, Mapping) or not targets.get("is_ready", True):
        return False
    low = _number(targets.get("protein_min"), -1)
    high = _number(targets.get("protein_max"), -1)
    return low > 0 and high >= low and low <= value <= high


def _daily_flags(
    records: Mapping[str, Any], start: str, end: str, challenge: Mapping[str, Any]
) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    challenge_type = str(challenge.get("challenge_type") or "")
    daily_target = _number(_config(challenge, "daily_target"), 0)
    for raw_date, raw_record in records.items():
        day = _date(raw_date)
        if not _in_window(day, start, end) or not isinstance(raw_record, Mapping):
            continue
        if challenge_type == "water_streak":
            water = raw_record.get("water", {})
            values = water.get("records_ml", []) if isinstance(water, Mapping) else []
            flags[day] = isinstance(values, list) and bool(values) and sum(_number(v) for v in values) >= daily_target
        elif challenge_type == "nutrition_streak":
            flags[day] = _nutrition_met(raw_record, challenge)
        elif challenge_type in {"training_streak", "training_days", "effective_training_streak", "effective_training_days"}:
            sessions = [session for session in _sessions(raw_record) if _completed_session(session)]
            if challenge_type.startswith("effective_"):
                minimum = _number(_config(challenge, "min_duration_min"), 0)
                sessions = [session for session in sessions if _session_duration_minutes(session) >= minimum]
            flags[day] = bool(sessions)
    return flags


def _streak(flags: Mapping[str, bool], end: str, *, target: int | None = None) -> int:
    if not _valid_date(end):
        return 0
    cursor = _dt.date.fromisoformat(end)
    count = 0
    while flags.get(cursor.isoformat()) is True:
        count += 1
        cursor -= _dt.timedelta(days=1)
        if target and count >= target:
            break
    return count


def challenge_progress(
    challenge: Mapping[str, Any], records: Mapping[str, Any], *, today: str | None = None
) -> dict[str, Any]:
    """Calculate one challenge only from real records inside its date window."""
    records = records if isinstance(records, Mapping) else {}
    today = _date(today or _dt.date.today().isoformat())
    start = _date(challenge.get("start_date"))
    configured_end = _date(challenge.get("end_date")) or today
    end = min(configured_end, today)
    target = max(0.0, _number(challenge.get("target")))
    challenge_type = str(challenge.get("challenge_type") or "")
    current = 0.0
    selected_action = str(_config(challenge, "action_id", "") or "").strip()
    selected_body_part = str(_config(challenge, "body_part", "") or "").strip()
    days = sorted(
        ((_date(key), value) for key, value in records.items()
         if _in_window(_date(key), start, end) and isinstance(value, Mapping)),
        key=lambda item: item[0],
    )
    completed_sessions: list[Mapping[str, Any]] = []
    for _, record in days:
        completed_sessions.extend(session for session in _sessions(record) if _completed_session(session))

    if challenge_type == "training_sessions":
        current = len(completed_sessions)
    elif challenge_type == "training_volume":
        for session in completed_sessions:
            if selected_action or selected_body_part:
                current += _exercise_stats(session, selected_action, selected_body_part)[0]
            else:
                try:
                    current += session_volume(TrainingSession.from_dict(dict(session)), include_warmup=False)
                except (TypeError, ValueError, KeyError):
                    current += _exercise_stats(session)[0]
        if str(challenge.get("unit") or "kg").lower() == "lbs":
            current *= KG_TO_LBS
    elif challenge_type == "max_weight":
        if selected_action:
            current = max((_exercise_stats(session, selected_action)[1] for session in completed_sessions), default=0.0)
            if str(challenge.get("unit") or "kg").lower() == "lbs":
                current *= KG_TO_LBS
    elif challenge_type == "exercise_reps":
        if _config(challenge, "any_action", False) and not selected_action:
            totals: dict[str, int] = {}
            for session in completed_sessions:
                exercises = session.get("exercises", [])
                for exercise in exercises if isinstance(exercises, list) else []:
                    if not isinstance(exercise, Mapping):
                        continue
                    identity = str(exercise.get("exercise_id") or exercise.get("name") or exercise.get("id") or "")
                    if identity:
                        totals[identity] = totals.get(identity, 0) + _exercise_stats(
                            {"exercises": [exercise]}
                        )[2]
            current = max(totals.values(), default=0)
        else:
            current = sum(_exercise_stats(session, selected_action, selected_body_part)[2] for session in completed_sessions)
    elif challenge_type == "training_sets":
        current = sum(_exercise_stats(session, selected_action, selected_body_part)[3] for session in completed_sessions)
    elif challenge_type == "heavy_sets":
        minimum = _number(_config(challenge, "min_weight"), 0)
        current = sum(_exercise_stats(session, selected_action, selected_body_part, minimum)[3] for session in completed_sessions)
    elif challenge_type in {"training_streak", "effective_training_streak", "water_streak", "nutrition_streak"}:
        current = _streak(_daily_flags(records, start, end, challenge), end)
    elif challenge_type in {"training_days", "effective_training_days"}:
        current = sum(_daily_flags(records, start, end, challenge).values())
    elif challenge_type == "cardio_sessions":
        minimum = _number(_config(challenge, "min_duration_min"), 0)
        current = sum(
            1 for session in completed_sessions
            if _cardio_duration_minutes(session) >= minimum
        )
    elif challenge_type == "time_window_sessions":
        start_hour = _number(_config(challenge, "start_hour"), 0)
        end_hour = _number(_config(challenge, "end_hour"), 24)
        for session in completed_sessions:
            try:
                hour = _dt.datetime.fromisoformat(str(session.get("started_at") or "")).hour
            except (TypeError, ValueError):
                continue
            if start_hour <= hour < end_hour:
                current += 1
    elif challenge_type == "special_day_sessions":
        rule = str(_config(challenge, "date_rule", "weekend") or "weekend")
        specified = {
            _date(item) for item in _config(challenge, "special_dates", [])
        } if isinstance(_config(challenge, "special_dates", []), list) else set()
        for day, record in days:
            if not any(_completed_session(session) for session in _sessions(record)) or not _valid_date(day):
                continue
            weekday = _dt.date.fromisoformat(day).weekday()
            if (rule == "weekend" and weekday >= 5) or (rule == "weekday" and weekday < 5) or (rule == "dates" and day in specified):
                current += 1
    elif challenge_type == "body_target":
        metric = str(_config(challenge, "metric", "weight"))
        values: list[float] = []
        for day, record in days:
            profile = record.get("profile", {})
            if not isinstance(profile, Mapping):
                continue
            if metric in {"weight", "bodyfat"}:
                measurement = normalize_body_measurement(record, day)
                value = measurement.get("weight_kg" if metric == "weight" else "bodyfat_percent")
            else:
                circumference = profile.get("circumference", {})
                value = circumference.get(metric) if isinstance(circumference, Mapping) and circumference.get("measured_at") else None
            if value not in (None, ""):
                values.append(_number(value))
        if values:
            current = values[-1]

    current = round(current, 2)
    direction = str(_config(challenge, "direction", "at_least"))
    has_measurement = challenge_type != "body_target" or bool(values)
    complete = has_measurement and target > 0 and (current <= target if direction == "at_most" else current >= target)
    if complete:
        percent = 100.0
    elif target <= 0:
        percent = 0.0
    elif direction == "at_most":
        percent = max(0.0, min(99.0, (2 - current / target) * 100)) if current > 0 else 0.0
    else:
        percent = min(99.0, current / target * 100)
    return {
        "current": current,
        "target": target,
        "unit": str(challenge.get("unit") or ""),
        "percent": round(percent, 1),
        "complete": complete,
        "start_date": start,
        "end_date": configured_end,
        "label": challenge_type_label(challenge_type),
    }


def _clean_item(value: Mapping[str, Any], *, status: str) -> dict[str, Any] | None:
    item = copy.deepcopy(dict(value))
    identity = str(item.get("id") or "").strip()
    if not identity:
        return None
    item["id"] = identity
    item["status"] = status
    return item


def normalize_challenge_state(value: Any) -> dict[str, Any]:
    """Normalize corrupted/legacy-safe state without reading old achievement data."""
    value = value if isinstance(value, Mapping) else {}
    active: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in value.get("active", []) if isinstance(value.get("active", []), list) else []:
        if not isinstance(raw, Mapping):
            continue
        item = _clean_item(raw, status="active")
        lane = str(item.get("lane") or "") if item else ""
        if not item or lane not in LANES or item["id"] in seen_ids or len(active) >= 3:
            continue
        active.append(item)
        seen_ids.add(item["id"])
    for raw in value.get("completed", []) if isinstance(value.get("completed", []), list) else []:
        if not isinstance(raw, Mapping):
            continue
        item = _clean_item(raw, status="completed")
        if not item or item["id"] in seen_ids:
            continue
        completed.append(item)
        seen_ids.add(item["id"])
    for raw in value.get("failed", []) if isinstance(value.get("failed", []), list) else []:
        if not isinstance(raw, Mapping):
            continue
        item = _clean_item(raw, status="failed")
        if not item or item["id"] in seen_ids:
            continue
        failed.append(item)
        seen_ids.add(item["id"])
    completed_ids = {item["id"] for item in completed}
    pending = list(dict.fromkeys(
        str(item) for item in value.get("pending_celebrations", [])
        if str(item) in completed_ids
    )) if isinstance(value.get("pending_celebrations", []), list) else []
    celebrated = list(dict.fromkeys(
        str(item) for item in value.get("celebrated", []) if str(item)
    )) if isinstance(value.get("celebrated", []), list) else []
    pending = [identity for identity in pending if identity not in celebrated]
    failed_ids = {item["id"] for item in failed}
    pending_failures = list(dict.fromkeys(
        str(item) for item in value.get("pending_failures", [])
        if str(item) in failed_ids
    )) if isinstance(value.get("pending_failures", []), list) else []
    acknowledged_failures = list(dict.fromkeys(
        str(item) for item in value.get("acknowledged_failures", []) if str(item)
    )) if isinstance(value.get("acknowledged_failures", []), list) else []
    pending_failures = [identity for identity in pending_failures if identity not in acknowledged_failures]
    return {
        "version": 2,
        "active": active,
        "completed": completed,
        "failed": failed,
        "pending_celebrations": pending,
        "celebrated": celebrated,
        "pending_failures": pending_failures,
        "acknowledged_failures": acknowledged_failures,
    }


def _dates_for_template(base: Mapping[str, Any], now_date: str) -> tuple[str, str]:
    config = base.get("config", {}) if isinstance(base.get("config"), Mapping) else {}
    configured_days = 30 if config.get("calendar_month") else _number(
        config.get("window_days"), base.get("target", 30)
    )
    days = max(1, int(configured_days))
    start = _dt.date.fromisoformat(now_date)
    end = start + _dt.timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def create_challenge(
    template_or_data: ChallengeTemplate | Mapping[str, Any], *, now: str | None = None, **overrides: Any
) -> dict[str, Any]:
    base = template_or_data.to_dict() if isinstance(template_or_data, ChallengeTemplate) else copy.deepcopy(dict(template_or_data))
    now_value = now or _dt.datetime.now().isoformat(timespec="seconds")
    now_date = _date(now_value)
    if not _valid_date(now_date):
        raise ValueError("创建时间格式不正确")
    is_template = bool(base.get("chain_id"))
    default_start, default_end = _dates_for_template(base, now_date) if is_template else (
        now_date,
        (_dt.date.fromisoformat(now_date) + _dt.timedelta(days=30)).isoformat(),
    )
    config = copy.deepcopy(base.get("config", {})) if isinstance(base.get("config"), Mapping) else {}
    for key in ("action_id", "daily_target", "indicator", "metric", "direction", "window_days"):
        if key in config and key not in base:
            base[key] = config[key]
    template_id = str(base.get("template_id") or base.get("id") or "") if is_template else ""
    result = {
        "id": uuid.uuid4().hex,
        "template_id": template_id,
        "title": "目标挑战",
        "declaration": "",
        "lane": TYPE_LANES.get(str(base.get("challenge_type") or ""), "training"),
        "challenge_type": "training_sessions",
        "target": 1.0,
        "unit": "次",
        "start_date": default_start,
        "end_date": default_end,
        "status": "active",
        "created_at": now_value,
        "level": None,
        "level_name": "自定义",
        "level_color": "#B98518",
        **base,
        **overrides,
    }
    result["id"] = uuid.uuid4().hex
    result["template_id"] = template_id
    result["status"] = "active"
    result["created_at"] = now_value
    if result.get("level") is not None:
        info = level_info(result["level"])
        result.update({"level_name": info["name"], "level_color": info["color"]})
    validate_challenge(result)
    return result


def validate_challenge(challenge: Mapping[str, Any]) -> None:
    title = str(challenge.get("title") or "").strip()
    challenge_type = str(challenge.get("challenge_type") or "")
    lane = str(challenge.get("lane") or "")
    start = _date(challenge.get("start_date"))
    end = _date(challenge.get("end_date"))
    if not title:
        raise ValueError("请输入挑战名称")
    if challenge_type not in TYPE_LANES:
        raise ValueError("请选择支持的挑战类型")
    if lane not in LANES:
        raise ValueError("请选择挑战所属赛道")
    if _number(challenge.get("target")) <= 0:
        raise ValueError("目标值必须大于 0")
    if not _valid_date(start) or not _valid_date(end) or start > end:
        raise ValueError("挑战日期范围不正确")
    if challenge_type in {"max_weight"} and not str(_config(challenge, "action_id", "")).strip():
        raise ValueError("请选择一个训练动作")
    if challenge_type == "heavy_sets" and _number(_config(challenge, "min_weight")) <= 0:
        raise ValueError("大重量组数必须设置大于 0 的重量门槛")
    if challenge_type in {"effective_training_days", "effective_training_streak", "cardio_sessions"} and _number(_config(challenge, "min_duration_min")) <= 0:
        raise ValueError("请设置大于 0 的单次最低时长")
    if challenge_type == "time_window_sessions":
        start_hour = _number(_config(challenge, "start_hour"), -1)
        end_hour = _number(_config(challenge, "end_hour"), -1)
        if not 0 <= start_hour < end_hour <= 24:
            raise ValueError("训练时间段必须满足 0 ≤ 开始小时 < 结束小时 ≤ 24")
    if challenge_type == "special_day_sessions":
        rule = str(_config(challenge, "date_rule", ""))
        if rule not in {"weekend", "weekday", "dates"}:
            raise ValueError("请选择特殊日期类型")
        special_dates = _config(challenge, "special_dates", [])
        if rule == "dates" and (
            not isinstance(special_dates, list) or not special_dates
            or any(not _valid_date(_date(item)) for item in special_dates)
        ):
            raise ValueError("请按 YYYY-MM-DD 填写至少一个有效日期")
    if challenge_type == "water_streak" and _number(_config(challenge, "daily_target")) <= 0:
        raise ValueError("每日饮水目标必须大于 0")
    if challenge_type == "nutrition_streak" and str(_config(challenge, "indicator", "")) not in {"protein", "carb_cycle"}:
        raise ValueError("请选择饮食达标指标")
    if challenge_type == "body_target" and not str(_config(challenge, "metric", "")).strip():
        raise ValueError("请选择身体指标")


def challenge_failure_reason(
    challenge: Mapping[str, Any], records: Mapping[str, Any], *, today: str
) -> str:
    """Detect a real deadline miss or a streak broken after the challenge was created."""
    today_value = _date(today)
    if not _valid_date(today_value):
        return ""
    end = _date(challenge.get("end_date"))
    if _valid_date(end) and today_value > end:
        return "挑战已超过结束日期，目标仍未完成"

    challenge_type = str(challenge.get("challenge_type") or "")
    if challenge_type not in {
        "training_streak", "effective_training_streak", "water_streak", "nutrition_streak",
    }:
        return ""
    valid_starts = [
        value for value in (_date(challenge.get("start_date")), _date(challenge.get("created_at")))
        if _valid_date(value)
    ]
    if not valid_starts:
        return ""
    monitor_start = max(valid_starts)
    cursor = _dt.date.fromisoformat(monitor_start)
    last_closed_day = _dt.date.fromisoformat(today_value) - _dt.timedelta(days=1)
    if _valid_date(end):
        last_closed_day = min(last_closed_day, _dt.date.fromisoformat(end))
    if cursor > last_closed_day:
        return ""
    flags = _daily_flags(records, monitor_start, last_closed_day.isoformat(), challenge)
    started = False
    while cursor <= last_closed_day:
        if flags.get(cursor.isoformat()) is True:
            started = True
        elif started:
            return "连续记录已经中断"
        cursor += _dt.timedelta(days=1)
    return ""


def recalculate_state(
    stored: Any, records: Mapping[str, Any], *, now: str | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = normalize_challenge_state(stored)
    now_value = now or _dt.datetime.now().isoformat(timespec="seconds")
    completed_now: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for challenge in state["active"]:
        progress = challenge_progress(challenge, records, today=_date(now_value))
        challenge.update({
            "current": progress["current"],
            "progress_percent": progress["percent"],
            "last_calculated_at": now_value,
        })
        if progress["complete"]:
            challenge.update({
                "status": "completed",
                "completed_at": now_value,
                "completed_value": progress["current"],
                "final_progress": progress["current"],
            })
            state["completed"].insert(0, challenge)
            if challenge["id"] not in state["celebrated"] and challenge["id"] not in state["pending_celebrations"]:
                state["pending_celebrations"].append(challenge["id"])
            completed_now.append(copy.deepcopy(challenge))
        else:
            failure_reason = challenge_failure_reason(challenge, records, today=_date(now_value))
            if failure_reason:
                challenge.update({
                    "status": "failed",
                    "failed_at": now_value,
                    "failure_reason": failure_reason,
                    "failed_value": progress["current"],
                    "final_progress": progress["current"],
                })
                state["failed"].insert(0, challenge)
                if challenge["id"] not in state["acknowledged_failures"] and challenge["id"] not in state["pending_failures"]:
                    state["pending_failures"].append(challenge["id"])
            else:
                remaining.append(challenge)
    state["active"] = remaining
    return state, completed_now


def add_challenge(
    stored: Any,
    challenge: Mapping[str, Any],
    records: Mapping[str, Any],
    *,
    now: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = normalize_challenge_state(stored)
    item = copy.deepcopy(dict(challenge))
    validate_challenge(item)
    lane = str(item.get("lane"))
    if len(state["active"]) >= 3:
        raise ValueError("进行中挑战最多三项")
    state["active"].append(item)
    state, completed = recalculate_state(state, records, now=now)
    saved = completed[0] if completed else next(active for active in state["active"] if active["id"] == item["id"])
    return state, copy.deepcopy(saved)


def delete_active_challenges(stored: Any, identities: Sequence[str]) -> tuple[dict[str, Any], int]:
    state = normalize_challenge_state(stored)
    selected = {str(identity) for identity in identities if str(identity)}
    before = len(state["active"])
    state["active"] = [item for item in state["active"] if item["id"] not in selected]
    return state, before - len(state["active"])


def consume_next_celebration(stored: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
    state = normalize_challenge_state(stored)
    while state["pending_celebrations"]:
        identity = state["pending_celebrations"].pop(0)
        if identity not in state["celebrated"]:
            state["celebrated"].append(identity)
        item = next((entry for entry in state["completed"] if entry["id"] == identity), None)
        if item:
            return state, copy.deepcopy(item)
    return state, None


def consume_pending_celebrations(stored: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = normalize_challenge_state(stored)
    completed_by_id = {item["id"]: item for item in state["completed"]}
    consumed = []
    for identity in state["pending_celebrations"]:
        if identity not in state["celebrated"]:
            state["celebrated"].append(identity)
        item = completed_by_id.get(identity)
        if item is not None:
            consumed.append(copy.deepcopy(item))
    state["pending_celebrations"] = []
    return state, consumed


def consume_pending_failures(stored: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = normalize_challenge_state(stored)
    failed_by_id = {item["id"]: item for item in state["failed"]}
    consumed = []
    for identity in state["pending_failures"]:
        if identity not in state["acknowledged_failures"]:
            state["acknowledged_failures"].append(identity)
        item = failed_by_id.get(identity)
        if item is not None:
            consumed.append(copy.deepcopy(item))
    state["pending_failures"] = []
    return state, consumed


def mark_failed_retried(stored: Any, identity: str, *, now: str | None = None) -> dict[str, Any]:
    state = normalize_challenge_state(stored)
    retried_at = now or _dt.datetime.now().isoformat(timespec="seconds")
    for item in state["failed"]:
        if item["id"] == str(identity):
            item["retried_at"] = retried_at
            break
    state["pending_failures"] = [item for item in state["pending_failures"] if item != str(identity)]
    if str(identity) not in state["acknowledged_failures"]:
        state["acknowledged_failures"].append(str(identity))
    return state


def visible_recommendations(
    stored: Any,
    records: Mapping[str, Any] | None = None,
    *,
    today: str | None = None,
    profile: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    state = normalize_challenge_state(stored)
    completed_levels: dict[str, int] = {}
    for item in state["completed"]:
        chain_id = str(item.get("chain_id") or "")
        if chain_id:
            completed_levels[chain_id] = max(completed_levels.get(chain_id, -1), int(item.get("level", -1)))
    active_chains = {str(item.get("chain_id")) for item in state["active"] if item.get("chain_id")}
    chains: dict[str, list[ChallengeTemplate]] = {}
    for template in recommended_templates(profile):
        chains.setdefault(template.chain_id, []).append(template)

    visible = []
    for chain_id, templates in chains.items():
        if chain_id in active_chains:
            continue
        config = templates[0].config if templates else {}
        if config.get("repeatable_same"):
            visible.append(templates[0].to_dict())
            continue
        if config.get("one_time") and completed_levels.get(chain_id, -1) >= 0:
            continue
        next_level = completed_levels.get(chain_id, -1) + 1
        candidates = [template for template in templates if template.level >= next_level]
        if not candidates:
            highest = max(templates, key=lambda item: item.level)
            if highest.challenge_type == "body_target":
                if records is not None and not recommendation_progress(highest, records, today=today)["complete"]:
                    visible.append(highest.to_dict())
                continue
            selected = repeatable_template(templates, next_level)
            if records is not None:
                for extended_level in range(next_level, next_level + 100):
                    candidate = repeatable_template(templates, extended_level)
                    if not recommendation_progress(candidate, records, today=today)["complete"]:
                        break
                    selected = candidate
            visible.append(selected.to_dict())
            continue
        selected = candidates[0]
        if records is not None:
            for candidate in candidates:
                progress = recommendation_progress(candidate, records, today=today)
                if not progress["complete"]:
                    break
                selected = candidate
        visible.append(selected.to_dict())
    return visible


def recommendation_progress(
    template: ChallengeTemplate | Mapping[str, Any], records: Mapping[str, Any], *, today: str | None = None
) -> dict[str, Any]:
    now_date = _date(today or _dt.date.today().isoformat())
    preview = create_challenge(template, now=f"{now_date}T00:00:00")
    return challenge_progress(preview, records, today=now_date)


def filter_recommendations_by_lane(
    recommendations: Sequence[Mapping[str, Any]], lane: str = "all"
) -> list[dict[str, Any]]:
    selected = str(lane or "all")
    if selected != "all" and selected not in LANES:
        return []
    return [
        copy.deepcopy(dict(item))
        for item in recommendations
        if isinstance(item, Mapping) and (selected == "all" or item.get("lane") == selected)
    ]


def lane_available(stored: Any, lane: str) -> bool:
    return lane in LANES and len(normalize_challenge_state(stored)["active"]) < 3


__all__ = [
    "add_challenge", "challenge_failure_reason", "challenge_progress", "consume_next_celebration", "consume_pending_celebrations", "consume_pending_failures", "create_challenge",
    "delete_active_challenges", "filter_recommendations_by_lane", "lane_available", "normalize_challenge_state",
    "mark_failed_retried", "recalculate_state", "recommendation_progress", "validate_challenge",
    "visible_recommendations",
]

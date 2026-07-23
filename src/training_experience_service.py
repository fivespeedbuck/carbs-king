"""Pure helpers for workout reuse, exercise ranking, and rest cycles."""

from __future__ import annotations

import copy
import datetime as dt
from decimal import Decimal, InvalidOperation
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from uuid import uuid4

from training_models import normalize_group_type, normalize_recording_mode
from training_service import migrate_legacy_training, raw_training_sessions


BODY_PART_ORDER = ("胸", "背", "肩", "腿", "二头", "三头", "腹", "有氧")
WEIGHT_STEP_KG = Decimal("1.25")
MAX_WEIGHT_KG = Decimal("1000")
_BODY_PART_ALIASES = {
    "胸部": "胸", "背部": "背", "肩部": "肩", "腿部": "腿",
    "肱二头肌": "二头", "二头肌": "二头", "手臂二头": "二头",
    "肱三头肌": "三头", "三头肌": "三头", "手臂三头": "三头",
    "腹部": "腹", "核心": "腹", "核心肌群": "腹", "心肺": "有氧",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _iso(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def normalize_weight_input(value: Any) -> float:
    text = str(value or "").strip().replace("，", ",").replace(",", ".")
    if not text:
        raise ValueError("重量不能为空")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("请输入有效重量") from exc
    if not number.is_finite() or number < 0 or number > MAX_WEIGHT_KG:
        raise ValueError("重量需在 0-1000 kg 之间")
    return float(number.quantize(Decimal("0.01")))


def adjust_weight_kg(value: Any, steps: int) -> float:
    try:
        current = Decimal(str(value if value not in (None, "") else 0))
    except InvalidOperation:
        current = Decimal("0")
    adjusted = min(MAX_WEIGHT_KG, max(Decimal("0"), current + WEIGHT_STEP_KG * int(steps)))
    return float(adjusted.quantize(Decimal("0.01")))


def format_weight_kg(value: Any) -> str:
    number = Decimal(str(normalize_weight_input(value))).quantize(Decimal("0.01"))
    return format(number.normalize(), "f")


def _iso_text(value: dt.datetime) -> str:
    return value.isoformat(timespec="seconds")


def _session_sort_key(session: Mapping[str, Any], record_date: str) -> tuple[str, str, str]:
    return (
        str(session.get("date") or record_date),
        str(session.get("ended_at") or session.get("started_at") or ""),
        str(session.get("id") or ""),
    )


def normalize_body_part(value: Any) -> str:
    part = str(value or "").strip()
    return _BODY_PART_ALIASES.get(part, part)


def session_body_parts(session: Mapping[str, Any]) -> tuple[str, ...]:
    """Return unique known body parts in the product's fixed display order."""
    seen: set[str] = set()
    extras: list[str] = []
    exercises = session.get("exercises", [])
    if not isinstance(exercises, list):
        return ()
    for exercise in exercises:
        if not isinstance(exercise, Mapping):
            continue
        part = normalize_body_part(exercise.get("body_part", exercise.get("target")))
        if not part or part in seen:
            continue
        seen.add(part)
        if part not in BODY_PART_ORDER:
            extras.append(part)
    return tuple(part for part in BODY_PART_ORDER if part in seen) + tuple(sorted(extras))


def _has_completed_set(session: Mapping[str, Any]) -> bool:
    for exercise in session.get("exercises", []) if isinstance(session.get("exercises"), list) else []:
        if not isinstance(exercise, Mapping):
            continue
        for training_set in exercise.get("sets", []) if isinstance(exercise.get("sets"), list) else []:
            if isinstance(training_set, Mapping) and training_set.get("completed"):
                return True
    return False


def _is_effective_session(session: Mapping[str, Any]) -> bool:
    """Accept completed real sessions and set-less legacy sessions without inventing work."""
    exercises = [
        item for item in session.get("exercises", [])
        if isinstance(item, Mapping) and (str(item.get("name") or "").strip() or str(item.get("body_part") or "").strip())
    ] if isinstance(session.get("exercises"), list) else []
    if not exercises or session.get("status") not in {"completed", "incomplete"}:
        return False
    has_structured_work = any(
        normalize_recording_mode(item.get("recording_mode")) != "strength"
        or (isinstance(item.get("sets"), list) and item.get("sets"))
        for item in exercises
    )
    if not has_structured_work:
        return True
    return _has_completed_set(session) or any(
        normalize_recording_mode(item.get("recording_mode")) != "strength" and item.get("completed")
        for item in exercises
    )


def _record_sessions(records: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(records, Mapping):
        return []
    result: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for key, raw_record in records.items():
        if not isinstance(raw_record, Mapping):
            continue
        record_date = str(raw_record.get("date") or key)
        training = raw_record.get("training")
        structured = raw_training_sessions(training)
        if structured:
            candidates = structured
        else:
            migrated = migrate_legacy_training(training, record_date)
            candidates = [migrated.to_dict()] if migrated is not None else []
        for session in candidates:
            identity = str(session.get("id") or "")
            dedupe = identity or repr(session)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            snapshot = copy.deepcopy(dict(session))
            snapshot.setdefault("date", record_date)
            result.append((record_date, snapshot))
    return result


def history_training_cards(records: Any, body_part: str | None = None) -> list[dict[str, Any]]:
    """Return the latest effective whole workout for each body-part combination."""
    requested = normalize_body_part(body_part)
    latest: dict[tuple[str, ...], tuple[tuple[str, str, str], dict[str, Any]]] = {}
    for record_date, session in _record_sessions(records):
        if not _is_effective_session(session):
            continue
        parts = session_body_parts(session)
        if not parts or (requested and requested not in parts):
            continue
        key = _session_sort_key(session, record_date)
        if parts not in latest or key > latest[parts][0]:
            latest[parts] = (key, session)
    cards = []
    for parts, (sort_key, session) in latest.items():
        cards.append({
            "combination": "+".join(parts),
            "body_parts": list(parts),
            "date": str(session.get("date") or sort_key[0]),
            "session_id": str(session.get("id") or ""),
            "exercise_count": len(session.get("exercises", [])),
            "session": copy.deepcopy(session),
        })
    return sorted(cards, key=lambda item: (item["date"], item["session"].get("ended_at", ""), item["combination"]), reverse=True)


def copy_whole_session(
    source_session: Mapping[str, Any],
    current_session: Mapping[str, Any] | None = None,
    *,
    mode: str = "replace",
    new_date: str | None = None,
    id_factory: Callable[[str], str] = _new_id,
) -> dict[str, Any]:
    """Copy a complete workout plan, rebuilding IDs and clearing execution state."""
    if mode not in {"replace", "append"}:
        raise ValueError("mode must be 'replace' or 'append'")
    if not isinstance(source_session, Mapping) or not session_body_parts(source_session):
        raise ValueError("source_session must contain a complete workout combination")
    raw_exercises = source_session.get("exercises", [])
    if not isinstance(raw_exercises, list):
        raise ValueError("source_session exercises must be a list")

    replacement_session_id = id_factory("session") if mode == "replace" else ""
    copied_exercises: list[dict[str, Any]] = []
    exercise_id_map: dict[str, str] = {}
    for raw_exercise in raw_exercises:
        if not isinstance(raw_exercise, Mapping):
            continue
        exercise = copy.deepcopy(dict(raw_exercise))
        old_id = str(exercise.get("id") or "")
        exercise["id"] = id_factory("session_exercise")
        if old_id:
            exercise_id_map[old_id] = exercise["id"]
        exercise["recording_mode"] = normalize_recording_mode(exercise.get("recording_mode"))
        exercise["completed"] = False
        exercise["completed_at"] = ""
        raw_sets = exercise.get("sets", [])
        exercise["sets"] = []
        if isinstance(raw_sets, list):
            for index, raw_set in enumerate(raw_sets, 1):
                if not isinstance(raw_set, Mapping):
                    continue
                training_set = copy.deepcopy(dict(raw_set))
                training_set.update({
                    "id": id_factory("set"), "order": index, "completed": False,
                    "completed_at": "", "rir": None, "rpe": None,
                })
                exercise["sets"].append(training_set)
        copied_exercises.append(exercise)
    if not copied_exercises:
        raise ValueError("source_session has no copyable exercises")

    copied_groups: list[dict[str, Any]] = []
    for raw_group in source_session.get("exercise_groups", []) if isinstance(source_session.get("exercise_groups"), list) else []:
        if not isinstance(raw_group, Mapping):
            continue
        member_ids = [exercise_id_map.get(str(item), "") for item in raw_group.get("exercise_ids", [])]
        member_ids = [item for item in member_ids if item]
        group_type = normalize_group_type(raw_group.get("group_type", raw_group.get("type")))
        if group_type and len(member_ids) >= 2:
            copied_groups.append({
                "id": id_factory("exercise_group"),
                "group_type": group_type,
                "order": len(copied_groups) + 1,
                "exercise_ids": member_ids,
            })

    if mode == "append":
        if not isinstance(current_session, Mapping):
            raise ValueError("append mode requires current_session")
        result = copy.deepcopy(dict(current_session))
        existing = result.get("exercises", [])
        result["exercises"] = [copy.deepcopy(item) for item in existing if isinstance(item, Mapping)] if isinstance(existing, list) else []
        result["exercises"].extend(copied_exercises)
        existing_groups = result.get("exercise_groups", [])
        result["exercise_groups"] = [copy.deepcopy(item) for item in existing_groups if isinstance(item, Mapping)] if isinstance(existing_groups, list) else []
        result["exercise_groups"].extend(copied_groups)
    else:
        result = {
            "id": replacement_session_id,
            "date": new_date if new_date is not None else str(source_session.get("date") or ""),
            "status": "planned",
            "exercises": copied_exercises,
            "exercise_groups": copied_groups,
        }

    for index, exercise in enumerate(result["exercises"], 1):
        exercise["order"] = index
    result["exercise_groups"] = normalize_exercise_groups(result["exercises"], result.get("exercise_groups", []))
    result.update({
        "status": "planned", "started_at": "", "ended_at": "",
        "total_duration_min": None, "summary_note": "", "fatigue_status": "",
        "rest_until": "", "rest_cycle": None, "incomplete": False,
    })
    if new_date is not None:
        result["date"] = new_date
    return result


def exercise_usage_stats(records: Any) -> dict[str, dict[str, Any]]:
    """Count effective sessions per exercise and retain its most recent date."""
    stats: dict[str, dict[str, Any]] = {}
    for record_date, session in _record_sessions(records):
        if not _is_effective_session(session):
            continue
        seen_in_session: set[str] = set()
        for exercise in session.get("exercises", []):
            if not isinstance(exercise, Mapping):
                continue
            name = str(exercise.get("name") or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen_in_session:
                continue
            seen_in_session.add(key)
            date = str(session.get("date") or record_date)
            entry = stats.setdefault(key, {"name": name, "session_count": 0, "last_date": ""})
            entry["session_count"] += 1
            entry["last_date"] = max(entry["last_date"], date)
    return stats


def sort_exercises(exercises: Sequence[Mapping[str, Any]], stats: Mapping[str, Mapping[str, Any]], mode: str = "frequent") -> list[dict[str, Any]]:
    """Sort library entries by frequent use, recency, or name without mutation."""
    if mode not in {"frequent", "recent", "name"}:
        raise ValueError("mode must be 'frequent', 'recent', or 'name'")
    result = [copy.deepcopy(dict(item)) for item in exercises if isinstance(item, Mapping)]

    def usage(item: Mapping[str, Any]) -> Mapping[str, Any]:
        return stats.get(str(item.get("name") or "").strip().casefold(), {})

    result.sort(key=lambda item: str(item.get("name") or "").casefold())
    if mode == "frequent":
        result.sort(key=lambda item: str(usage(item).get("last_date", "")), reverse=True)
        result.sort(key=lambda item: int(usage(item).get("session_count", 0)), reverse=True)
        return result
    if mode == "recent":
        result.sort(key=lambda item: int(usage(item).get("session_count", 0)), reverse=True)
        result.sort(key=lambda item: str(usage(item).get("last_date", "")), reverse=True)
        return result
    return result


def reorder_session_exercises(exercises: Sequence[Mapping[str, Any]], dragged_id: str, target_id: str) -> list[dict[str, Any]]:
    """Move one complete exercise by stable ID without detaching its nested set data."""
    result = [copy.deepcopy(dict(item)) for item in exercises if isinstance(item, Mapping)]
    ids = [str(item.get("id") or "") for item in result]
    if not dragged_id or not target_id or dragged_id == target_id or dragged_id not in ids or target_id not in ids:
        return result
    dragged_index = ids.index(dragged_id)
    original_target_index = ids.index(target_id)
    moved = result.pop(dragged_index)
    target_index = next(index for index, item in enumerate(result) if str(item.get("id") or "") == target_id)
    result.insert(target_index + (1 if dragged_index < original_target_index else 0), moved)
    for index, item in enumerate(result, 1):
        item["order"] = index
    return result


def reorder_session_exercise_blocks(
    exercises: Sequence[Mapping[str, Any]],
    groups: Sequence[Mapping[str, Any]],
    dragged_id: str,
    target_id: str,
) -> list[dict[str, Any]]:
    """Move a normal exercise or an entire exercise group as one visible block."""
    result = [copy.deepcopy(dict(item)) for item in exercises if isinstance(item, Mapping)]
    ids = [str(item.get("id") or "") for item in result]
    if not dragged_id or not target_id or dragged_id == target_id or dragged_id not in ids or target_id not in ids:
        return result

    position = {exercise_id: index for index, exercise_id in enumerate(ids)}
    normalized_groups = normalize_exercise_groups(result, groups)

    def block_for(exercise_id: str) -> list[str]:
        exercise = result[position[exercise_id]]
        group_id = str(exercise.get("group_id") or "")
        group = next((item for item in normalized_groups if str(item.get("id") or "") == group_id), None)
        if not group:
            return [exercise_id]
        return [item for item in group.get("exercise_ids", []) if item in position]

    dragged_block = block_for(dragged_id)
    target_block = block_for(target_id)
    if not dragged_block or not target_block or dragged_block == target_block:
        return result

    dragged_set = set(dragged_block)
    remaining = [item for item in result if str(item.get("id") or "") not in dragged_set]
    remaining_ids = [str(item.get("id") or "") for item in remaining]
    target_positions = [remaining_ids.index(item) for item in target_block if item in remaining_ids]
    if not target_positions:
        return result
    insert_at = min(target_positions)
    if min(position[item] for item in dragged_block) < min(position[item] for item in target_block):
        insert_at = max(target_positions) + 1

    by_id = {str(item.get("id") or ""): item for item in result}
    moved = [by_id[item] for item in dragged_block if item in by_id]
    reordered = remaining[:insert_at] + moved + remaining[insert_at:]
    for index, item in enumerate(reordered, 1):
        item["order"] = index
    normalize_exercise_groups(reordered, groups)
    return reordered


def preview_session_exercise_block_order(
    exercises: Sequence[Mapping[str, Any]],
    groups: Sequence[Mapping[str, Any]],
    dragged_id: str,
    target_id: str,
) -> list[str]:
    """Return visible block leaders in their drop-preview order without mutation."""
    reordered = reorder_session_exercise_blocks(exercises, groups, dragged_id, target_id)
    normalized_groups = normalize_exercise_groups(reordered, groups)
    leader_by_member = {
        str(member_id): str(group.get("exercise_ids", [""])[0])
        for group in normalized_groups
        for member_id in group.get("exercise_ids", [])
        if group.get("exercise_ids")
    }
    visible: list[str] = []
    for exercise in reordered:
        exercise_id = str(exercise.get("id") or "")
        if not exercise_id:
            continue
        leader_id = leader_by_member.get(exercise_id, exercise_id)
        if leader_id not in visible:
            visible.append(leader_id)
    return visible


def normalize_exercise_groups(
    exercises: Sequence[Mapping[str, Any]], groups: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Drop broken memberships and synchronize group/member order by stable IDs."""
    position = {
        str(item.get("id") or ""): index
        for index, item in enumerate(exercises)
        if isinstance(item, Mapping) and str(item.get("id") or "")
    }
    claimed: set[str] = set()
    result: list[dict[str, Any]] = []
    for raw_group in groups if isinstance(groups, Sequence) else []:
        if not isinstance(raw_group, Mapping):
            continue
        group_type = normalize_group_type(raw_group.get("group_type", raw_group.get("type")))
        raw_ids = raw_group.get("exercise_ids", [])
        member_ids = [
            str(item) for item in raw_ids
            if str(item) in position and str(item) not in claimed
        ] if isinstance(raw_ids, list) else []
        member_ids = sorted(dict.fromkeys(member_ids), key=position.get)
        if not group_type or len(member_ids) < 2:
            continue
        group_id = str(raw_group.get("id") or _new_id("exercise_group"))
        result.append({
            "id": group_id,
            "group_type": group_type,
            "order": len(result) + 1,
            "exercise_ids": member_ids,
        })
        claimed.update(member_ids)

    by_id = {str(item.get("id") or ""): item for item in exercises if isinstance(item, dict)}
    for exercise in by_id.values():
        exercise["group_id"] = ""
        exercise["group_order"] = None
    for group in result:
        for member_order, exercise_id in enumerate(group["exercise_ids"], 1):
            exercise = by_id.get(exercise_id)
            if exercise is not None:
                exercise["group_id"] = group["id"]
                exercise["group_order"] = member_order
    return result


def create_exercise_group(
    exercises: Sequence[Mapping[str, Any]],
    groups: Sequence[Mapping[str, Any]],
    exercise_ids: Sequence[str],
    group_type: str,
    *,
    id_factory: Callable[[str], str] = _new_id,
) -> list[dict[str, Any]]:
    normalized_type = normalize_group_type(group_type)
    selected = list(dict.fromkeys(str(item) for item in exercise_ids if str(item)))
    valid_ids = {str(item.get("id") or "") for item in exercises if isinstance(item, Mapping)}
    if not normalized_type:
        raise ValueError("group_type must be 'superset' or 'compound'")
    if len(selected) < 2 or any(item not in valid_ids for item in selected):
        raise ValueError("an exercise group requires at least two valid exercises")
    selected_set = set(selected)
    retained: list[dict[str, Any]] = []
    for raw_group in groups if isinstance(groups, Sequence) else []:
        if not isinstance(raw_group, Mapping):
            continue
        remaining = [str(item) for item in raw_group.get("exercise_ids", []) if str(item) not in selected_set]
        if len(remaining) >= 2:
            retained.append({**copy.deepcopy(dict(raw_group)), "exercise_ids": remaining})
    retained.append({
        "id": id_factory("exercise_group"),
        "group_type": normalized_type,
        "order": len(retained) + 1,
        "exercise_ids": selected,
    })
    return normalize_exercise_groups(exercises, retained)


def next_group_work(
    session: Mapping[str, Any], current_exercise_id: str, current_round: int
) -> dict[str, Any] | None:
    """Return the next pending group member and whether a grouped round just closed."""
    exercises = [item for item in session.get("exercises", []) if isinstance(item, Mapping)] if isinstance(session.get("exercises"), list) else []
    by_id = {str(item.get("id") or ""): item for item in exercises}
    current = by_id.get(str(current_exercise_id))
    if current is None:
        return None
    group_id = str(current.get("group_id") or "")
    group = next((
        item for item in session.get("exercise_groups", [])
        if isinstance(item, Mapping) and str(item.get("id") or "") == group_id
    ), None)
    if group is None:
        return None
    member_ids = [str(item) for item in group.get("exercise_ids", []) if str(item) in by_id]
    if current_exercise_id not in member_ids:
        return None

    def pending(exercise_id: str, round_index: int) -> bool:
        exercise = by_id[exercise_id]
        if normalize_recording_mode(exercise.get("recording_mode")) == "strength":
            sets = exercise.get("sets", [])
            return isinstance(sets, list) and round_index < len(sets) and isinstance(sets[round_index], Mapping) and not sets[round_index].get("completed")
        return round_index == 0 and not exercise.get("completed")

    current_position = member_ids.index(current_exercise_id)
    for exercise_id in member_ids[current_position + 1:] + member_ids[:current_position + 1]:
        if pending(exercise_id, current_round):
            return {"exercise_id": exercise_id, "set_index": current_round, "grouped_round_complete": False, "group_complete": False}
    max_rounds = max(
        len(by_id[exercise_id].get("sets", []))
        if normalize_recording_mode(by_id[exercise_id].get("recording_mode")) == "strength" else 1
        for exercise_id in member_ids
    )
    for next_round in range(current_round + 1, max_rounds):
        for exercise_id in member_ids:
            if pending(exercise_id, next_round):
                return {"exercise_id": exercise_id, "set_index": next_round, "grouped_round_complete": True, "group_complete": False}
    return {"exercise_id": "", "set_index": 0, "grouped_round_complete": True, "group_complete": True}


def start_rest_cycle(duration_seconds: int, now: dt.datetime, *, id_factory: Callable[[str], str] = _new_id) -> dict[str, Any]:
    seconds = max(0, int(duration_seconds))
    return {
        "id": id_factory("rest"), "status": "running", "started_at": _iso_text(now),
        "ends_at": _iso_text(now + dt.timedelta(seconds=seconds)),
        "paused_remaining_seconds": None, "skipped": False, "notified": False,
        "notified_at": "", "ended_at": "",
    }


def rest_remaining_seconds(cycle: Mapping[str, Any], now: dt.datetime) -> int:
    if cycle.get("status") == "paused":
        return max(0, int(cycle.get("paused_remaining_seconds") or 0))
    if cycle.get("status") in {"skipped", "finished"}:
        return 0
    ends_at = _iso(cycle.get("ends_at"))
    if ends_at is None:
        return 0
    current = now
    if ends_at.tzinfo is not None and current.tzinfo is None:
        current = current.replace(tzinfo=ends_at.tzinfo)
    elif ends_at.tzinfo is None and current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    return max(0, int((ends_at - current).total_seconds()))


def adjust_rest_cycle(cycle: Mapping[str, Any], delta_seconds: int, now: dt.datetime) -> dict[str, Any]:
    result = copy.deepcopy(dict(cycle))
    if result.get("status") not in {"running", "paused"}:
        return result
    remaining = max(0, rest_remaining_seconds(result, now) + int(delta_seconds))
    if remaining == 0:
        result["status"] = "running"
        result["ends_at"] = _iso_text(now)
        result["paused_remaining_seconds"] = None
    elif result.get("status") == "paused":
        result["paused_remaining_seconds"] = remaining
    else:
        result["ends_at"] = _iso_text(now + dt.timedelta(seconds=remaining))
    return result


def pause_rest_cycle(cycle: Mapping[str, Any], now: dt.datetime) -> dict[str, Any]:
    result = copy.deepcopy(dict(cycle))
    if result.get("status") == "running":
        result["paused_remaining_seconds"] = rest_remaining_seconds(result, now)
        result["status"] = "paused"
    return result


def resume_rest_cycle(cycle: Mapping[str, Any], now: dt.datetime) -> dict[str, Any]:
    result = copy.deepcopy(dict(cycle))
    if result.get("status") == "paused":
        remaining = max(0, int(result.get("paused_remaining_seconds") or 0))
        result["ends_at"] = _iso_text(now + dt.timedelta(seconds=remaining))
        result["paused_remaining_seconds"] = None
        result["status"] = "running"
    return result


def skip_rest_cycle(cycle: Mapping[str, Any], now: dt.datetime) -> dict[str, Any]:
    result = copy.deepcopy(dict(cycle))
    if result.get("status") not in {"finished", "skipped"}:
        result.update({"status": "skipped", "skipped": True, "ended_at": _iso_text(now), "paused_remaining_seconds": None})
    return result


def finish_rest_cycle(cycle: Mapping[str, Any], now: dt.datetime) -> tuple[dict[str, Any], bool]:
    """Finish a naturally elapsed cycle and atomically claim its one notification."""
    result = copy.deepcopy(dict(cycle))
    if result.get("status") != "running" or rest_remaining_seconds(result, now) > 0:
        return result, False
    result.update({"status": "finished", "ended_at": _iso_text(now), "paused_remaining_seconds": None})
    should_notify = not bool(result.get("skipped")) and not bool(result.get("notified"))
    if should_notify:
        result["notified"] = True
        result["notified_at"] = _iso_text(now)
    return result, should_notify


def undo_completed_set(session: Mapping[str, Any], set_id: str) -> dict[str, Any]:
    """Return a copy with one completed set unlocked for correction."""
    return undo_completed_set_result(session, set_id)["session"]


def undo_completed_set_result(session: Mapping[str, Any], set_id: str) -> dict[str, Any]:
    """Return an explicit undo result while preserving the legacy session API."""
    result = copy.deepcopy(dict(session))
    for exercise_index, exercise in enumerate(result.get("exercises", []) if isinstance(result.get("exercises"), list) else []):
        if not isinstance(exercise, dict):
            continue
        for set_index, training_set in enumerate(exercise.get("sets", []) if isinstance(exercise.get("sets"), list) else []):
            if isinstance(training_set, dict) and str(training_set.get("id") or "") == str(set_id):
                was_completed = bool(training_set.get("completed"))
                training_set["completed"] = False
                training_set["completed_at"] = ""
                return {
                    "session": result,
                    "set_id": str(set_id),
                    "exercise_index": exercise_index,
                    "set_index": set_index,
                    "was_completed": was_completed,
                    "completed": False,
                    "status": "undone" if was_completed else "unchanged",
                }
    raise KeyError(f"training set not found: {set_id}")

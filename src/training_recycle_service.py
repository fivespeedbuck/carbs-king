"""Persistent 15-day recycle bin for completed training sessions."""

from __future__ import annotations

import copy
import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any

from storage_service import TRAINING_RECYCLE_BIN_FILE, load_json, save_json


RETENTION_DAYS = 15


def _parse(value: Any) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value or "").strip())
    except (TypeError, ValueError):
        return None


def recycle_expiry_label(deleted_at: Any, *, now: dt.datetime | None = None) -> str:
    """Return the remaining retention time for one recycle-bin entry."""
    deleted = _parse(deleted_at)
    if deleted is None:
        return "自动清除时间未知"
    current = now or dt.datetime.now().astimezone()
    if deleted.tzinfo is None and current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    elif deleted.tzinfo is not None and current.tzinfo is None:
        current = current.replace(tzinfo=deleted.tzinfo)
    seconds = (deleted + dt.timedelta(days=RETENTION_DAYS) - current).total_seconds()
    if seconds < 86400:
        return "不足 1 天后自动清除"
    return f"{int(seconds // 86400)} 天后自动清除"


def load_recycled_training_sessions(
    *, now: dt.datetime | None = None
) -> list[dict[str, Any]]:
    raw = load_json(TRAINING_RECYCLE_BIN_FILE, [])
    items = [copy.deepcopy(dict(item)) for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []
    current = now or dt.datetime.now().astimezone()
    cutoff = current - dt.timedelta(days=RETENTION_DAYS)
    retained = []
    for item in items:
        deleted_at = _parse(item.get("deleted_at"))
        if deleted_at is None:
            continue
        comparable_now = current
        comparable_cutoff = cutoff
        if deleted_at.tzinfo is None and current.tzinfo is not None:
            comparable_now = current.replace(tzinfo=None)
            comparable_cutoff = comparable_now - dt.timedelta(days=RETENTION_DAYS)
        elif deleted_at.tzinfo is not None and current.tzinfo is None:
            comparable_cutoff = current.replace(tzinfo=deleted_at.tzinfo) - dt.timedelta(days=RETENTION_DAYS)
        if deleted_at > comparable_cutoff:
            retained.append(item)
    if retained != items:
        save_json(TRAINING_RECYCLE_BIN_FILE, retained)
    return retained


def recycle_training_session(
    session: Mapping[str, Any], *, original_date: str, deleted_at: str
) -> dict[str, Any]:
    entry = {
        "id": f"trash_{uuid.uuid4().hex}",
        "original_date": str(original_date).strip(),
        "deleted_at": str(deleted_at).strip(),
        "session": copy.deepcopy(dict(session)),
    }
    items = load_recycled_training_sessions()
    items.insert(0, entry)
    save_json(TRAINING_RECYCLE_BIN_FILE, items)
    return copy.deepcopy(entry)


def remove_recycled_training_session(entry_id: str) -> dict[str, Any] | None:
    key = str(entry_id or "").strip()
    items = load_recycled_training_sessions()
    selected = next((item for item in items if str(item.get("id") or "") == key), None)
    if selected is None:
        return None
    save_json(
        TRAINING_RECYCLE_BIN_FILE,
        [item for item in items if str(item.get("id") or "") != key],
    )
    return copy.deepcopy(selected)


__all__ = [
    "RETENTION_DAYS",
    "recycle_expiry_label",
    "load_recycled_training_sessions",
    "recycle_training_session",
    "remove_recycled_training_session",
]

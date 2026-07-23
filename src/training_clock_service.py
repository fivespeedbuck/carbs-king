"""Wall-clock based workout timing that survives navigation and process restarts."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any


MAX_ACTIVE_SECONDS = 18 * 60 * 60


def _parse(value: Any) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _compatible_now(now: dt.datetime, reference: dt.datetime) -> dt.datetime:
    if reference.tzinfo is None:
        return now.replace(tzinfo=None) if now.tzinfo is not None else now
    if now.tzinfo is None:
        return now.replace(tzinfo=reference.tzinfo)
    return now.astimezone(reference.tzinfo)


def active_session_with_start(session: Mapping[str, Any], now: dt.datetime) -> tuple[dict[str, Any], bool]:
    """Migrate an active legacy session missing ``started_at`` without inventing a long workout."""
    result = dict(session)
    if result.get("status") != "active" or _parse(result.get("started_at")) is not None:
        return result, False
    try:
        fallback_minutes = max(0.0, min(float(result.get("total_duration_min") or 0), MAX_ACTIVE_SECONDS / 60))
    except (TypeError, ValueError):
        fallback_minutes = 0.0
    started = now - dt.timedelta(minutes=fallback_minutes)
    result["started_at"] = started.isoformat(timespec="seconds")
    result["clock_migrated"] = True
    return result, True


def session_elapsed_seconds(session: Mapping[str, Any] | None, now: dt.datetime) -> int:
    """Return a bounded duration from persisted timestamps; missing/invalid data never becomes negative."""
    if not isinstance(session, Mapping):
        return 0
    status = str(session.get("status") or "planned")
    started = _parse(session.get("started_at"))
    if started is None:
        try:
            return max(0, min(int(round(float(session.get("total_duration_min") or 0) * 60)), MAX_ACTIVE_SECONDS))
        except (TypeError, ValueError):
            return 0
    current = _compatible_now(now, started)
    if status in {"completed", "incomplete"}:
        ended = _parse(session.get("ended_at"))
        if ended is None:
            try:
                return max(0, int(round(float(session.get("total_duration_min") or 0) * 60)))
            except (TypeError, ValueError):
                return 0
        current = _compatible_now(ended, started)
    raw = int((current - started).total_seconds())
    try:
        paused = max(0, int(float(session.get("paused_duration_seconds") or 0)))
    except (TypeError, ValueError):
        paused = 0
    return max(0, min(raw - paused, MAX_ACTIVE_SECONDS))


def finalize_session_clock(session: Mapping[str, Any], now: dt.datetime, *, incomplete: bool = False) -> dict[str, Any]:
    result, _ = active_session_with_start(session, now)
    elapsed = session_elapsed_seconds(result, now)
    result.update({
        "status": "completed",
        "incomplete": bool(incomplete),
        "ended_at": now.isoformat(timespec="seconds"),
        "total_duration_min": round(elapsed / 60, 1),
    })
    return result


__all__ = ["MAX_ACTIVE_SECONDS", "active_session_with_start", "finalize_session_clock", "session_elapsed_seconds"]

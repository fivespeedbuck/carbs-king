"""Period summary and raw daily rows for analytics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import flet as ft

from analytics_model import DataPageConfig, ORANGE, SUB, SURFACE, TEXT, _mapping
from analytics_ui import _card, _metric, _text

def _render_summary(model: Mapping[str, Any]) -> ft.Container:
    summary = _mapping(model.get("summary"))

    def change_text(value: Any, unit: str) -> str:
        if not isinstance(value, (int, float)):
            return "无"
        sign = "+" if value > 0 else "±" if value == 0 else ""
        return f"{sign}{value:g} {unit}"

    return _card(
        ft.Column(
            [
                ft.Row([_metric("训练天数", summary["training_days"]), _metric("休息天数", summary["rest_days"], color=ORANGE)], spacing=8),
                ft.Row([_metric("体重变化", change_text(summary.get("weight_change"), "kg")), _metric("体脂变化", change_text(summary.get("bodyfat_change"), "%"))], spacing=8),
                ft.Row([_metric("平均睡眠", f"{summary['avg_sleep_hours']:g}h" if summary["avg_sleep_hours"] is not None else "无"), _metric("平均热量", f"{summary['avg_kcal']:g} kcal" if summary["avg_kcal"] is not None else "无")], spacing=8),
                ft.Row([_metric("平均饮水", f"{summary['avg_water_ml']:g} ml" if summary["avg_water_ml"] is not None else "无"), _metric("未记录天数", summary["unrecorded_days"], color=SUB)], spacing=8),
            ],
            spacing=8,
        )
    )


def _raw_day_line(item: Mapping[str, Any]) -> ft.Container:
    training = _mapping(item.get("training"))
    diet = _mapping(item.get("diet"))
    body = _mapping(item.get("body"))
    recovery = _mapping(item.get("recovery"))
    training_label = training.get("body_part_label") or ("休息" if not training else "")
    kcal = diet.get("kcal")
    weight = body.get("weight_kg")
    sleep = recovery.get("sleep_minutes")
    return ft.Container(
        content=ft.Row(
            [
                _text(item.get("date", ""), size=12, color=SUB),
                _text(f"{weight:g}kg" if isinstance(weight, (int, float)) else "身体未测", size=12, color=TEXT, weight="bold"),
                _text(f"{kcal:g}kcal" if isinstance(kcal, (int, float)) else "饮食未记", size=12, color=TEXT),
                _text(str(training_label or "训练未记"), size=12, color=TEXT),
                _text(f"{round(sleep / 60, 1):g}h" if isinstance(sleep, (int, float)) else "恢复未记", size=12, color=SUB),
            ],
            spacing=8,
        ),
        bgcolor=SURFACE,
        border_radius=6,
        padding=8,
    )


def _render_raw_list(model: Mapping[str, Any], on_toggle: Callable[[Any], None] | None) -> ft.Container:
    cfg: DataPageConfig = model["config"]
    rows = [_raw_day_line(item) for item in model.get("raw_days", [])] if cfg.raw_expanded else []
    return _card(
        ft.Column(
            [
                ft.Row([
                    _text("原始逐日列表", size=15, weight="bold"),
                    ft.IconButton(
                        icon=ft.Icons.EXPAND_LESS if cfg.raw_expanded else ft.Icons.EXPAND_MORE,
                        tooltip="收起" if cfg.raw_expanded else "展开",
                        icon_color=SUB,
                        on_click=on_toggle,
                    ),
                ], alignment="spaceBetween"),
                *rows,
            ],
            spacing=6,
        )
    )

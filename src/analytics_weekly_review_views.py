"""Weekly review view for analytics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import flet as ft

from analytics_model import SUB, SURFACE, _mapping
from analytics_ui import _card, _text


def _render_weekly_review(model: Mapping[str, Any]) -> ft.Control:
    review = _mapping(model.get("weekly_review"))
    items = [
        ("体重变化", _mapping(review.get("weight"))),
        ("训练负荷", _mapping(review.get("training"))),
        ("饮食目标", _mapping(review.get("diet"))),
        ("睡眠", _mapping(review.get("sleep"))),
    ]

    def tile(title: str, item: Mapping[str, Any]) -> ft.Control:
        return ft.Container(
            content=ft.Column([
                _text(title, size=12, color=SUB, weight="bold"),
                _text(str(item.get("label") or "暂无足够数据"), size=16, weight="bold"),
                ft.Text(str(item.get("detail") or ""), size=12, color=SUB, max_lines=1, overflow="ellipsis"),
            ], spacing=1),
            bgcolor=SURFACE,
            border_radius=6,
            padding=8,
            height=70,
            expand=True,
        )

    return _card(ft.Column([
        _text("本周总结", size=16, weight="bold"),
        ft.Row([tile(*items[0]), tile(*items[1])], spacing=6),
        ft.Row([tile(*items[2]), tile(*items[3])], spacing=6),
    ], spacing=6))

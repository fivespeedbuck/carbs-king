"""Trend and exercise-progress views for analytics."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

import flet as ft
import flet.canvas as cv

from analytics_model import (
    BODY_PART_FILTERS, BORDER, CHART_OPTIONS, PRIMARY,
    PURPLE, SUB, SURFACE, _mapping, _number,
)
from analytics_ui import _card, _chip, _metric, _text, _value_or_empty

def _chart_title(chart_kind: str) -> str:
    return dict(CHART_OPTIONS).get(chart_kind, "体重")


def _empty_entry(label: str, on_click: Callable[[Any], None] | None) -> ft.Container:
    return ft.Container(
        content=ft.Row([
            _text("暂无真实记录", size=14, color=SUB, weight="bold"),
            _chip(label, False, on_click),
        ], spacing=8),
        bgcolor=SURFACE,
        border_radius=8,
        padding=10,
    )


def _render_training_details(
    model: Mapping[str, Any],
    on_action_trend_open: Callable[[Any], None] | None,
    on_body_part_filter_change: Callable[[str], None] | None,
) -> list[ft.Control]:
    trend = _mapping(model.get("trend"))
    weekly = [item for item in trend.get("weekly_training", []) if isinstance(item, Mapping)]
    best_lifts = [item for item in trend.get("best_lifts", []) if isinstance(item, Mapping)]
    week_rows = [
        ft.Row([
            _text(item["label"], size=12, color=SUB),
            _text(f"{item['sets']} 组", size=13, weight="bold"),
            _text(f"{item['volume_kg']:g} kg", size=13, color=PRIMARY, weight="bold"),
        ], alignment="spaceBetween")
        for item in weekly
        if item.get("sets") or item.get("volume_kg")
    ]
    filter_row = ft.Row(
        [
            _chip(part, trend["body_part_filter"] == part, None if on_body_part_filter_change is None else lambda e, value=part: on_body_part_filter_change(value))
            for part in BODY_PART_FILTERS
        ],
        spacing=5,
        scroll=getattr(getattr(ft, "ScrollMode", object()), "HIDDEN", "hidden"),
    )
    lift_rows = [
        ft.Container(
            content=ft.Row([
                ft.Column([
                    _text(f"{item['body_part']} · {item['exercise'] or '未命名动作'}", size=13, weight="bold"),
                    _text(item["date"], size=12, color=SUB),
                ], spacing=1, expand=True),
                _text(f"{item['weight_kg']:g} x {item['reps']:g}", size=13, weight="bold"),
                _text(f"1RM {item['epley_1rm_kg']:g}", size=13, color=PRIMARY, weight="bold"),
            ], spacing=8),
            bgcolor=SURFACE,
            border_radius=6,
            padding=8,
        )
        for item in best_lifts
    ]
    return [
        ft.Row([_metric("周总组数", sum(item.get("sets", 0) for item in weekly)), _metric("周总容量", f"{sum(item.get('volume_kg', 0) for item in weekly):g} kg")], spacing=8),
        ft.Container(content=ft.Column(week_rows or [_text("暂无真实完成组", size=13, color=SUB)], spacing=4), bgcolor=SURFACE, border_radius=8, padding=10),
        ft.Row([
            _text("PR（个人最佳成绩）", size=16, weight="bold"),
            _chip("进入", False, on_action_trend_open),
        ], spacing=8),
        _text("按部位筛选个人最佳成绩", size=15, weight="bold"),
        filter_row,
        ft.Column(lift_rows or [_empty_entry("+记录训练", None)], spacing=6),
    ]


def _render_action_trend(
    model: Mapping[str, Any],
    on_action_trend_close: Callable[[Any], None] | None,
    on_selected_exercise_change: Callable[[str], None] | None,
    on_add_record: Callable[[str], None] | None,
) -> list[ft.Control]:
    trend = _mapping(_mapping(model.get("trend")).get("exercise_trend"))
    options = [item for item in trend.get("options", []) if isinstance(item, Mapping)]
    selected = str(trend.get("selected_exercise") or "")
    add_click = None if on_add_record is None else lambda e: on_add_record("training")
    if not options:
        return [
            ft.Row([
                _text("PR（个人最佳成绩）", size=16, weight="bold"),
                _chip("返回训练汇总", False, on_action_trend_close),
            ], spacing=8),
            _empty_entry(str(trend.get("empty_action_label") or "+记录训练"), add_click),
        ]

    points = [item for item in trend.get("points", []) if isinstance(item, Mapping)]
    values = [_number(item.get("epley_1rm_kg")) for item in points]
    recorded = [item for item in values if item is not None]
    min_value = min(recorded) if recorded else 0
    max_value = max(recorded) if recorded else 1
    span = max(max_value - min_value, 1)
    bars = []
    for point, value in zip(points, values):
        height = 18 if value is None else 28 + int((value - min_value) / span * 78)
        bars.append(
            ft.Container(
                content=ft.Container(width=10, height=height, bgcolor=BORDER if value is None else PURPLE, border_radius=5),
                height=118,
                alignment=ft.Alignment.BOTTOM_CENTER,
                tooltip=f"{point['date']} · {point['label']}",
                expand=True,
            )
        )
    option_row = ft.Row(
        [
            _chip(
                str(item["exercise"]),
                selected == item["exercise"],
                None if on_selected_exercise_change is None else lambda e, value=str(item["exercise"]): on_selected_exercise_change(value),
            )
            for item in options
        ],
        spacing=5,
        scroll=getattr(getattr(ft, "ScrollMode", object()), "HIDDEN", "hidden"),
    )
    return [
        ft.Row([
            _text("PR（个人最佳成绩）", size=16, weight="bold"),
            _chip("返回训练汇总", False, on_action_trend_close),
        ], spacing=8),
        option_row,
        ft.Row([
            _metric("最佳重量", _value_or_empty(trend.get("best_weight_kg"), "kg")),
            _metric("最高次数", _value_or_empty(trend.get("best_reps"))),
            _metric("最佳 1RM", _value_or_empty(trend.get("best_epley_1rm_kg"), "kg")),
        ], spacing=8),
        _empty_entry(str(trend.get("empty_action_label") or "+记录训练"), add_click) if not recorded else ft.Container(height=0),
    ]


def _format_tick(value: float) -> str:
    if abs(value) < 1e-9:
        value = 0.0
    if abs(value) >= 1000:
        return f"{value / 1000:g}k"
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.1f}"


def _clamped_label_left(center: float, label_width: float, chart_width: float) -> float:
    return max(0.0, min(chart_width - label_width, center - label_width / 2))


_CHART_HEIGHT = 226.0
_PLOT_TOP = 24.0
_PLOT_BOTTOM = 38.0
_Y_AXIS_WIDTH = 34.0
_SEVEN_DAY_PLOT_WIDTH = 278.0
_LONG_PERIOD_DAY_WIDTH = 44.0
_EDGE_PADDING = 24.0


class _InitiallyLatestRow(ft.Row):
    """Scrollable row that jumps to the latest edge once after mounting."""

    def did_mount(self):
        super().did_mount()
        self.page.run_task(self._show_latest_once)

    async def _show_latest_once(self):
        # Let the browser finish measuring the wide canvas before positioning it.
        await asyncio.sleep(0.05)
        await self.scroll_to(offset=-1, duration=0)


def _chart_date_label(value: Any) -> str:
    day = date.fromisoformat(str(value))
    return f"{day.month}/{day.day}"


_POINT_LABEL_WIDTH = 64.0
_POINT_LABEL_HEIGHT = 20.0
_POINT_LABEL_GAP = 3.0


def _smooth_path_elements(
    positions: list[tuple[float, float]],
) -> list[cv.Path.PathElement]:
    """Build a restrained cubic curve that passes through every real point."""
    if not positions:
        return []
    elements: list[cv.Path.PathElement] = [cv.Path.MoveTo(*positions[0])]
    for (start_x, start_y), (end_x, end_y) in zip(positions, positions[1:]):
        control_offset = (end_x - start_x) / 3
        elements.append(cv.Path.CubicTo(
            start_x + control_offset,
            start_y,
            end_x - control_offset,
            end_y,
            end_x,
            end_y,
        ))
    return elements


def _extreme_point_indices(
    recorded: list[tuple[int, Mapping[str, Any], float]],
) -> set[int]:
    """Return at most one maximum and one minimum point for persistent labels."""
    if not recorded:
        return set()
    maximum = max(recorded, key=lambda item: item[2])
    minimum = min(recorded, key=lambda item: item[2])
    return {maximum[0], minimum[0]}


def _trend_statistics(
    recorded: list[tuple[int, Mapping[str, Any], float]],
    unit: str,
) -> ft.Control:
    values = [item[2] for item in recorded]
    change = values[-1] - values[0] if len(values) > 1 else None

    def value_text(value: float) -> str:
        return f"{_format_tick(value)} {unit}".rstrip()

    if change is None:
        change_text = "--"
    else:
        sign = "+" if change > 0 else "±" if abs(change) < 1e-9 else ""
        change_text = f"{sign}{_format_tick(change)} {unit}".rstrip()

    items = (
        ("记录次数", f"{len(recorded)} 次"),
        ("区间变化", change_text),
        ("最高", value_text(max(values))),
        ("最低", value_text(min(values))),
    )
    cells = [
        ft.Container(
            content=ft.Column([
                _text(label, size=12, color=SUB),
                _text(value, size=17, weight="bold"),
            ], spacing=2),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            expand=True,
            data=f"trend-stat-{index}",
        )
        for index, (label, value) in enumerate(items)
    ]
    return ft.Container(
        content=ft.Column([
            ft.Row(cells[:2], spacing=0),
            ft.Divider(height=1, color=BORDER),
            ft.Row(cells[2:], spacing=0),
        ], spacing=0),
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        data="trend-statistics",
    )


def _labels_overlap(first: tuple[float, float], second: tuple[float, float]) -> bool:
    first_left, first_top = first
    second_left, second_top = second
    return (
        first_left < second_left + _POINT_LABEL_WIDTH + _POINT_LABEL_GAP
        and second_left < first_left + _POINT_LABEL_WIDTH + _POINT_LABEL_GAP
        and first_top < second_top + _POINT_LABEL_HEIGHT + _POINT_LABEL_GAP
        and second_top < first_top + _POINT_LABEL_HEIGHT + _POINT_LABEL_GAP
    )


def _segment_intersects_rect(
    start: tuple[float, float],
    end: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    """Return whether a line segment crosses a label rectangle."""
    x1, y1 = start
    x2, y2 = end
    left, top, right, bottom = rect
    dx = x2 - x1
    dy = y2 - y1
    lower, upper = 0.0, 1.0
    for direction, distance in (
        (-dx, x1 - left),
        (dx, right - x1),
        (-dy, y1 - top),
        (dy, bottom - y1),
    ):
        if abs(direction) < 1e-9:
            if distance < 0:
                return False
            continue
        ratio = distance / direction
        if direction < 0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return False
    return True


def _label_crosses_line(
    position: tuple[float, float],
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> bool:
    left, top = position
    clearance = 2.0
    rect = (
        left - clearance,
        top - clearance,
        left + _POINT_LABEL_WIDTH + clearance,
        top + _POINT_LABEL_HEIGHT + clearance,
    )
    return any(_segment_intersects_rect(start, end, rect) for start, end in segments)


def _point_label_positions(
    point_positions: list[tuple[float, float]],
    chart_width: float,
    plot_top: float,
    plot_bottom: float,
) -> list[tuple[float, float]]:
    """Place labels without overlapping adjacent labels or the trend line."""
    maximum_top = max(plot_top, plot_bottom - _POINT_LABEL_HEIGHT)
    segments = list(zip(point_positions, point_positions[1:]))
    placed: list[tuple[float, float]] = []
    for index, (center_x, center_y) in enumerate(point_positions):
        above = center_y - _POINT_LABEL_HEIGHT - 3.0
        below = center_y + 3.0
        neighbour_y = [
            point_positions[neighbour][1]
            for neighbour in (index - 1, index + 1)
            if 0 <= neighbour < len(point_positions)
        ]
        if neighbour_y and center_y <= min(neighbour_y):
            preferred_tops = [above, below]
        elif neighbour_y and center_y >= max(neighbour_y):
            preferred_tops = [below, above]
        else:
            preferred_tops = [above, below] if index % 2 == 0 else [below, above]

        # Keep labels visually attached to their point. Horizontal nudges solve
        # dense seven-day collisions before any small vertical adjustment.
        candidates: list[tuple[float, float]] = []
        for top in preferred_tops:
            for horizontal_shift in (0.0, -12.0, 12.0, -24.0, 24.0, -40.0, 40.0, -56.0, 56.0):
                left = _clamped_label_left(
                    center_x + horizontal_shift,
                    _POINT_LABEL_WIDTH,
                    chart_width,
                )
                candidates.append((left, top))
        for vertical_shift in (-6.0, 6.0):
            for top in preferred_tops:
                left = _clamped_label_left(center_x, _POINT_LABEL_WIDTH, chart_width)
                candidates.append((left, top + vertical_shift))

        chosen: tuple[float, float] | None = None
        seen_positions: set[tuple[float, float]] = set()
        for candidate_left, candidate_top in candidates:
            left = max(0.0, min(chart_width - _POINT_LABEL_WIDTH, candidate_left))
            top = max(plot_top, min(maximum_top, candidate_top))
            rounded_position = (round(left, 3), round(top, 3))
            if rounded_position in seen_positions:
                continue
            seen_positions.add(rounded_position)
            position = (left, top)
            if (
                not any(_labels_overlap(position, previous) for previous in placed)
                and not _label_crosses_line(position, segments)
            ):
                chosen = position
                break
        fallback_left = _clamped_label_left(center_x, _POINT_LABEL_WIDTH, chart_width)
        placed.append(chosen or (fallback_left, max(plot_top, min(maximum_top, preferred_tops[0]))))
    return placed


def _render_readable_chart(
    trend: Mapping[str, Any],
    on_trend_point_select: Callable[[str], None] | None,
) -> ft.Control:
    points = [item for item in trend.get("points", []) if isinstance(item, Mapping)]
    values = [_number(point.get("value")) for point in points]
    recorded = [(index, point, value) for index, (point, value) in enumerate(zip(points, values)) if value is not None]
    period_days = int(trend.get("period_days") or len(points) or 7)
    selected_date = str(trend.get("selected_trend_date") or "")

    # A lone measurement is a state, not a time series. Keeping it centered makes
    # it readable in 7/30/90-day windows without suggesting invented data.
    if len(recorded) == 1:
        _, point, value = recorded[0]
        axis = _mapping(trend.get("axis"))
        axis_min = float(axis.get("min", value - 1.0))
        axis_max = float(axis.get("max", value + 1.0))
        axis_span = max(axis_max - axis_min, 1e-9)
        ticks = [float(item) for item in axis.get("ticks", [])]
        center_x = _SEVEN_DAY_PLOT_WIDTH / 2
        plot_height = _CHART_HEIGHT - _PLOT_TOP - _PLOT_BOTTOM
        center_y = _PLOT_TOP + (axis_max - value) / axis_span * plot_height
        point_color = PURPLE if str(point.get("date")) == selected_date else PRIMARY
        shapes: list[cv.Shape] = []
        axis_controls: list[ft.Control] = []
        for tick in ticks:
            y = _PLOT_TOP + (axis_max - tick) / axis_span * plot_height
            shapes.append(cv.Line(0, y, _SEVEN_DAY_PLOT_WIDTH, y, paint=ft.Paint(color="#DDE6E2", stroke_width=1)))
            axis_controls.append(ft.Text(
                _format_tick(tick),
                size=12,
                color=SUB,
                left=0,
                top=y - 8,
                width=_Y_AXIS_WIDTH,
                text_align="right",
                max_lines=1,
                no_wrap=True,
            ))
        shapes.append(cv.Circle(center_x, center_y, 6.5, paint=ft.Paint(color=point_color, style=ft.PaintingStyle.FILL)))
        point_label = str(point.get("label") or _format_tick(value))
        controls: list[ft.Control] = [
            cv.Canvas(shapes=shapes, width=_SEVEN_DAY_PLOT_WIDTH, height=_CHART_HEIGHT),
            ft.Container(
                content=ft.Text(point_label, size=13, color=point_color, weight="bold", text_align="center", no_wrap=True),
                data="single-trend-point-label",
                left=center_x - 46,
                top=center_y - 38,
                width=92,
                padding=2,
                border_radius=4,
            ),
            ft.Container(
                width=40,
                height=40,
                left=center_x - 20,
                top=center_y - 20,
                tooltip=f"{point['date']} · {point_label}",
                on_click=None if on_trend_point_select is None else lambda e, value=str(point["date"]): on_trend_point_select(value),
                ink=True,
                border_radius=20,
            ),
            ft.Text(
                _chart_date_label(point.get("date")),
                size=12,
                color=PRIMARY,
                weight="bold",
                left=center_x - 28,
                top=_CHART_HEIGHT - 30,
                width=56,
                text_align="center",
                max_lines=1,
                no_wrap=True,
            ),
        ]
        plot = ft.Stack(
            controls,
            width=_SEVEN_DAY_PLOT_WIDTH,
            height=_CHART_HEIGHT,
            data={"mode": "single", "date_x": {str(point["date"]): center_x}},
        )
        axis_stack = ft.Stack(axis_controls, width=_Y_AXIS_WIDTH, height=_CHART_HEIGHT, data="trend-y-axis")
        return ft.Container(
            content=ft.Row([axis_stack, plot], spacing=3, vertical_alignment="start", height=_CHART_HEIGHT),
            height=_CHART_HEIGHT,
            data={
                "period_days": period_days,
                "recorded_count": 1,
                "scrollable": False,
                "y_axis_width": _Y_AXIS_WIDTH,
            },
        )

    axis = _mapping(trend.get("axis"))
    axis_min = float(axis.get("min", 0.0))
    axis_max = float(axis.get("max", 1.0))
    axis_span = max(axis_max - axis_min, 1e-9)
    ticks = [float(item) for item in axis.get("ticks", [])]
    is_long_period = period_days > 7
    plot_width = (
        _EDGE_PADDING * 2 + _LONG_PERIOD_DAY_WIDTH * max(0, len(points) - 1)
        if is_long_period
        else _SEVEN_DAY_PLOT_WIDTH
    )
    plot_height = _CHART_HEIGHT - _PLOT_TOP - _PLOT_BOTTOM

    def x_at(index: int) -> float:
        if len(points) <= 1:
            return plot_width / 2
        if is_long_period:
            return _EDGE_PADDING + _LONG_PERIOD_DAY_WIDTH * index
        return _EDGE_PADDING + (plot_width - _EDGE_PADDING * 2) / (len(points) - 1) * index

    def y_at(value: float) -> float:
        return _PLOT_TOP + (axis_max - value) / axis_span * plot_height

    grid_paint = ft.Paint(color="#DDE6E2", stroke_width=1)
    line_paint = ft.Paint(
        color=PRIMARY,
        stroke_width=2.5,
        style=ft.PaintingStyle.STROKE,
    )
    point_paint = ft.Paint(color=PRIMARY, style=ft.PaintingStyle.FILL)
    shapes: list[cv.Shape] = []
    plot_controls: list[ft.Control] = []
    axis_controls: list[ft.Control] = []
    for tick in ticks:
        y = y_at(tick)
        shapes.append(cv.Line(0, y, plot_width, y, paint=grid_paint))
        axis_controls.append(ft.Text(
            _format_tick(tick),
            size=12,
            color=SUB,
            left=0,
            top=y - 8,
            width=_Y_AXIS_WIDTH,
            text_align="right",
            max_lines=1,
            no_wrap=True,
        ))

    point_positions = [(x_at(index), y_at(value)) for index, _, value in recorded]
    baseline = _PLOT_TOP + plot_height
    if len(point_positions) > 1:
        area_elements = _smooth_path_elements(point_positions)
        area_elements.extend([
            cv.Path.LineTo(point_positions[-1][0], baseline),
            cv.Path.LineTo(point_positions[0][0], baseline),
            cv.Path.Close(),
        ])
        shapes.append(cv.Path(
            area_elements,
            paint=ft.Paint(color="#20117A65", style=ft.PaintingStyle.FILL),
            data="trend-area",
        ))
        shapes.append(cv.Path(
            _smooth_path_elements(point_positions),
            paint=line_paint,
            data="trend-smooth-line",
        ))

    selected_record = next(
        (item for item in recorded if str(item[1].get("date")) == selected_date),
        None,
    )
    if selected_record is not None:
        selected_index, selected_point, selected_value = selected_record
        selected_x = x_at(selected_index)
        selected_y = y_at(selected_value)
        shapes.append(cv.Line(
            selected_x,
            _PLOT_TOP,
            selected_x,
            baseline,
            paint=ft.Paint(color="#69117A65", stroke_width=1.2),
            data="trend-selection-line",
        ))
        bubble_width = 112.0
        bubble_left = _clamped_label_left(selected_x, bubble_width, plot_width)
        bubble_top = max(0.0, selected_y - 60.0)
        plot_controls.append(ft.Container(
            content=ft.Column([
                _text(str(selected_point.get("date")), size=12, color=SUB),
                _text(str(selected_point.get("label") or _format_tick(selected_value)), size=15, weight="bold"),
            ], spacing=1),
            left=bubble_left,
            top=bubble_top,
            width=bubble_width,
            padding=ft.Padding.symmetric(horizontal=10, vertical=7),
            bgcolor="#F7FAF9",
            border=ft.Border.all(1, BORDER),
            border_radius=7,
            shadow=ft.BoxShadow(blur_radius=8, color="#22000000"),
            data="trend-selection-bubble",
        ))

    extreme_indices = _extreme_point_indices(recorded)
    maximum_index = max(recorded, key=lambda item: item[2])[0]
    minimum_index = min(recorded, key=lambda item: item[2])[0]
    for index, point, value in recorded:
        x, y = x_at(index), y_at(value)
        selected = str(point.get("date")) == selected_date
        shapes.append(cv.Circle(
            x,
            y,
            6 if selected else 4.5,
            paint=ft.Paint(color=PURPLE, style=ft.PaintingStyle.FILL) if selected else point_paint,
        ))
        plot_controls.append(ft.Container(
            width=34,
            height=34,
            left=x - 17,
            top=y - 17,
            tooltip=f"{point['date']} · {point['label']}",
            on_click=None if on_trend_point_select is None else lambda e, value=str(point["date"]): on_trend_point_select(value),
            ink=True,
            border_radius=17,
        ))
        if index in extreme_indices and not selected:
            label_top = y - _POINT_LABEL_HEIGHT - 5 if index == maximum_index else y + 5
            plot_controls.append(ft.Container(
                content=ft.Text(
                    str(point.get("label") or _format_tick(value)),
                    size=12,
                    color=PRIMARY,
                    weight="bold",
                    text_align="center",
                    no_wrap=True,
                ),
                data="trend-extreme-label",
                left=_clamped_label_left(x, _POINT_LABEL_WIDTH, plot_width),
                top=label_top,
                width=_POINT_LABEL_WIDTH,
                height=_POINT_LABEL_HEIGHT,
                padding=1,
                border_radius=3,
            ))

    recorded_indices = {item[0] for item in recorded}
    for index, point in enumerate(points):
        label_width = 40.0
        plot_controls.append(ft.Text(
            _chart_date_label(point.get("date")),
            size=12,
            color=PRIMARY if index in recorded_indices else SUB,
            weight="bold" if index in recorded_indices else None,
            left=_clamped_label_left(x_at(index), label_width, plot_width),
            top=_CHART_HEIGHT - 29,
            width=label_width,
            text_align="center",
            max_lines=1,
            no_wrap=True,
        ))

    plot_controls.insert(0, cv.Canvas(shapes=shapes, width=plot_width, height=_CHART_HEIGHT))
    date_positions = {str(point["date"]): x_at(index) for index, point in enumerate(points)}
    plot = ft.Stack(
        plot_controls,
        width=plot_width,
        height=_CHART_HEIGHT,
        data={"mode": "smooth-area", "date_x": date_positions, "plot_width": plot_width},
    )
    scroller_type = _InitiallyLatestRow if is_long_period else ft.Row
    plot_scroller = scroller_type(
        [plot],
        spacing=0,
        scroll=getattr(getattr(ft, "ScrollMode", object()), "HIDDEN", "hidden") if is_long_period else None,
        auto_scroll=False,
        alignment="center" if not is_long_period else "start",
        expand=True,
        height=_CHART_HEIGHT,
        data="trend-horizontal-scroll",
    )
    axis_stack = ft.Stack(axis_controls, width=_Y_AXIS_WIDTH, height=_CHART_HEIGHT, data="trend-y-axis")
    return ft.Container(
        content=ft.Row(
            [axis_stack, plot_scroller],
            spacing=3,
            vertical_alignment="start",
            height=_CHART_HEIGHT,
        ),
        height=_CHART_HEIGHT,
        data={
            "period_days": period_days,
            "recorded_count": len(recorded),
            "scrollable": is_long_period,
            "y_axis_width": _Y_AXIS_WIDTH,
        },
    )


def _render_trend_chart(
    model: Mapping[str, Any],
    on_add_record: Callable[[str], None] | None,
    on_action_trend_open: Callable[[Any], None] | None,
    on_action_trend_close: Callable[[Any], None] | None,
    on_selected_exercise_change: Callable[[str], None] | None,
    on_body_part_filter_change: Callable[[str], None] | None,
    on_metric_change: Callable[[str], None] | None,
    on_trend_point_select: Callable[[str], None] | None,
) -> ft.Container:
    trend = _mapping(model.get("trend"))
    points = [item for item in trend.get("points", []) if isinstance(item, Mapping)]
    values = [_number(point.get("value")) for point in points]
    recorded = [item for item in values if item is not None]
    chart_kind = str(trend["chart_kind"])
    add_click = None if on_add_record is None else lambda e, value=chart_kind: on_add_record(value)
    extra: list[ft.Control] = []
    if chart_kind == "training":
        exercise_trend = _mapping(trend.get("exercise_trend"))
        if exercise_trend.get("open"):
            extra = _render_action_trend(model, on_action_trend_close, on_selected_exercise_change, on_add_record)
        else:
            extra.extend(_render_training_details(model, on_action_trend_open, on_body_part_filter_change))

    metric_options = [item for item in trend.get("metric_options", []) if isinstance(item, Mapping)]
    metric_row = ft.Row(
        [
            _chip(
                str(item.get("label")),
                str(item.get("key")) == str(trend.get("metric_key")),
                None if on_metric_change is None else lambda e, value=str(item.get("key")): on_metric_change(value),
            )
            for item in metric_options
        ],
        spacing=5,
        scroll=getattr(getattr(ft, "ScrollMode", object()), "HIDDEN", "hidden"),
    )
    latest = _mapping(trend.get("latest"))
    change = _number(trend.get("change"))
    earliest_change = _number(trend.get("change_from_earliest"))
    latest_text = str(latest.get("label") or "暂无数据")

    def comparison_text(label: str, value: float | None) -> str:
        if value is None:
            return f"{label} --"
        sign = "+" if value > 0 else "±" if value == 0 else ""
        return f"{label} {sign}{value:g} {trend['unit']}".rstrip()

    change_text = comparison_text("较上次", change)
    earliest_change_text = comparison_text("较最早", earliest_change)
    chart_control = _render_readable_chart(trend, on_trend_point_select) if recorded and not _mapping(trend.get("exercise_trend")).get("open") else ft.Container(height=0)

    return _card(
        ft.Column(
            [
                ft.Row([
                    ft.Column([
                        _text(str(trend["title"]), size=16, weight="bold"),
                        _text(str(trend["description"]), size=12, color=SUB),
                    ], spacing=2, expand=True),
                    ft.Row([
                        _chip(str(trend["empty_action_label"]), False, add_click),
                    ], spacing=6),
                ], alignment="spaceBetween"),
                metric_row,
                ft.Row([
                    ft.Column([_text("最新", size=12, color=SUB), _text(latest_text, size=20, weight="bold")], spacing=1),
                    ft.Column([
                        _text(change_text, size=12, color=SUB, weight="bold"),
                        _text(earliest_change_text, size=12, color=SUB, weight="bold"),
                    ], spacing=2, horizontal_alignment="end"),
                ], alignment="spaceBetween"),
                chart_control,
                _trend_statistics(
                    [(index, point, value) for index, (point, value) in enumerate(zip(points, values)) if value is not None],
                    str(trend.get("unit") or ""),
                ) if recorded else ft.Container(height=0),
                ft.Container(
                    content=_text(str(trend["empty_message"]), size=13, color=SUB),
                    bgcolor=SURFACE,
                    border_radius=8,
                    padding=10,
                ) if not recorded else ft.Container(height=0),
                *extra,
            ],
            spacing=10,
        )
    )

"""Recovery feature controller: measurements, water, sleep, and daily supplements."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from analytics_service import make_body_measurement
from app_state import AppState
from app_utils import to_float
from controller_runtime import ControllerRuntime
from form_views import FormViewContext, build_dialog, build_full_form_sheet
from ui_components import (
    GREEN, PRIMARY, PRIMARY_SOFT, RED, SKY_BLUE, SUB, TEXT, card, make_button,
    mobile_text_field, plain_number_field, quantity_unit_grid, responsive_field_grid,
    section_title, small_text, water_progress_bar,
)


@dataclass(frozen=True)
class RecoveryControllerDependencies:
    state: AppState
    runtime: ControllerRuntime
    persist_daily: Callable[..., None]
    persist_profile: Callable[[], None]
    supplements: list[dict[str, Any]]
    iso_now: Callable[[], str]
    keyboard_number: Any
    scroll_hidden: Any


@dataclass
class RecoveryController:
    render_page: Callable[[], ft.Control]
    sleep_total_minutes: Callable[[], int]
    format_minutes: Callable[[int], str]
    add_water: Callable[[float], None]
    delete_water_amount: Callable[[float], None]


def create_recovery_controller(deps: RecoveryControllerDependencies) -> RecoveryController:
    state = deps.state
    runtime = deps.runtime
    page = runtime.page
    refresh = runtime.refresh
    snack = runtime.snack
    set_view = runtime.navigate
    open_control = runtime.open_control
    close_control = runtime.close_control
    responsive_width = runtime.responsive_width
    responsive_bar_width = runtime.responsive_bar_width
    save_current = deps.persist_daily
    save_profile_from_state = deps.persist_profile
    supplements = deps.supplements
    iso_now = deps.iso_now
    _KEYBOARD_NUMBER = deps.keyboard_number
    _SCROLL_HIDDEN = deps.scroll_hidden

    def dialog_base(title, content, actions=None, on_close=None):
        return build_dialog(title, content, actions=actions, on_close=on_close)

    def full_form_sheet(title, controls, on_save, save_label="保存"):
        return build_full_form_sheet(
            FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
            title,
            controls,
            on_save,
            save_label,
        )

    def parse_time_minutes(value):
        """Parse HH:MM / H:MM / HHMM / H into minutes from 00:00."""
        s = str(value or "").strip()
        if not s:
            return None
        try:
            if ":" in s:
                parts = s.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            else:
                digits = "".join(ch for ch in s if ch.isdigit())
                if not digits:
                    return None
                if len(digits) <= 2:
                    hour = int(digits)
                    minute = 0
                else:
                    hour = int(digits[:-2])
                    minute = int(digits[-2:])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour * 60 + minute
        except Exception:
            return None
        return None

    def duration_between(start, end):
        sm = parse_time_minutes(start)
        em = parse_time_minutes(end)
        if sm is None or em is None:
            return 0
        diff = em - sm
        if diff < 0:
            diff += 24 * 60
        return diff

    def sleep_total_minutes():
        sl = state.get("sleep", {})
        total = duration_between(sl.get("bed_time", ""), sl.get("wake_time", ""))
        for nap in sl.get("naps", []):
            total += duration_between(nap.get("start", ""), nap.get("end", ""))
        return int(total)

    def format_minutes(total):
        total = int(total or 0)
        h = total // 60
        m = total % 60
        if h and m:
            return f"{h}小时{m}分"
        if h:
            return f"{h}小时"
        if m:
            return f"{m}分"
        return "未记录"

    def add_water(amount):
        state["water"].append(float(amount))
        save_current()
        refresh()

    def delete_water(idx):
        if 0 <= idx < len(state["water"]):
            state["water"].pop(idx)
            save_current()
            refresh()

    def delete_last_water():
        if state["water"]:
            state["water"].pop()
            save_current()
            refresh()
        else:
            snack("暂无饮水记录")

    def delete_water_amount(amount):
        try:
            remain = float(amount or 0)
        except Exception:
            remain = 0
        if remain <= 0:
            snack("请输入要删除的饮水量")
            return
        if not state["water"]:
            snack("暂无饮水记录")
            return

        while remain > 0 and state["water"]:
            last = float(state["water"][-1])
            if last <= remain + 1e-9:
                remain -= last
                state["water"].pop()
            else:
                state["water"][-1] = round(last - remain, 1)
                remain = 0

        save_current()
        refresh()

    def add_nap(start, end):
        if duration_between(start, end) <= 0:
            snack("请填写正确的小睡时间")
            return
        state.setdefault("sleep", {"bed_time": "", "wake_time": "", "naps": []})
        state["sleep"].setdefault("naps", []).append({"start": str(start or "").strip(), "end": str(end or "").strip()})
        save_current()
        refresh()

    def delete_nap(idx):
        naps = state.get("sleep", {}).get("naps", [])
        if 0 <= idx < len(naps):
            naps.pop(idx)
            save_current()
            refresh()

    def render_recovery_page():
        weight = mobile_text_field("体重 kg", state.get("weight", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        bodyfat = mobile_text_field("体脂 %", state.get("bodyfat", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)

        def save_body_metric(metric):
            state["weight"] = str(weight.value or "")
            state["bodyfat"] = str(bodyfat.value or "")
            previous = state.get("measurement", {}) if isinstance(state.get("measurement"), dict) else {}
            measured_weight = state["weight"] if metric == "weight" else previous.get("weight_kg") if previous.get("weight_measured") else None
            measured_bodyfat = state["bodyfat"] if metric == "bodyfat" else previous.get("bodyfat_percent") if previous.get("bodyfat_measured") else None
            state["measurement"] = make_body_measurement(
                weight_kg=measured_weight,
                bodyfat_percent=measured_bodyfat,
                measured_at=iso_now(),
            )
            save_profile_from_state()
            save_current()
            refresh()
            snack("体重已记录" if metric == "weight" else "体脂已记录")

        body_card = card(ft.Column([
            ft.Row([section_title("今日身体"), small_text("可分别标记实测")], alignment="spaceBetween"),
            responsive_field_grid([
                ft.Column([weight, make_button("记录体重", on_click=lambda e: save_body_metric("weight"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True)], spacing=6, expand=True),
                ft.Column([bodyfat, make_button("记录体脂", on_click=lambda e: save_body_metric("bodyfat"), bgcolor="#E8F1F6", color=SKY_BLUE, expand=True)], spacing=6, expand=True),
            ], columns=2, viewport_width=responsive_width()),
        ], spacing=10), padding=14)
        return ft.Column([
            ft.Container(content=ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="返回今日", on_click=lambda e: set_view("today")),
                ft.Text("身体与恢复", size=20, weight="bold", color=TEXT),
            ], spacing=4), padding=8),
            body_card,
            render_water(),
            render_supp_today(),
            render_sleep(),
        ], spacing=0)

    def _split_time_parts(value, default_hour="23", default_minute="00"):
        text = str(value or "").strip()
        if ":" in text:
            hh, mm = text.split(":", 1)
            if hh.isdigit() and mm.isdigit():
                return hh.zfill(2), mm.zfill(2)
        return default_hour, default_minute

    def _build_time_value(hour_value, minute_value):
        return f"{str(hour_value or '00').zfill(2)}:{str(minute_value or '00').zfill(2)}"

    def time_display_button(text, on_click):
        return ft.Container(
            content=ft.Text(text or "选择时间", size=20, weight="bold", color=TEXT, text_align="center"),
            bgcolor="#FAFAFA",
            border_radius=8,
            padding=14,
            on_click=on_click,
        )

    def time_line(label, value, on_click):
        return ft.Container(
            content=ft.Row([
                ft.Text(label, size=13, color=TEXT, weight="bold"),
                ft.Container(content=time_display_button(value, on_click), expand=True),
            ], spacing=12, vertical_alignment="center"),
            bgcolor="#FFFFFF",
            border_radius=8,
            padding=6,
        )

    def open_time_wheel(title, current_value, default_hour, default_minute, on_save):
        selected = {"hour": default_hour, "minute": default_minute}
        selected["hour"], selected["minute"] = _split_time_parts(current_value, default_hour, default_minute)

        dlg = None
        hour_col = ft.Column(spacing=4, scroll=_SCROLL_HIDDEN)
        minute_col = ft.Column(spacing=4, scroll=_SCROLL_HIDDEN)

        def option_cell(value, kind):
            active = selected[kind] == value
            return ft.Container(
                content=ft.Text(value, size=20, weight="bold" if active else "normal", color=PRIMARY if active else TEXT, text_align="center"),
                bgcolor=PRIMARY_SOFT if active else "#FFFFFF",
                border_radius=8,
                padding=12,
                on_click=lambda e, v=value, k=kind: choose(k, v),
            )

        def rebuild():
            hour_col.controls.clear()
            minute_col.controls.clear()
            for i in range(24):
                hour_col.controls.append(option_cell(f"{i:02d}", "hour"))
            for i in range(60):
                minute_col.controls.append(option_cell(f"{i:02d}", "minute"))

        def choose(kind, value):
            selected[kind] = value
            rebuild()
            page.update()

        def confirm(e=None):
            on_save(_build_time_value(selected["hour"], selected["minute"]))
            close_control(dlg)

        rebuild()

        content = ft.Column([
            ft.Row([
                ft.Container(content=ft.Column([small_text("时"), ft.Container(content=hour_col, height=380)], spacing=4), expand=True),
                ft.Container(content=ft.Column([small_text("分"), ft.Container(content=minute_col, height=380)], spacing=4), expand=True),
            ], spacing=12),
        ], width=responsive_width(), height=430, spacing=8)

        dlg = dialog_base(
            title,
            content,
            [ft.Container(content=make_button("确定", on_click=confirm, expand=True), width=responsive_width())],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def render_sleep():
        sl = state.setdefault("sleep", {"bed_time": "", "wake_time": "", "naps": []})

        def save_bed(value):
            sl["bed_time"] = value
            save_current()
            refresh()

        def save_wake(value):
            sl["wake_time"] = value
            save_current()
            refresh()

        def open_add_nap_dialog(e=None):
            selected = {"start": "13:00", "end": "14:00"}
            dlg = None

            def set_start(value):
                selected["start"] = value
                start_button.content.value = value
                page.update()

            def set_end(value):
                selected["end"] = value
                end_button.content.value = value
                page.update()

            start_button = time_display_button(
                selected["start"],
                lambda event: open_time_wheel("选择小睡开始", selected["start"], "13", "00", set_start),
            )
            end_button = time_display_button(
                selected["end"],
                lambda event: open_time_wheel("选择小睡结束", selected["end"], "14", "00", set_end),
            )

            def nap_time_line(label, button):
                return ft.Container(
                    content=ft.Row([
                        ft.Text(label, size=13, color=TEXT, weight="bold"),
                        ft.Container(content=button, expand=True),
                    ], spacing=12, vertical_alignment="center"),
                    bgcolor="#FFFFFF",
                    border_radius=8,
                    padding=6,
                )

            def confirm(e=None):
                if duration_between(selected["start"], selected["end"]) <= 0:
                    snack("请填写正确的小睡时间")
                    return
                sl.setdefault("naps", []).append({"start": selected["start"], "end": selected["end"]})
                save_current()
                close_control(dlg)
                refresh()
                snack("已添加小睡")

            dialog_width = responsive_width()
            content = ft.Column([
                small_text("点击时间进行选择"),
                nap_time_line("开始", start_button),
                nap_time_line("结束", end_button),
            ], width=dialog_width, height=175, spacing=10)
            dlg = full_form_sheet(
                "添加小睡",
                [content],
                confirm,
                save_label="保存小睡",
            )
            open_control(dlg)

        nap_rows = []
        for idx, nap in enumerate(sl.get("naps", [])):
            mins = duration_between(nap.get("start", ""), nap.get("end", ""))
            nap_rows.append(ft.Container(content=ft.Row([
                ft.Text(f"{nap.get('start','')} - {nap.get('end','')}", size=13, color=TEXT),
                ft.Row([
                    small_text(format_minutes(mins)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=RED, on_click=lambda e, i=idx: delete_nap(i)),
                ], spacing=4),
            ], alignment="spaceBetween"), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))

        if not nap_rows:
            nap_rows.append(ft.Container(content=small_text("暂无小睡记录"), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))

        total_minutes = sleep_total_minutes()
        total_text = format_minutes(total_minutes)

        return card(ft.Column([
            ft.Row([section_title("睡眠记录"), ft.Text(total_text, size=20, weight="bold", color=SKY_BLUE if total_minutes >= 420 else TEXT)], alignment="spaceBetween"),
            small_text("夜间睡眠"),
            time_line("入睡", sl.get("bed_time", "") or "23:00", lambda e: open_time_wheel("选择入睡时间", sl.get("bed_time", "23:00"), "23", "00", save_bed)),
            time_line("起床", sl.get("wake_time", "") or "07:00", lambda e: open_time_wheel("选择起床时间", sl.get("wake_time", "07:00"), "07", "00", save_wake)),
            make_button("添加小睡", on_click=open_add_nap_dialog, icon=ft.Icons.ADD, expand=True),
            ft.Column(nap_rows, spacing=0),
        ], spacing=10))

    def render_water():
        water_total = int(sum(state["water"]))
        custom_water = plain_number_field(value="250", width=114, keyboard_type=_KEYBOARD_NUMBER, height=48)

        input_box = ft.Row([
            ft.Container(content=custom_water, width=114, ),
            ft.Text("ml", size=16, color=SUB, weight="bold"),
        ], spacing=6, vertical_alignment="center")

        return card(ft.Column([
            ft.Row([section_title("饮水记录"), small_text("目标 2000 ml")], alignment="spaceBetween"),
            ft.Row([
                ft.Text(f"{water_total} ml", size=22, weight="bold", color=SKY_BLUE if water_total >= 2000 else GREEN),
                make_button("+250", on_click=lambda e: add_water(250), bgcolor=PRIMARY_SOFT, color=GREEN),
                make_button("+375", on_click=lambda e: add_water(375), bgcolor=PRIMARY_SOFT, color=GREEN),
                make_button("+500", on_click=lambda e: add_water(500), bgcolor=PRIMARY_SOFT, color=GREEN),
            ], alignment="spaceBetween"),
            water_progress_bar(water_total, 2000, width=responsive_bar_width()),
            ft.Row([
                input_box,
                make_button("记录", on_click=lambda e: add_water(to_float(custom_water.value, 250)), expand=True),
                make_button("删除", on_click=lambda e: delete_water_amount(to_float(custom_water.value, 250)), bgcolor="#FDECEC", color=RED, expand=True),
            ], spacing=8, vertical_alignment="center"),
        ], spacing=10))

    def render_supp_today():
        supp_controls = []
        selected_map = {s.get("name"): s for s in state["supplements"]}

        for supp in supplements:
            name = supp.get("name", "")
            checked = name in selected_map
            amount_value = selected_map.get(name, {}).get("amount", supp.get("default_amount", ""))

            cb = ft.Checkbox(value=checked)
            amount = plain_number_field(value=str(amount_value), width=84, height=44)

            def on_change(e=None, s=supp, amount_field=amount, cb_ref=cb):
                existing = [x for x in state["supplements"] if x.get("name") != s.get("name")]
                if cb_ref.value:
                    existing.append({"name": s.get("name"), "amount": amount_field.value, "unit": s.get("unit", "")})
                state["supplements"] = existing
                save_current()
                refresh()

            cb.on_change = on_change
            amount.on_change = on_change

            bg = "#EDF9F4" if checked else "#FAFAFA"
            supp_controls.append(ft.Container(content=ft.Row([
                ft.Container(width=4, height=42, bgcolor=PRIMARY if checked else "#DDDDDD", border_radius=3),
                ft.Row([cb], width=34),
                ft.Text(name, size=13, weight="bold", color=TEXT, expand=True),
                amount,
                ft.Text(supp.get("unit", ""), size=15, color=SUB, weight="bold"),
            ], alignment="spaceBetween", vertical_alignment="center", spacing=8), bgcolor=bg, border_radius=8, padding=8, margin=3))

        if not supp_controls:
            supp_controls.append(ft.Container(content=small_text("暂无补剂"), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))

        def open_supplement_editor(edit_index=None):
            editing = edit_index is not None
            item = supplements[edit_index] if editing else {"name": "", "default_amount": "", "unit": ""}
            dialog_width = responsive_width()
            name = mobile_text_field("补剂名称", value=str(item.get("name", "")), width=dialog_width)
            amount = mobile_text_field("默认用量", value=str(item.get("default_amount", "")), expand=True)
            unit = mobile_text_field("单位", value=str(item.get("unit", "")), expand=True)
            dlg = None

            def confirm(e=None):
                supplement_name = str(name.value or "").strip()
                if not supplement_name:
                    snack("补剂名称不能为空")
                    return
                data = {
                    "name": supplement_name,
                    "default_amount": str(amount.value or "").strip(),
                    "unit": str(unit.value or "").strip(),
                }
                if editing:
                    old_name = str(supplements[edit_index].get("name") or "")
                    supplements[edit_index] = data
                    for selected in state["supplements"]:
                        if selected.get("name") == old_name:
                            selected["name"] = supplement_name
                            selected["unit"] = data["unit"]
                else:
                    if any(str(existing.get("name") or "") == supplement_name for existing in supplements):
                        snack("补剂已存在")
                        return
                    supplements.append(data)
                save_current()
                close_control(dlg)
                refresh()

            dlg = full_form_sheet(
                "修改补剂" if editing else "新增补剂",
                [
                    section_title("名称与用量"),
                    name,
                    quantity_unit_grid(amount, unit, viewport_width=dialog_width),
                ],
                confirm,
            )
            open_control(dlg)

        def delete_supplement(index):
            if not 0 <= index < len(supplements):
                return
            name = str(supplements[index].get("name") or "")
            supplements.pop(index)
            state["supplements"] = [item for item in state["supplements"] if item.get("name") != name]
            save_current()
            refresh()

        library_rows = []
        for index, supplement in enumerate(supplements):
            library_rows.append(ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(str(supplement.get("name") or ""), size=13, weight="bold", color=TEXT),
                        small_text(f"默认 {supplement.get('default_amount', '')}{supplement.get('unit', '')}"),
                    ], spacing=2, expand=True),
                    ft.IconButton(icon=ft.Icons.EDIT, tooltip="修改补剂", icon_color=PRIMARY, width=48, height=48, on_click=lambda e, i=index: open_supplement_editor(i)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="删除补剂", icon_color=RED, width=48, height=48, on_click=lambda e, i=index: delete_supplement(i)),
                ], spacing=4),
                bgcolor="#FAFAFA", border_radius=8, padding=8,
            ))
        if not library_rows:
            library_rows.append(ft.Container(content=small_text("暂无补剂库项目"), bgcolor="#FAFAFA", border_radius=8, padding=8))

        selected_count = len(state["supplements"])
        return card(ft.Column([
            ft.Row([ft.Text(f"今日补剂 {selected_count}", size=15, weight="bold"), make_button("新增补剂", on_click=lambda e: open_supplement_editor(), icon=ft.Icons.ADD, bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
            ft.Column(supp_controls, spacing=2),
            ft.Row([section_title("补剂库"), small_text(f"{len(supplements)} 项")], alignment="spaceBetween"),
            ft.Column(library_rows, spacing=6),
        ], spacing=8))

    return RecoveryController(
        render_page=render_recovery_page,
        sleep_total_minutes=sleep_total_minutes,
        format_minutes=format_minutes,
        add_water=add_water,
        delete_water_amount=delete_water_amount,
    )


__all__ = ["RecoveryController", "RecoveryControllerDependencies", "create_recovery_controller"]

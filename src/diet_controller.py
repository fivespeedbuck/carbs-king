"""Diet feature controller: meals, food library, and supplement library."""

from __future__ import annotations

import datetime
import uuid
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import flet as ft

from app_defaults import DAY_TYPES
from app_state import AppState
from app_utils import calc_item, to_float
from controller_runtime import ControllerRuntime
from diet_service import PersistedSupplementList, DietViewState, diet_route_for_view, normalize_diet_view
from diet_views import DietShellRenderers, build_diet_shell, diet_shortcut_panel
from form_views import FormViewContext, build_full_form_sheet
from repositories import AppRepositories
from ui_components import (
    BORDER, GREEN, PRIMARY, PRIMARY_SOFT, RED, SUB, TEXT, card, macro_progress_bar,
    make_button, mobile_dropdown, mobile_text_field, quantity_unit_grid, section_title,
    small_text, thin_border, two_field_grid,
)


FOOD_UNIT_PRESETS = ("g", "ml", "个", "份")
CUSTOM_UNIT_OPTION = "自定义"


def resolve_food_unit(selected_unit: Any, custom_unit: Any = "") -> str:
    selected = str(selected_unit or "").strip()
    if selected == CUSTOM_UNIT_OPTION:
        return str(custom_unit or "").strip()
    return selected


def bind_custom_unit_visibility(
    unit_input: Any,
    custom_unit_holder: Any,
    request_update: Callable[[], None],
) -> Callable[[Any], None]:
    """Bind to Flet's real Dropdown selection event and keep the holder in sync."""

    def handle_select(event=None):
        event_control = getattr(event, "control", None)
        selected = getattr(event_control, "value", None)
        if selected is None:
            selected = unit_input.value
        else:
            unit_input.value = selected
        custom_unit_holder.visible = selected == CUSTOM_UNIT_OPTION
        request_update()

    dropdown = getattr(unit_input, "field", unit_input)
    dropdown.on_select = handle_select
    return handle_select


@dataclass(frozen=True)
class DietControllerDependencies:
    state: AppState
    repositories: AppRepositories
    records: dict[str, Any]
    runtime: ControllerRuntime
    persist_daily: Callable[..., None]
    persist_records: Callable[[], None]
    get_targets: Callable[[], Mapping[str, float]]
    daily_total: Callable[[], Mapping[str, float]]
    meals: tuple[str, ...]
    keyboard_number: Any
    scroll_hidden: Any


@dataclass
class DietController:
    foods: list[dict[str, Any]]
    supplements: list[dict[str, Any]]
    render_page: Callable[[], ft.Control]
    open_add_food: Callable[..., None]
    open_food_editor: Callable[..., None]
    delete_food: Callable[[int], None]
    food_shortcuts: Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]]]]


def create_diet_controller(deps: DietControllerDependencies) -> DietController:
    state = deps.state
    repositories = deps.repositories
    records = deps.records
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
    persist_records = deps.persist_records
    get_targets = deps.get_targets
    daily_total = deps.daily_total
    MEALS = deps.meals
    _KEYBOARD_NUMBER = deps.keyboard_number
    _SCROLL_HIDDEN = deps.scroll_hidden
    foods = repositories.foods.load()
    supplements = PersistedSupplementList(repositories.supplements.load(), repositories.supplements.save)

    def full_form_sheet(title, controls, on_save, save_label="保存"):
        return build_full_form_sheet(
            FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
            title,
            controls,
            on_save,
            save_label,
        )

    def meal_for_current_time():
        hour = datetime.datetime.now().hour
        if hour < 10:
            return "早餐"
        if hour < 15:
            return "午餐"
        return "晚餐"

    def food_shortcuts(meal_name, limit=4):
        """Return meal-aware frequent foods and true recent foods with last quantity."""
        today = date.today()
        cutoff = today - datetime.timedelta(days=29)
        meal_counts = Counter()
        global_counts = Counter()
        latest_items = {}
        latest_meal_items = {}
        recent_candidates = []
        known_names = {str(food.get("name", "")) for food in foods}

        for record_date in sorted(records.keys(), reverse=True):
            record = records.get(record_date, {})
            if not isinstance(record, dict):
                continue
            try:
                in_last_30_days = cutoff <= date.fromisoformat(record_date) <= today
            except (TypeError, ValueError):
                in_last_30_days = False
            meal_names_for_day = set()
            global_names_for_day = set()
            for meal in MEALS:
                saved_meals = record.get("meals", {})
                if not isinstance(saved_meals, dict):
                    continue
                meal_items = saved_meals.get(meal, [])
                if not isinstance(meal_items, list):
                    continue
                for index, item in enumerate(meal_items):
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("food", "")).strip()
                    if not name or name not in known_names:
                        continue
                    if in_last_30_days:
                        global_names_for_day.add(name)
                        if meal == meal_name:
                            meal_names_for_day.add(name)
                    sort_key = str(item.get("added_at") or f"{record_date}T{index:06d}")
                    if in_last_30_days and meal == meal_name:
                        recent_candidates.append((sort_key, item))
                    if name not in latest_items or sort_key > latest_items[name][0]:
                        latest_items[name] = (sort_key, item)
                    if meal == meal_name and (name not in latest_meal_items or sort_key > latest_meal_items[name][0]):
                        latest_meal_items[name] = (sort_key, item)
            global_counts.update(global_names_for_day)
            meal_counts.update(meal_names_for_day)

        source_counts = meal_counts or global_counts
        common_names = [name for name, _ in sorted(source_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]]
        common = []
        for name in common_names:
            latest = latest_meal_items.get(name) or latest_items.get(name)
            if latest:
                common.append(latest[1])

        recent = []
        seen = set()
        for _, item in sorted(recent_candidates, key=lambda pair: pair[0], reverse=True):
            name = str(item.get("food", "")).strip()
            if name in seen:
                continue
            seen.add(name)
            recent.append(item)
            if len(recent) >= limit:
                break
        return common, recent

    def open_add_food_dialog(default_meal="午餐"):
        dialog_width = responsive_width()

        meal_dd = mobile_dropdown("餐次", default_meal, [ft.dropdown.Option(m) for m in MEALS], expand=True)
        search = mobile_text_field("搜索食物", expand=True)
        food_dd = mobile_dropdown("食物", None, [ft.dropdown.Option(f["name"]) for f in foods], expand=True)

        def current_unit():
            food = next((f for f in foods if f.get("name") == food_dd.value), None)
            return food.get("unit", "g") if food else "g"

        qty = mobile_text_field(f"数量（{current_unit()}）", keyboard_type=_KEYBOARD_NUMBER, expand=True)

        def update_qty_label():
            qty.label_text = f"数量（{current_unit()}）"

        def apply_filter(e=None):
            kw = (search.value or "").strip().lower()
            filtered = [f for f in foods if not kw or kw in f.get("name", "").lower() or kw in f.get("category", "").lower()]
            food_dd.options = [ft.dropdown.Option(f["name"]) for f in filtered]
            if len(filtered) == 1:
                food_dd.value = filtered[0]["name"]
            update_qty_label()
            page.update()

        def food_changed(e=None):
            update_qty_label()
            page.update()

        search.on_change = apply_filter
        food_dd.on_change = food_changed

        dlg = None

        def append_food(food, amount, meal_name, close_dialog=False):
            item = {
                "food": food["name"], "qty": amount, "unit": food.get("unit", "g"),
                "method": food.get("method", ""),
                "id": uuid.uuid4().hex,
                "added_at": datetime.datetime.now().isoformat(timespec="microseconds"),
                **calc_item(food, amount),
            }
            original_date = state["date"]
            item_id = item["id"]
            state["meals"].setdefault(meal_name, []).append(item)
            save_current()
            if close_dialog:
                close_control(dlg)
                refresh()

            def undo():
                original_record = records.get(original_date)
                if not isinstance(original_record, dict):
                    return
                original_meals = original_record.get("meals", {})
                if not isinstance(original_meals, dict):
                    return
                meal_items = original_meals.get(meal_name, [])
                if not isinstance(meal_items, list):
                    return
                index = next((i for i, saved in enumerate(meal_items) if isinstance(saved, dict) and saved.get("id") == item_id), None)
                if index is None:
                    return
                meal_items.pop(index)
                persist_records()
                if state.get("date") == original_date:
                    state["meals"].setdefault(meal_name, [])
                    state["meals"][meal_name] = [saved for saved in state["meals"][meal_name] if not isinstance(saved, dict) or saved.get("id") != item_id]
                    refresh()
                snack("已撤销快捷添加")

            snack(f"已添加 {food['name']} {amount:g}{food.get('unit', 'g')}", "撤销", undo)

        def select_shortcut(item):
            name = str(item.get("food", ""))
            food_dd.value = name
            search.value = ""
            qty.value = f"{to_float(item.get('qty')):g}"
            food_dd.options = [ft.dropdown.Option(f["name"]) for f in foods]
            update_qty_label()
            page.update()

        shortcut_mode = {"value": "common"}
        shortcut_list = ft.Column(spacing=6)
        shortcut_tabs = ft.Row(spacing=6)

        def shortcut_label(item):
            name = str(item.get("food", ""))
            qty_text = f"{to_float(item.get('qty')):g}{item.get('unit', '')}"
            return f"{name} · {qty_text}"

        def update_shortcuts(e=None):
            common_foods, recent_foods = food_shortcuts(meal_dd.value or default_meal)
            current = common_foods if shortcut_mode["value"] == "common" else recent_foods
            shortcut_list.controls.clear()
            if not current:
                shortcut_list.controls.append(small_text("记录几次后，这里会出现快捷食物"))
            for item in current:
                shortcut_list.controls.append(ft.Container(
                    content=ft.Row([
                        ft.Container(
                            content=ft.Text(shortcut_label(item), size=12, weight="bold", color=GREEN, max_lines=1, overflow="ellipsis"),
                            height=44, padding=ft.Padding(left=10, top=0, right=10, bottom=0),
                            alignment=ft.Alignment.CENTER_LEFT, expand=True,
                            on_click=lambda e, x=item: select_shortcut(x),
                        ),
                        ft.IconButton(icon=ft.Icons.ADD, icon_color="#FFFFFF", bgcolor=PRIMARY,
                                      icon_size=19, tooltip="按上次份量立即添加",
                                      on_click=lambda e, x=item: quick_add(x)),
                    ], spacing=4),
                    bgcolor=PRIMARY_SOFT, border=thin_border(), border_radius=8,
                    padding=ft.Padding(left=0, top=0, right=3, bottom=0),
                ))

            shortcut_tabs.controls = [
                make_button("常用", on_click=lambda e: set_shortcut_mode("common"), bgcolor=PRIMARY if shortcut_mode["value"] == "common" else PRIMARY_SOFT, color="#FFFFFF" if shortcut_mode["value"] == "common" else GREEN, expand=True),
                make_button("最近", on_click=lambda e: set_shortcut_mode("recent"), bgcolor=PRIMARY if shortcut_mode["value"] == "recent" else PRIMARY_SOFT, color="#FFFFFF" if shortcut_mode["value"] == "recent" else GREEN, expand=True),
            ]
            if e is not None:
                page.update()

        def set_shortcut_mode(mode):
            shortcut_mode["value"] = mode
            update_shortcuts(True)

        def quick_add(item):
            food = next((f for f in foods if f.get("name") == item.get("food")), None)
            amount = to_float(item.get("qty"), 0)
            if not food or amount <= 0:
                snack("快捷食物数据无效，请手动填写")
                return
            append_food(food, amount, meal_dd.value or default_meal, close_dialog=True)

        meal_dd.on_change = lambda e: update_shortcuts(True)
        update_shortcuts()

        def confirm(e):
            if not food_dd.value or not qty.value:
                snack("请选择食物并填写数量")
                return
            food = next((f for f in foods if f["name"] == food_dd.value), None)
            q = to_float(qty.value)
            if not food or q <= 0:
                snack("食物或数量不正确")
                return
            append_food(food, q, meal_dd.value or default_meal, close_dialog=True)

        dlg = full_form_sheet(
            "添加饮食",
            [
                diet_shortcut_panel(shortcut_tabs, shortcut_list),
                two_field_grid(meal_dd, qty, viewport_width=dialog_width),
                two_field_grid(search, food_dd, viewport_width=dialog_width),
            ],
            confirm,
        )
        open_control(dlg)

    def open_food_library_dialog(edit_index=None):
        editing = edit_index is not None
        dialog_width = responsive_width()
        item = foods[edit_index] if editing else {
            "name": "",
            "category": "",
            "unit": "g",
            "method": "",
            "base_qty": 100,
            "kcal": 0,
            "carb": 0,
            "protein": 0,
            "fat": 0,
        }

        field_labels = {
            "name": "食物名称",
            "category": "分类",
            "unit": "单位",
            "method": "计量口径",
            "base_qty": "基准数量",
            "kcal": "热量 kcal",
            "carb": "碳水 g",
            "protein": "蛋白 g",
            "fat": "脂肪 g",
        }

        fields = {}
        for key in ["name", "category", "method", "base_qty", "kcal", "carb", "protein", "fat"]:
            fields[key] = mobile_text_field(
                field_labels[key],
                value=str(item.get(key, "")),
                width=dialog_width if key == "method" else None,
                keyboard_type=_KEYBOARD_NUMBER if key in ["base_qty", "kcal", "carb", "protein", "fat"] else None,
                expand=key != "method",
            )
        unit_values = FOOD_UNIT_PRESETS
        current_unit = str(item.get("unit", "g") or "g")
        custom_unit_selected = current_unit not in unit_values
        fields["unit"] = mobile_dropdown(
            "单位",
            CUSTOM_UNIT_OPTION if custom_unit_selected else current_unit,
            [ft.dropdown.Option(value) for value in (*unit_values, CUSTOM_UNIT_OPTION)],
            expand=True,
        )
        fields["custom_unit"] = mobile_text_field(
            "自定义单位",
            current_unit if custom_unit_selected else "",
            expand=True,
        )
        custom_unit_holder = ft.Container(
            content=fields["custom_unit"],
            visible=custom_unit_selected,
        )

        bind_custom_unit_visibility(fields["unit"], custom_unit_holder, page.update)

        dlg = None

        def confirm(e):
            name = (fields["name"].value or "").strip()
            if not name:
                snack("食物名称不能为空")
                return

            selected_unit = resolve_food_unit(fields["unit"].value, fields["custom_unit"].value)
            if not selected_unit:
                snack("请填写自定义单位")
                return

            data = {k: (fields[k].value or "").strip() for k in ["name", "category", "method"]}
            data["unit"] = selected_unit
            for k in ["base_qty", "kcal", "carb", "protein", "fat"]:
                data[k] = to_float(fields[k].value)

            if editing:
                foods[edit_index] = data
            else:
                if any(f.get("name") == name for f in foods):
                    snack("食物已存在")
                    return
                foods.append(data)

            repositories.foods.save(foods)
            close_control(dlg)
            refresh()
            snack("食物库已保存")

        dlg = full_form_sheet(
            "修改食物" if editing else "新增食物",
            [
                section_title("名称与分类"),
                two_field_grid(fields["name"], fields["category"], viewport_width=dialog_width),
                section_title("计量口径"),
                quantity_unit_grid(fields["base_qty"], fields["unit"], viewport_width=dialog_width),
                custom_unit_holder, fields["method"],
                section_title("营养数据"),
                two_field_grid(fields["kcal"], fields["carb"], viewport_width=dialog_width),
                two_field_grid(fields["protein"], fields["fat"], viewport_width=dialog_width),
            ],
            confirm,
        )
        open_control(dlg)

    def delete_meal_item(meal, idx):
        try:
            state["meals"][meal].pop(idx)
            save_current()
            refresh()
        except Exception:
            pass

    def delete_food(idx):
        if 0 <= idx < len(foods):
            foods.pop(idx)
            repositories.foods.save(foods)
            refresh()

    def render_diet_page():
        total = daily_total()
        targets = get_targets()

        def set_day(day_name):
            state["day_type"] = day_name
            save_current()
            refresh()

        day_buttons = []
        for day_name in DAY_TYPES:
            selected = state["day_type"] == day_name
            day_buttons.append(make_button(day_name, on_click=lambda e, d=day_name: set_day(d), bgcolor=PRIMARY if selected else PRIMARY_SOFT, color="#FFFFFF" if selected else GREEN, expand=True))
        summary = card(ft.Column([
            section_title("饮食总览"),
            ft.Row(day_buttons, spacing=7),
            macro_progress_bar("碳水", total["carb"], target_min=targets["carb_min"], target_max=targets["carb_max"], kind="carb", width=responsive_bar_width()),
            macro_progress_bar("蛋白", total["protein"], target_min=targets["protein_min"], target_max=targets["protein_max"], kind="protein", width=responsive_bar_width()),
            macro_progress_bar("脂肪", total["fat"], target_min=targets["fat_min"], target_max=targets["fat_max"], kind="fat", width=responsive_bar_width()),
        ], spacing=8), padding=14)
        active = DietViewState(normalize_diet_view(state.get("current_view")))

        def select_diet_view(view):
            set_view(diet_route_for_view(view))

        shell = build_diet_shell(
            active,
            DietShellRenderers(
                today_diet=lambda: ft.Column([summary, render_diet()], spacing=0),
                food_library=render_food_library,
            ),
            select_diet_view,
        )
        return ft.Container(content=shell, padding=ft.Padding(left=8, top=8, right=8, bottom=0))

    def render_diet():
        total = daily_total()
        selected_meal = state.get("selected_meal", "汇总")

        def set_selected_meal(meal):
            state["selected_meal"] = meal
            refresh()

        def meal_count(meal):
            if meal == "汇总":
                return sum(len(state["meals"].get(m, [])) for m in MEALS)
            return len(state["meals"].get(meal, []))

        def meal_button(meal):
            selected = selected_meal == meal
            count = meal_count(meal)
            label = meal if count == 0 else f"{meal} {count}"
            return ft.Container(content=ft.Text(label, size=12, weight="bold", color="#FFFFFF" if selected else GREEN, text_align="center", max_lines=1, overflow="ellipsis"), bgcolor=PRIMARY if selected else PRIMARY_SOFT, border=thin_border(PRIMARY if selected else BORDER), border_radius=8, height=44, alignment=ft.Alignment.CENTER, padding=6, expand=True, on_click=lambda e, m=meal: set_selected_meal(m))

        def meal_totals(meal):
            t = {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}
            items = state.get("meals", {}).get(meal, []) if isinstance(state.get("meals"), dict) else []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                for k in t:
                    t[k] += to_float(item.get(k))
            return {k: round(v, 1) for k, v in t.items()}

        content_rows = []
        if selected_meal == "汇总":
            any_record = False
            for meal in MEALS:
                raw_items = state.get("meals", {}).get(meal, []) if isinstance(state.get("meals"), dict) else []
                items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
                if not items:
                    continue
                any_record = True
                mt = meal_totals(meal)
                names = "、".join([str(x.get("food", "")) for x in items[:3]])
                if len(items) > 3:
                    names += "…"
                content_rows.append(ft.Container(content=ft.Column([
                    ft.Row([ft.Text(meal, size=13, weight="bold", color=TEXT), small_text(f"{mt['kcal']} kcal｜碳{mt['carb']} 蛋{mt['protein']} 脂{mt['fat']}")], alignment="spaceBetween"),
                    ft.Text(names, size=12, color=SUB) if names else ft.Container(),
                ], spacing=2), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))
            if not any_record:
                content_rows.append(ft.Container(content=small_text("暂无饮食记录"), bgcolor="#FAFAFA", border_radius=12, padding=10))
            header_right = f"{total['kcal']} kcal｜碳 {total['carb']}g｜蛋白 {total['protein']}g｜脂肪 {total['fat']}g"
        else:
            raw_meal_items = state.get("meals", {}).get(selected_meal, []) if isinstance(state.get("meals"), dict) else []
            meal_items = [item for item in raw_meal_items if isinstance(item, dict)] if isinstance(raw_meal_items, list) else []
            mt = meal_totals(selected_meal)
            header_right = f"{mt['kcal']} kcal｜碳 {mt['carb']}g｜蛋白 {mt['protein']}g｜脂肪 {mt['fat']}g"
            if meal_items:
                for idx, item in enumerate(meal_items):
                    content_rows.append(ft.Container(content=ft.Row([
                        ft.Column([ft.Text(f"{item.get('food')} {item.get('qty')}{item.get('unit')}", size=13, weight="bold", color=TEXT), small_text(f"{item.get('kcal')} kcal｜碳 {item.get('carb')}｜蛋 {item.get('protein')}｜脂 {item.get('fat')}")], expand=True, spacing=2),
                        ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, icon_size=18, on_click=lambda e, m=selected_meal, i=idx: delete_meal_item(m, i)),
                    ], alignment="spaceBetween"), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))
            else:
                content_rows.append(ft.Container(content=small_text("暂无记录"), bgcolor="#FAFAFA", border_radius=12, padding=10))

        return card(ft.Column([
            ft.Row([section_title("饮食记录"), make_button("添加", on_click=lambda e, m=(meal_for_current_time() if selected_meal=="汇总" else selected_meal): open_add_food_dialog(m), icon=ft.Icons.ADD, expand=False)], alignment="spaceBetween"),
            ft.Row([meal_button("汇总"), meal_button("早餐"), meal_button("午餐"), meal_button("晚餐")], spacing=5),
            ft.Row([meal_button("练前"), meal_button("练后"), meal_button("偷吃")], spacing=5),
            ft.Container(content=ft.Column([
                ft.Row([
                    ft.Text(selected_meal, size=13, weight="bold", color=TEXT),
                    ft.Text(header_right, size=12, color=SUB, text_align="end", max_lines=2, overflow="ellipsis", expand=True),
                ], spacing=8, vertical_alignment="start"),
                ft.Column(content_rows, spacing=1),
            ], spacing=6), bgcolor="#FFFFFF", border_radius=8, padding=8),
        ], spacing=8))

    def render_food_library():
        search = mobile_text_field("搜索食物", value="", expand=True)
        list_box = ft.Column(spacing=4)

        def rebuild_list(e=None):
            kw = (search.value or "").strip().lower()
            list_box.controls.clear()
            filtered = [(i, f) for i, f in enumerate(foods) if not kw or kw in f.get("name", "").lower() or kw in f.get("category", "").lower()]
            for idx, f in filtered:
                list_box.controls.append(card(ft.Row([
                    ft.Column([
                        ft.Text(f"{f.get('name')}｜{f.get('category')}", size=14, weight="bold"),
                        small_text(f"{f.get('method')}｜基准 {f.get('base_qty')}{f.get('unit')}｜{f.get('kcal')} kcal｜碳 {f.get('carb')} 蛋白 {f.get('protein')} 脂肪 {f.get('fat')}")
                    ], expand=True, spacing=2),
                    ft.IconButton(icon=ft.Icons.EDIT, icon_color=PRIMARY, on_click=lambda e, i=idx: open_food_library_dialog(i)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, on_click=lambda e, i=idx: delete_food(i)),
                ]), padding=10, margin_bottom=6))
            page.update()

        search.on_change = rebuild_list
        rebuild_list()
        return ft.Column([
            card(ft.Row([section_title("食物库"), make_button("新增", on_click=lambda e: open_food_library_dialog(), icon=ft.Icons.ADD)], alignment="spaceBetween")),
            card(search, padding=10),
            list_box,
        ], spacing=0)

    return DietController(
        foods=foods,
        supplements=supplements,
        render_page=render_diet_page,
        open_add_food=open_add_food_dialog,
        open_food_editor=open_food_library_dialog,
        delete_food=delete_food,
        food_shortcuts=food_shortcuts,
    )


__all__ = ["DietController", "DietControllerDependencies", "create_diet_controller"]

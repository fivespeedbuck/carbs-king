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
from food_library import FOOD_CATEGORIES, food_catalog, search_foods
from form_views import FormViewContext, build_full_form_sheet
from repositories import AppRepositories
from ui_components import (
    BORDER, GREEN, INPUT_FIELD_HEIGHT,
    PRIMARY, PRIMARY_SOFT, RED, SUB, TEXT, card, page_card, macro_progress_bar,
    make_button, mobile_dropdown, mobile_text_field, quantity_unit_grid, section_title,
    set_input_focused, small_text, thin_border, two_field_grid,
)


FOOD_UNIT_PRESETS = ("g", "ml", "个", "份")
CUSTOM_UNIT_OPTION = "自定义"


def compact_daily_summary(total: Mapping[str, Any]) -> str:
    """Keep the phone-width daily total on one line with whole values."""
    whole = {
        key: max(0, int(to_float(total.get(key)) + 0.5))
        for key in ("kcal", "carb", "protein", "fat")
    }
    return (
        f"{whole['kcal']}kcal｜碳{whole['carb']}g｜"
        f"蛋{whole['protein']}g｜脂{whole['fat']}g"
    )


def resolve_food_unit(selected_unit: Any, custom_unit: Any = "") -> str:
    selected = str(selected_unit or "").strip()
    if selected == CUSTOM_UNIT_OPTION:
        return str(custom_unit or "").strip()
    return selected


def update_food_selector(selector: Any, matches: list[Mapping[str, Any]]) -> None:
    """Update either the Add Food choice sheet or a legacy Dropdown."""
    names = [str(item.get("name") or "").strip() for item in matches]
    names = [name for name in names if name]
    set_choices = getattr(selector, "set_choices", None)
    if callable(set_choices):
        set_choices(names)
        return
    selector.options = [ft.dropdown.Option(name) for name in names]
    selector.field.disabled = not names
    selector.field.hint_text = "无匹配食物" if not names else "请选择食物"
    selector.field.menu_height = min(240, max(48, len(names) * 48))
    if len(names) == 1:
        selector.value = names[0]
    elif str(selector.value or "") not in names:
        selector.value = None


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
    food_shortcuts: Callable[..., list[dict[str, Any]]]


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
    foods = food_catalog(repositories.foods.load())
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
        """Return meal-aware frequent foods with their last editable quantity."""
        today = date.today()
        cutoff = today - datetime.timedelta(days=29)
        meal_counts = Counter()
        global_counts = Counter()
        latest_items = {}
        latest_meal_items = {}
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

        return common

    def open_add_food_dialog(default_meal="午餐"):
        dialog_width = responsive_width()

        def upward_choice_input(label, value, choices):
            """Opaque bottom choice sheet used instead of Android's transparent popup."""
            control = mobile_text_field(label, value or "", expand=True)
            field = control.field
            field.read_only = True
            field.show_cursor = False
            field.can_request_focus = False
            field.suffix_icon = ft.Icons.ARROW_DROP_DOWN
            control.choice_values = []

            def set_choices(values):
                clean = [str(item).strip() for item in values if str(item).strip()]
                control.choice_values = clean
                field.hint_text = "无匹配食物" if not clean else "请选择"
                if len(clean) == 1:
                    control.value = clean[0]
                elif str(control.value or "") not in clean:
                    control.value = ""

            def open_choices(e=None):
                values = list(control.choice_values)
                if not values:
                    return
                set_input_focused(False)
                choice_sheet = None

                def choose(selected_value):
                    control.value = selected_value
                    close_control(choice_sheet)
                    handler = control.on_change
                    if callable(handler):
                        handler(None)
                    else:
                        page.update()

                rows = [ft.Container(
                    content=ft.Text(
                        item,
                        size=16,
                        color=TEXT,
                        weight="bold" if item == control.value else None,
                        max_lines=1,
                        overflow="ellipsis",
                    ),
                    height=50,
                    padding=ft.Padding(left=18, top=0, right=18, bottom=0),
                    alignment=ft.Alignment.CENTER_LEFT,
                    bgcolor=PRIMARY_SOFT if item == control.value else "#FFFFFF",
                    border=ft.Border(bottom=ft.BorderSide(1, BORDER)),
                    ink=True,
                    on_click=lambda event, selected=item: choose(selected),
                ) for item in values]
                # Keep the final option above Android's gesture/navigation
                # area. The spacer scrolls into view after the last row.
                safe_bottom_spacer = ft.Container(
                    height=28,
                    bgcolor="#FFFFFF",
                    data="upward-choice-safe-bottom",
                )
                list_height = min(330, max(78, len(rows) * 50 + 28))
                choice_sheet = ft.BottomSheet(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Container(
                                content=ft.Row([
                                    ft.Text(label, size=18, weight="bold", color=TEXT),
                                    ft.IconButton(
                                        icon=ft.Icons.CLOSE,
                                        tooltip="关闭",
                                        on_click=lambda event: close_control(choice_sheet),
                                    ),
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                padding=ft.Padding(left=18, top=4, right=8, bottom=4),
                                bgcolor="#FFFFFF",
                            ),
                            ft.Column(
                                [*rows, safe_bottom_spacer],
                                height=list_height,
                                spacing=0,
                                scroll=_SCROLL_HIDDEN,
                            ),
                        ], spacing=0, tight=True),
                        bgcolor="#FFFFFF",
                        border_radius=ft.BorderRadius(
                            top_left=16, top_right=16, bottom_left=0, bottom_right=0
                        ),
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    ),
                    bgcolor="#FFFFFF",
                    barrier_color="#66000000",
                    dismissible=True,
                    draggable=True,
                    show_drag_handle=True,
                    use_safe_area=True,
                    data="upward-choice-sheet",
                )
                open_control(choice_sheet)

            control.set_choices = set_choices
            control.open_choice_panel = open_choices
            field.on_click = open_choices
            set_choices(choices)
            return control

        meal_dd = upward_choice_input("餐次", default_meal, MEALS)
        search = mobile_text_field("搜索食物", expand=True)
        food_dd = upward_choice_input("食物", None, [])
        update_food_selector(food_dd, foods[:24])

        def current_unit():
            food = next((f for f in foods if f.get("name") == food_dd.value), None)
            return food.get("unit", "g") if food else "g"

        qty = mobile_text_field(f"数量（{current_unit()}）", keyboard_type=_KEYBOARD_NUMBER, expand=True)

        def fixed_food_field(control):
            """Give Dropdown and TextField the same painted Android outline."""
            field = control.field
            field.height = INPUT_FIELD_HEIGHT
            field.border = ft.InputBorder.NONE
            field.bgcolor = ft.Colors.TRANSPARENT
            field.content_padding = 12
            control.controls[1] = ft.Container(
                content=field,
                height=INPUT_FIELD_HEIGHT,
                bgcolor="#FFFFFF",
                border=thin_border(),
                border_radius=8,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            )
            return control

        for control in (meal_dd, qty, search, food_dd):
            fixed_food_field(control)

        def choose_portion(grams):
            # Dishes are recorded by what was actually eaten, not the whole
            # shared plate. These are intentionally editable gram shortcuts.
            qty.value = str(grams)
            page.update()

        portion_shortcuts = ft.Column([
            ft.Row([
                make_button("一两口 30g", on_click=lambda e: choose_portion(30), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True, height=56),
                make_button("几口 60g", on_click=lambda e: choose_portion(60), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True, height=56),
            ], spacing=8),
            ft.Row([
                make_button("半份 150g", on_click=lambda e: choose_portion(150), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True, height=56),
                make_button("一份 250g", on_click=lambda e: choose_portion(250), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True, height=56),
            ], spacing=8),
        ], spacing=8)

        def update_qty_label():
            qty.label_text = f"数量（{current_unit()}）"

        def apply_filter(e=None):
            kw = (search.value or "").strip().lower()
            filtered = search_foods(kw, foods=foods)[:24]
            update_food_selector(food_dd, filtered)
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
                snack("已撤销添加")

            snack(f"已添加 {food['name']} {amount:g}{food.get('unit', 'g')}", "撤销", undo)

        def select_shortcut(item):
            name = str(item.get("food", ""))
            # Keep the dropdown payload small. Sending the complete 2,000+
            # food catalog on every shortcut click can stall the Flet client,
            # and setting a value before its option exists creates a transient
            # invalid Dropdown state. Add the selected food to the normal
            # 24-item window first, then prefill the editable fields.
            visible_names = [str(food.get("name", "")) for food in foods[:24]]
            if name and name not in visible_names:
                visible_names.insert(0, name)
            food_dd.set_choices([value for value in visible_names if value])
            food_dd.value = name
            search.value = ""
            qty.value = f"{to_float(item.get('qty')):g}"
            update_qty_label()
            page.update()

        shortcut_list = ft.Column(spacing=6)
        shortcut_header = ft.Container(
            content=ft.Text("常用", size=14, weight="bold", color="#FFFFFF", text_align="center"),
            height=48,
            bgcolor=PRIMARY,
            border_radius=8,
            alignment=ft.Alignment.CENTER,
        )

        def shortcut_label(item):
            name = str(item.get("food", ""))
            qty_text = f"{to_float(item.get('qty')):g}{item.get('unit', '')}"
            return f"{name} · {qty_text}"

        def update_shortcuts(e=None):
            current = food_shortcuts(meal_dd.value or default_meal)
            shortcut_list.controls.clear()
            if not current:
                shortcut_list.controls.append(small_text("记录几次后，这里会出现快捷食物"))
            for item in current:
                shortcut_list.controls.append(ft.Container(
                    content=ft.Text(shortcut_label(item), size=12, weight="bold", color=GREEN, max_lines=1, overflow="ellipsis"),
                    height=44,
                    bgcolor=PRIMARY_SOFT, border=thin_border(), border_radius=8,
                    padding=ft.Padding(left=10, top=0, right=10, bottom=0),
                    alignment=ft.Alignment.CENTER_LEFT,
                    on_click=lambda e, x=item: select_shortcut(x),
                ))

            if e is not None:
                page.update()

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
                diet_shortcut_panel(shortcut_header, shortcut_list),
                two_field_grid(meal_dd, qty, viewport_width=dialog_width),
                portion_shortcuts,
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
        target_controls = (
            [small_text(str(targets.get("profile_message", "请完善个人资料后计算营养目标。")))]
            if not targets.get("is_ready", True)
            else [
                macro_progress_bar("碳水", total["carb"], target_min=targets["carb_min"], target_max=targets["carb_max"], kind="carb", width=responsive_bar_width()),
                macro_progress_bar("蛋白", total["protein"], target_min=targets["protein_min"], target_max=targets["protein_max"], kind="protein", width=responsive_bar_width()),
                macro_progress_bar("脂肪", total["fat"], target_min=targets["fat_min"], target_max=targets["fat_max"], kind="fat", width=responsive_bar_width()),
            ]
        )
        summary = page_card(ft.Column([
            section_title("饮食总览"),
            ft.Row(day_buttons, spacing=7),
            *target_controls,
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
        # Cards already own the shared 8 px page gutter.  Do not apply a
        # second horizontal inset here or the diet cards become narrower than
        # their peers on Today, Data and Me pages.
        return ft.Container(content=shell, padding=ft.Padding(left=0, top=8, right=0, bottom=0))

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
            header_right = compact_daily_summary(total)
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

        return page_card(ft.Column([
            ft.Row([section_title("饮食记录"), make_button("添加", on_click=lambda e, m=(meal_for_current_time() if selected_meal=="汇总" else selected_meal): open_add_food_dialog(m), icon=ft.Icons.ADD, expand=False)], alignment="spaceBetween"),
            ft.Row([meal_button("汇总"), meal_button("早餐"), meal_button("午餐"), meal_button("晚餐")], spacing=5),
            ft.Row([meal_button("练前"), meal_button("练后"), meal_button("偷吃")], spacing=5),
            ft.Container(content=ft.Column([
                ft.Row([
                    ft.Text(selected_meal, size=13, weight="bold", color=TEXT),
                    ft.Text(
                        header_right,
                        size=11 if selected_meal == "汇总" else 12,
                        color=SUB,
                        text_align="end",
                        max_lines=1 if selected_meal == "汇总" else 2,
                        overflow="ellipsis",
                        expand=True,
                    ),
                ], spacing=8, vertical_alignment="start"),
                ft.Column(content_rows, spacing=1),
            ], spacing=6), bgcolor="#FFFFFF", border_radius=8, padding=8),
        ], spacing=8))

    def _render_food_library_legacy():
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

    def render_food_library():
        """Fast, no-image food browser for the bundled 1,657-item catalog."""
        search = mobile_text_field("搜索食物", value="", expand=True)
        selected = {"category": "全部", "subgroup": "全部", "limit": 24}
        scroll_auto = getattr(getattr(ft, "ScrollMode", object()), "AUTO", "auto")
        filter_row = ft.Row(spacing=6, scroll=scroll_auto)
        list_box = ft.ListView(spacing=4, height=520, build_controls_on_demand=True, cache_extent=180)
        load_more_holder = ft.Column(spacing=6)

        def rebuild_filters():
            controls = [make_button(
                "全部",
                on_click=lambda e: choose_category("全部"),
                bgcolor=PRIMARY if selected["category"] == "全部" else PRIMARY_SOFT,
                color="#FFFFFF" if selected["category"] == "全部" else GREEN,
            )]
            controls.extend(
                make_button(
                    label,
                    on_click=lambda e, value=label: choose_category(value),
                    bgcolor=PRIMARY if selected["category"] == label and selected["subgroup"] == "全部" else PRIMARY_SOFT,
                    color="#FFFFFF" if selected["category"] == label and selected["subgroup"] == "全部" else GREEN,
                )
                for label in FOOD_CATEGORIES
            )
            if selected["category"] != "全部":
                subgroups = list(dict.fromkeys(
                    str(item.get("subgroup") or "其他")
                    for item in foods if item.get("category") == selected["category"]
                ))
                if selected["subgroup"] not in subgroups:
                    selected["subgroup"] = "全部"
                controls.extend(
                    make_button(
                        label,
                        on_click=lambda e, value=label: choose_subgroup(value),
                        bgcolor=PRIMARY if selected["subgroup"] == label else PRIMARY_SOFT,
                        color="#FFFFFF" if selected["subgroup"] == label else GREEN,
                    )
                    for label in subgroups
                )
            filter_row.controls = controls

        def choose_category(category):
            selected["category"] = category
            selected["subgroup"] = "全部"
            selected["limit"] = 24
            rebuild_filters()
            rebuild_list()
            page.update()

        def choose_subgroup(subgroup):
            selected["subgroup"] = subgroup
            selected["limit"] = 24
            rebuild_filters()
            rebuild_list()
            page.update()

        def load_more(e=None):
            selected["limit"] += 24
            rebuild_list()
            page.update()

        def rebuild_list(e=None):
            keyword = str(search.value or "").strip()
            category = None if keyword or selected["category"] == "全部" else selected["category"]
            matched = search_foods(keyword, category=category, foods=foods)
            if not keyword and selected["subgroup"] != "全部":
                matched = [item for item in matched if str(item.get("subgroup") or "其他") == selected["subgroup"]]
            visible = matched[:selected["limit"]]
            list_box.controls.clear()
            for food in visible:
                name = str(food.get("name") or "")
                index = next((i for i, item in enumerate(foods) if item.get("name") == name), -1)
                if index < 0:
                    continue
                macros = (
                    f"每 100g：{food.get('kcal')} kcal · 碳水 {food.get('carb')}g · "
                    f"蛋白 {food.get('protein')}g · 脂肪 {food.get('fat')}g"
                )
                micros = f"纤维 {food.get('fiber', 0)}g · 胆固醇 {food.get('cholesterol', 0)}mg"
                list_box.controls.append(card(ft.Row([
                    ft.Column([
                        ft.Text(f"{name} · {food.get('category')}", size=14, weight="bold", max_lines=1, overflow="ellipsis"),
                        small_text(macros),
                        small_text(micros, color=GREEN),
                    ], expand=True, spacing=2),
                    ft.IconButton(icon=ft.Icons.EDIT, icon_color=PRIMARY, on_click=lambda e, i=index: open_food_library_dialog(i)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, on_click=lambda e, i=index: delete_food(i)),
                ]), padding=10, margin_bottom=6))
            load_more_holder.controls.clear()
            if len(matched) > len(visible):
                load_more_holder.controls.append(make_button(
                    f"加载更多（已显示 {len(visible)}/{len(matched)}）",
                    on_click=load_more,
                    bgcolor=PRIMARY_SOFT,
                    color=GREEN,
                    expand=True,
                ))
            if e is not None:
                page.update()

        def on_search_change(e=None):
            selected["limit"] = 24
            rebuild_list(e)

        search.on_change = on_search_change
        rebuild_filters()
        rebuild_list()
        return ft.Column([
            card(ft.Row([section_title("食物库"), make_button("新增", on_click=lambda e: open_food_library_dialog(), icon=ft.Icons.ADD)], alignment="spaceBetween")),
            card(search, padding=10),
            card(ft.Container(content=filter_row, height=52, clip_behavior=ft.ClipBehavior.HARD_EDGE), padding=10),
            list_box,
            load_more_holder,
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

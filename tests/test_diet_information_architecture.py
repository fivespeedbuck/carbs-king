import unittest
from pathlib import Path
from types import SimpleNamespace

import flet as ft

from diet_service import (
    DIET_VIEWS,
    FOOD_LIBRARY_VIEW,
    ME_PAGE_BLOCKED_SUPPLEMENT_ACTIONS,
    PersistedSupplementList,
    SUPPLEMENT_LIBRARY_VIEW,
    TODAY_DIET_VIEW,
    DietViewState,
    diet_route_for_view,
    me_page_allows_action,
    normalize_diet_view,
    recovery_exposes_only_today_supplements,
    recovery_owns_supplement_surfaces,
    select_diet_view,
)
from diet_controller import (
    CUSTOM_UNIT_OPTION,
    FOOD_UNIT_PRESETS,
    bind_custom_unit_visibility,
    resolve_food_unit,
)
from diet_views import (
    DIET_INPUT_FIELD_HEIGHT,
    DIET_INPUT_LABEL_HEIGHT,
    DIET_TAB_HEIGHT,
    DietShellRenderers,
    aligned_input_row,
    build_diet_shell,
    diet_shortcut_panel,
    diet_tabs,
    fixed_labeled_input,
)
from form_views import (
    FORM_BODY_SPACING,
    FORM_FOOTER_SPACING,
    FORM_HORIZONTAL_PADDING,
    FORM_SHEET_CORNER_RADIUS,
    FormViewContext,
    build_full_form_sheet,
)
from ui_components import (
    FIELD_GRID_COLLAPSE_WIDTH,
    INPUT_LABEL_HEIGHT,
    mobile_dropdown,
    mobile_text_field,
    quantity_unit_grid,
    responsive_field_grid,
    three_field_grid,
    two_field_grid,
)
from today_views import TODAY_SECTION_SPACING, TodayDashboardActions, TodayDashboardModel, build_date_toolbar, build_today_dashboard


ROOT = Path(__file__).resolve().parents[1]
DIET_CONTROLLER_SOURCE = (ROOT / "src" / "diet_controller.py").read_text(encoding="utf-8-sig")
RECOVERY_CONTROLLER_SOURCE = (ROOT / "src" / "recovery_controller.py").read_text(encoding="utf-8-sig")


class DietInformationArchitectureTests(unittest.TestCase):
    def test_diet_subviews_are_mutually_exclusive(self):
        state = select_diet_view(DietViewState(), "supplements")

        self.assertEqual(state.active_view, TODAY_DIET_VIEW)
        self.assertEqual(
            state.visibility(),
            {
                TODAY_DIET_VIEW: True,
                FOOD_LIBRARY_VIEW: False,
            },
        )
        self.assertEqual(DIET_VIEWS, (TODAY_DIET_VIEW, FOOD_LIBRARY_VIEW))

    def test_legacy_routes_map_to_new_diet_shell_views(self):
        self.assertEqual(normalize_diet_view("diet"), TODAY_DIET_VIEW)
        self.assertEqual(normalize_diet_view("foods"), FOOD_LIBRARY_VIEW)
        self.assertEqual(normalize_diet_view("supplements"), TODAY_DIET_VIEW)
        self.assertEqual(normalize_diet_view("unknown"), TODAY_DIET_VIEW)

        self.assertEqual(diet_route_for_view(TODAY_DIET_VIEW), "diet")
        self.assertEqual(diet_route_for_view(FOOD_LIBRARY_VIEW), "foods")
        self.assertEqual(diet_route_for_view(SUPPLEMENT_LIBRARY_VIEW), "diet")

    def test_recovery_exclusively_owns_today_supplements_and_library(self):
        self.assertTrue(recovery_owns_supplement_surfaces(("today_supplements", "supplement_library")))
        self.assertTrue(recovery_exposes_only_today_supplements(("today_supplements", "supplement_library")))
        self.assertFalse(recovery_exposes_only_today_supplements(("today_supplements",)))

    def test_me_page_contract_blocks_supplement_management_actions(self):
        for action in ME_PAGE_BLOCKED_SUPPLEMENT_ACTIONS:
            self.assertFalse(me_page_allows_action(action))
        self.assertTrue(me_page_allows_action("export_handler:foods"))


class DietViewComponentTests(unittest.TestCase):
    def test_tabs_keep_fixed_touch_height_and_single_line_labels(self):
        selected = []
        row = diet_tabs(DietViewState(FOOD_LIBRARY_VIEW), selected.append)

        self.assertEqual(len(row.controls), len(DIET_VIEWS))
        for tab in row.controls:
            self.assertEqual(tab.height, DIET_TAB_HEIGHT)
            self.assertTrue(tab.expand)
            self.assertEqual(tab.content.max_lines, 1)
            self.assertEqual(tab.content.overflow, "ellipsis")

    def test_shell_renders_only_active_panel(self):
        calls = []
        renderers = DietShellRenderers(
            today_diet=lambda: calls.append("today") or "today-panel",
            food_library=lambda: calls.append("foods") or "foods-panel",
        )

        shell = build_diet_shell(DietViewState(FOOD_LIBRARY_VIEW), renderers, lambda view: None)

        self.assertEqual(calls, ["foods"])
        self.assertEqual(shell.controls[1], "foods-panel")

    def test_fixed_labeled_input_uses_external_fixed_label_not_floating_label(self):
        field = ft.TextField()
        control = fixed_labeled_input("数量", field, expand=True)

        self.assertEqual(control.controls[0].height, DIET_INPUT_LABEL_HEIGHT)
        self.assertEqual(control.controls[0].content.value, "数量")
        self.assertEqual(control.controls[0].content.max_lines, 2)
        self.assertEqual(control.field.height, DIET_INPUT_FIELD_HEIGHT)
        self.assertIsNone(field.label)

    def test_parallel_input_rows_are_top_aligned(self):
        row = aligned_input_row(["left", "right"])

        self.assertEqual(row.vertical_alignment, "start")
        self.assertEqual(row.spacing, 8)

    def test_shortcut_panel_keeps_tabs_and_results_together(self):
        tabs = ft.Row()
        shortcuts = ft.Column()

        panel = diet_shortcut_panel(tabs, shortcuts)

        self.assertEqual(panel.controls, [tabs, shortcuts])
        self.assertEqual(panel.spacing, 8)
        self.assertEqual(panel.horizontal_alignment, ft.CrossAxisAlignment.STRETCH)
        self.assertTrue(panel.tight)


class ResponsiveFieldLayoutTests(unittest.TestCase):
    def test_labels_use_fixed_two_line_slot_and_equal_field_height(self):
        short = mobile_text_field("数量", "1")
        long = mobile_text_field("这是一个需要换行的较长字段标签", "2")

        for control in (short, long):
            self.assertEqual(control.controls[0].height, INPUT_LABEL_HEIGHT)
            self.assertEqual(control.controls[0].content.max_lines, 2)
            self.assertEqual(control.field.height, DIET_INPUT_FIELD_HEIGHT)
        self.assertEqual(short.controls[0].height, long.controls[0].height)

    def test_430_viewport_content_keeps_pairs_and_triplets_but_narrow_width_collapses(self):
        fields = [mobile_text_field(label) for label in ("重量", "次数", "组数")]
        triplet = three_field_grid(*fields, viewport_width=340)
        narrow = responsive_field_grid(fields[:2], columns=2, viewport_width=FIELD_GRID_COLLAPSE_WIDTH - 1)

        self.assertEqual([cell.col["xs"] for cell in triplet.controls], [4, 4, 4])
        self.assertEqual([cell.col["xs"] for cell in narrow.controls], [12, 12])
        self.assertEqual(triplet.vertical_alignment, "start")

    def test_shared_pair_and_quantity_unit_proportions(self):
        quantity = mobile_text_field("基准数量")
        unit = mobile_text_field("单位")
        pair = two_field_grid(quantity, unit, viewport_width=340)
        compact = quantity_unit_grid(quantity, unit, viewport_width=340)

        self.assertEqual([cell.col["xs"] for cell in pair.controls], [6, 6])
        self.assertIs(compact.controls[0].content, quantity)
        self.assertIs(compact.controls[1].content, unit)
        self.assertEqual([cell.col["xs"] for cell in compact.controls], [8, 4])

    def test_fullscreen_form_keeps_scroll_body_separate_from_reachable_footer(self):
        closed = []
        sheet = build_full_form_sheet(
            FormViewContext(close_control=closed.append, scroll_mode="hidden"),
            "430x860 表单",
            [mobile_text_field("长标签字段") for _ in range(10)],
            lambda event: None,
        )

        layout = sheet.content.content
        body = layout.controls[1]
        footer = layout.controls[2]
        self.assertTrue(sheet.fullscreen)
        self.assertTrue(sheet.use_safe_area)
        self.assertTrue(sheet.maintain_bottom_view_insets_padding)
        self.assertEqual(sheet.content.border_radius.top_left, FORM_SHEET_CORNER_RADIUS)
        self.assertEqual(sheet.content.border_radius.top_right, FORM_SHEET_CORNER_RADIUS)
        self.assertEqual(sheet.content.border_radius.bottom_left, 0)
        self.assertEqual(sheet.content.border_radius.bottom_right, 0)
        self.assertEqual(sheet.content.clip_behavior, ft.ClipBehavior.HARD_EDGE)
        self.assertEqual(body.content.scroll, "hidden")
        self.assertTrue(body.content.expand)
        self.assertEqual(body.content.spacing, FORM_BODY_SPACING)
        self.assertEqual(body.content.horizontal_alignment, ft.CrossAxisAlignment.STRETCH)
        self.assertEqual(body.padding.left, FORM_HORIZONTAL_PADDING)
        self.assertEqual(body.padding.right, FORM_HORIZONTAL_PADDING)
        self.assertIsNot(body, footer)
        self.assertEqual(len(footer.content.controls), 2)
        self.assertEqual(footer.content.spacing, FORM_FOOTER_SPACING)
        self.assertEqual(footer.padding.left, FORM_HORIZONTAL_PADDING)
        self.assertEqual(footer.padding.right, FORM_HORIZONTAL_PADDING)
        self.assertTrue(all(button.height >= 48 for button in footer.content.controls))

    def test_food_form_uses_required_full_width_and_compact_pair_structure(self):
        self.assertEqual(FOOD_UNIT_PRESETS, ("g", "ml", "个", "份"))
        self.assertEqual(CUSTOM_UNIT_OPTION, "自定义")
        self.assertIn("ft.dropdown.Option(value) for value in (*unit_values, CUSTOM_UNIT_OPTION)", DIET_CONTROLLER_SOURCE)
        self.assertIn('quantity_unit_grid(fields["base_qty"], fields["unit"], viewport_width=dialog_width)', DIET_CONTROLLER_SOURCE)
        self.assertNotIn('unit_first=True', DIET_CONTROLLER_SOURCE)
        self.assertIn('selected_unit = resolve_food_unit(fields["unit"].value, fields["custom_unit"].value)', DIET_CONTROLLER_SOURCE)
        self.assertIn('two_field_grid(fields["name"], fields["category"]', DIET_CONTROLLER_SOURCE)
        self.assertIn('two_field_grid(fields["kcal"], fields["carb"]', DIET_CONTROLLER_SOURCE)
        self.assertIn('two_field_grid(fields["protein"], fields["fat"]', DIET_CONTROLLER_SOURCE)
        self.assertIn('width=dialog_width if key == "method" else None', DIET_CONTROLLER_SOURCE)
        self.assertIn('expand=key != "method"', DIET_CONTROLLER_SOURCE)

    def test_custom_food_unit_resolves_without_losing_existing_presets(self):
        self.assertEqual(resolve_food_unit("g", "杯"), "g")
        self.assertEqual(resolve_food_unit(CUSTOM_UNIT_OPTION, " 杯 "), "杯")
        self.assertEqual(resolve_food_unit(CUSTOM_UNIT_OPTION, "  "), "")

    def test_custom_unit_visibility_uses_real_dropdown_select_event(self):
        updates = []
        unit = mobile_dropdown(
            "单位",
            "g",
            [ft.dropdown.Option(value) for value in (*FOOD_UNIT_PRESETS, CUSTOM_UNIT_OPTION)],
        )
        holder = ft.Container(content=mobile_text_field("自定义单位"), visible=False)

        handler = bind_custom_unit_visibility(unit, holder, lambda: updates.append(holder.visible))

        self.assertIs(unit.field.on_select, handler)
        unit.field.on_select(SimpleNamespace(control=SimpleNamespace(value=CUSTOM_UNIT_OPTION)))
        self.assertEqual(unit.value, CUSTOM_UNIT_OPTION)
        self.assertTrue(holder.visible)
        unit.field.on_select(SimpleNamespace(control=SimpleNamespace(value="ml")))
        self.assertEqual(unit.value, "ml")
        self.assertFalse(holder.visible)
        self.assertEqual(updates, [True, False])

    def test_add_diet_form_pairs_meal_quantity_and_search_food(self):
        self.assertIn("two_field_grid(meal_dd, qty, viewport_width=dialog_width)", DIET_CONTROLLER_SOURCE)
        self.assertIn("two_field_grid(search, food_dd, viewport_width=dialog_width)", DIET_CONTROLLER_SOURCE)

    def test_add_diet_shortcuts_are_first_and_stay_attached_to_their_tabs(self):
        dialog_start = DIET_CONTROLLER_SOURCE.index('dlg = full_form_sheet(\n            "添加饮食"')
        dialog_end = DIET_CONTROLLER_SOURCE.index("\n        open_control(dlg)", dialog_start)
        dialog_source = DIET_CONTROLLER_SOURCE[dialog_start:dialog_end]

        shortcut_panel = dialog_source.index("diet_shortcut_panel(shortcut_tabs, shortcut_list)")
        meal_and_quantity = dialog_source.index("two_field_grid(meal_dd, qty")
        search_and_food = dialog_source.index("two_field_grid(search, food_dd")

        self.assertLess(shortcut_panel, meal_and_quantity)
        self.assertLess(meal_and_quantity, search_and_food)

    def test_supplements_exist_only_on_recovery_surface(self):
        for visible_text in ('"补剂库"', '"新增补剂"', '"今日补剂'):
            self.assertNotIn(visible_text, DIET_CONTROLLER_SOURCE)
            self.assertIn(visible_text, RECOVERY_CONTROLLER_SOURCE)
        self.assertIn("PersistedSupplementList", DIET_CONTROLLER_SOURCE)

    def test_shared_supplement_list_persists_recovery_mutations_without_main_wiring(self):
        snapshots = []
        supplements = PersistedSupplementList([], lambda values: snapshots.append([dict(item) for item in values]))

        supplements.append({"name": "肌酸", "default_amount": "5", "unit": "g"})
        supplements[0] = {"name": "肌酸", "default_amount": "3", "unit": "g"}
        supplements.pop()

        self.assertEqual(snapshots[0][0]["default_amount"], "5")
        self.assertEqual(snapshots[1][0]["default_amount"], "3")
        self.assertEqual(snapshots[2], [])

    def test_iqoo_430x860_today_layout_constructs_with_equal_peer_spacing(self):
        meals = ("早餐", "午餐", "晚餐", "练前", "练后", "偷吃")
        model = TodayDashboardModel(
            kcal=1800, kcal_target=2200, day_type="中碳日",
            macros={"carb": 180, "protein": 130, "fat": 55},
            targets={"carb_min": 180, "carb_max": 220, "protein_min": 120, "protein_max": 150, "fat_min": 50, "fat_max": 65},
            training_title="开始今天的训练", training_subtitle="动作、组数和计时都在训练页完成",
            training_icon=ft.Icons.FITNESS_CENTER, training_clock_active=False,
            meal_counts={meal: 0 for meal in meals}, water_ml=1250, supplement_count=2, sleep_text="7小时30分",
        )
        actions = TodayDashboardActions(lambda event: None, lambda meal: None, lambda event: None)
        dashboard = build_today_dashboard(model, actions, meals, bar_width=300)
        toolbar = build_date_toolbar("2026年07月22日", *(lambda event: None for _ in range(5)))
        page_content = ft.Column([*dashboard.control.controls, toolbar], spacing=TODAY_SECTION_SPACING, width=430, height=860)

        meals_card = dashboard.control.controls[2]
        self.assertEqual(page_content.spacing, 8)
        self.assertEqual(page_content.width, 430)
        self.assertEqual(page_content.height, 860)
        self.assertEqual(len(meals_card.content.controls[1].controls), 3)
        self.assertEqual(len(meals_card.content.controls[2].controls), 3)
        self.assertTrue(all(tile.height == 66 for row in meals_card.content.controls[1:3] for tile in row.controls))
        self.assertEqual(dashboard.control.controls[2].margin.bottom, 0)
        self.assertEqual(dashboard.control.controls[3].margin.bottom, 0)


if __name__ == "__main__":
    unittest.main()

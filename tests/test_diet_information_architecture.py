import unittest

from diet_service import (
    DIET_VIEWS,
    FOOD_LIBRARY_VIEW,
    ME_PAGE_BLOCKED_SUPPLEMENT_ACTIONS,
    SUPPLEMENT_LIBRARY_VIEW,
    TODAY_DIET_VIEW,
    DietViewState,
    diet_route_for_view,
    me_page_allows_action,
    normalize_diet_view,
    recovery_exposes_only_today_supplements,
    select_diet_view,
)
from diet_views import (
    DIET_INPUT_LABEL_HEIGHT,
    DIET_TAB_HEIGHT,
    DietShellRenderers,
    aligned_input_row,
    build_diet_shell,
    diet_tabs,
    fixed_labeled_input,
)


class DietInformationArchitectureTests(unittest.TestCase):
    def test_diet_subviews_are_mutually_exclusive(self):
        state = select_diet_view(DietViewState(), "supplements")

        self.assertEqual(state.active_view, SUPPLEMENT_LIBRARY_VIEW)
        self.assertEqual(
            state.visibility(),
            {
                TODAY_DIET_VIEW: False,
                FOOD_LIBRARY_VIEW: False,
                SUPPLEMENT_LIBRARY_VIEW: True,
            },
        )

    def test_legacy_routes_map_to_new_diet_shell_views(self):
        self.assertEqual(normalize_diet_view("diet"), TODAY_DIET_VIEW)
        self.assertEqual(normalize_diet_view("foods"), FOOD_LIBRARY_VIEW)
        self.assertEqual(normalize_diet_view("supplements"), SUPPLEMENT_LIBRARY_VIEW)
        self.assertEqual(normalize_diet_view("unknown"), TODAY_DIET_VIEW)

        self.assertEqual(diet_route_for_view(TODAY_DIET_VIEW), "diet")
        self.assertEqual(diet_route_for_view(FOOD_LIBRARY_VIEW), "foods")
        self.assertEqual(diet_route_for_view(SUPPLEMENT_LIBRARY_VIEW), "supplements")

    def test_recovery_page_contract_only_exposes_today_supplements(self):
        self.assertTrue(recovery_exposes_only_today_supplements(("today_supplements",)))
        self.assertFalse(recovery_exposes_only_today_supplements(("today_supplements", "supplement_library")))

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
            supplement_library=lambda: calls.append("supplements") or "supplements-panel",
        )

        shell = build_diet_shell(DietViewState(SUPPLEMENT_LIBRARY_VIEW), renderers, lambda view: None)

        self.assertEqual(calls, ["supplements"])
        self.assertEqual(shell.controls[1], "supplements-panel")

    def test_fixed_labeled_input_uses_external_fixed_label_not_floating_label(self):
        field = object()
        control = fixed_labeled_input("数量", field, expand=True)

        self.assertEqual(control.controls[0].height, DIET_INPUT_LABEL_HEIGHT)
        self.assertEqual(control.controls[0].content.value, "数量")
        self.assertEqual(control.controls[0].content.max_lines, 1)
        self.assertFalse(hasattr(field, "label"))

    def test_parallel_input_rows_are_top_aligned(self):
        row = aligned_input_row(["left", "right"])

        self.assertEqual(row.vertical_alignment, "start")
        self.assertEqual(row.spacing, 8)


if __name__ == "__main__":
    unittest.main()

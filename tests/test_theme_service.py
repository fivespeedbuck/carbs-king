import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import flet as ft

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from profile_theme_views import build_theme_panel  # noqa: E402
from theme_service import DEFAULT_THEME, THEME_OPTIONS, apply_theme, normalize_theme  # noqa: E402


class ThemeServiceTests(unittest.TestCase):
    def test_theme_values_are_limited_to_the_four_manual_choices(self):
        self.assertEqual(tuple(THEME_OPTIONS), ("green", "purple", "blue", "yellow"))
        self.assertEqual(normalize_theme("PURPLE"), "purple")
        self.assertEqual(normalize_theme("not-a-theme"), DEFAULT_THEME)

    def test_apply_theme_installs_the_selected_palette_without_losing_font(self):
        page = SimpleNamespace(theme=ft.Theme(font_family="Microsoft YaHei"))

        selected = apply_theme(page, "blue")

        self.assertEqual(selected, "blue")
        self.assertEqual(page.theme.color_scheme.primary, THEME_OPTIONS["blue"]["primary"])
        self.assertEqual(page.theme.color_scheme.primary_container, THEME_OPTIONS["blue"]["soft"])
        self.assertEqual(page.theme.font_family, "Microsoft YaHei")

    def test_theme_panel_contains_only_title_and_four_clickable_swatches(self):
        panel = build_theme_panel("green", lambda value: None)
        texts = []
        clickable = []

        def walk(control):
            if control is None:
                return
            if isinstance(control, ft.Text):
                texts.append(control.value)
            if getattr(control, "on_click", None) is not None:
                clickable.append(control)
            content = getattr(control, "content", None)
            if content is not None and content is not control:
                walk(content)
            for child in getattr(control, "controls", []) or []:
                walk(child)

        walk(panel)

        self.assertEqual(texts, ["主题色"])
        self.assertEqual(len(clickable), 4)


if __name__ == "__main__":
    unittest.main()

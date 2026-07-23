import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PRESENTATION_MODULES = (
    "form_views.py",
    "analytics_page.py",
    "analytics_trend_views.py",
    "analytics_weekly_review_views.py",
    "analytics_calendar_views.py",
    "analytics_summary_views.py",
    "analytics_ui.py",
    "data_record_controller.py",
    "navigation_views.py",
    "profile_views.py",
    "profile_details_views.py",
    "profile_macro_views.py",
    "profile_backup_views.py",
    "today_views.py",
    "training_views.py",
    "training_plan_views.py",
    "training_picker_views.py",
    "training_summary_views.py",
    "ui_components.py",
)


class ViewModuleBoundaryTests(unittest.TestCase):
    def test_presentation_modules_do_not_import_main_or_storage_services(self):
        forbidden = {"main", "json", "pathlib", "analytics_service", "training_service"}
        for name in PRESENTATION_MODULES:
            tree = ast.parse((SRC / name).read_text(encoding="utf-8-sig"), filename=name)
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(imported & forbidden, f"{name} crossed its presentation boundary")

    def test_view_modules_expose_small_public_entry_points(self):
        expected = {
            "today_views.py": {"build_date_toolbar", "build_today_dashboard"},
            "training_views.py": {"build_active_training"},
            "profile_views.py": {"build_achievement_wall"},
            "form_views.py": {"build_dialog", "build_full_form_sheet"},
            "navigation_views.py": {"build_bottom_navigation"},
        }
        for name, functions in expected.items():
            tree = ast.parse((SRC / name).read_text(encoding="utf-8-sig"), filename=name)
            public_functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
            self.assertTrue(functions <= public_functions, name)

    def test_main_delegates_extracted_surfaces(self):
        source = (SRC / "main.py").read_text(encoding="utf-8-sig")
        for call in (
            "TodayController(",
            "create_training_controller(",
            "create_profile_controller(",
            "create_data_record_controller(",
            "build_bottom_navigation(",
        ):
            self.assertIn(call, source)

    def test_analytics_model_is_framework_free_and_facade_has_no_implementation(self):
        model = ast.parse((SRC / "analytics_model.py").read_text(encoding="utf-8-sig"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(model)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".")[0]
            for node in ast.walk(model)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertNotIn("flet", imports)

        facade = ast.parse((SRC / "analytics_views.py").read_text(encoding="utf-8-sig"))
        implementations = [
            node for node in facade.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        self.assertEqual(implementations, [])

    def test_main_contains_no_feature_forms_or_direct_json_persistence(self):
        source = (SRC / "main.py").read_text(encoding="utf-8-sig")
        for forbidden in (
            "def record_payload(",
            "def render_today_dashboard(",
            "def render_training_workspace(",
            "def render_me(",
            "def render_data_page(",
            "save_json(",
            "load_json(",
        ):
            self.assertNotIn(forbidden, source)

    def test_services_are_flet_free_and_controllers_never_import_main(self):
        service_files = (
            "analytics_service.py",
            "backup_service.py",
            "diet_service.py",
            "nutrition_service.py",
            "training_clock_service.py",
            "training_experience_service.py",
            "training_service.py",
        )
        controller_files = tuple(path.name for path in SRC.glob("*_controller.py"))
        for name in service_files + controller_files:
            tree = ast.parse((SRC / name).read_text(encoding="utf-8-sig"), filename=name)
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            if name in service_files:
                self.assertNotIn("flet", imported, name)
            else:
                self.assertNotIn("main", imported, name)

    def test_daily_record_controller_is_the_only_feature_record_writer(self):
        for path in SRC.glob("*_controller.py"):
            if path.name == "daily_record_controller.py":
                continue
            source = path.read_text(encoding="utf-8-sig")
            self.assertNotIn("repositories.records.save(", source, path.name)


if __name__ == "__main__":
    unittest.main()

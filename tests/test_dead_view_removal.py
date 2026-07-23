import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeadViewRemovalTests(unittest.TestCase):
    def test_replaced_legacy_views_are_not_left_in_main(self):
        tree = ast.parse((ROOT / "src" / "main.py").read_text(encoding="utf-8-sig"))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        nested = {node.name for node in main.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertTrue({
            "render_profile", "render_history", "open_record_detail", "delete_history_record",
            "get_previous_body_info", "refresh_soft",
        }.isdisjoint(nested))

    def test_routes_delegate_to_one_feature_implementation(self):
        source = (ROOT / "src" / "main.py").read_text(encoding="utf-8-sig")
        for delegated in (
            "diet_controller.render_page()",
            "recovery_controller.render_page()",
            "training_controller.render_page()",
            "data_record_controller.render_page()",
            "profile_controller.render_page()",
        ):
            self.assertEqual(source.count(delegated), 1)


if __name__ == "__main__":
    unittest.main()

import ast
import dataclasses
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diet_controller import DietControllerDependencies  # noqa: E402
from profile_controller import ProfileControllerDependencies  # noqa: E402


class MainDependencyWiringTests(unittest.TestCase):
    def test_controller_dependency_keywords_match_their_dataclasses(self):
        tree = ast.parse((ROOT / "src" / "main.py").read_text(encoding="utf-8-sig"))
        contracts = {
            "DietControllerDependencies": DietControllerDependencies,
            "ProfileControllerDependencies": ProfileControllerDependencies,
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            dependency_type = contracts.get(node.func.id)
            if dependency_type is None:
                continue
            expected = {field.name for field in dataclasses.fields(dependency_type)}
            actual = {keyword.arg for keyword in node.keywords if keyword.arg}
            self.assertEqual(actual, expected, node.func.id)


if __name__ == "__main__":
    unittest.main()

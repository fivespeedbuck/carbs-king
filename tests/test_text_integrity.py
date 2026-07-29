import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class UserVisibleTextIntegrityTests(unittest.TestCase):
    def test_python_sources_use_utf8_without_bom(self):
        with_bom = [
            str(path.relative_to(ROOT))
            for path in sorted(SRC.rglob("*.py"))
            if path.read_bytes().startswith(b"\xef\xbb\xbf")
        ]
        self.assertEqual(with_bom, [])

    def test_python_string_literals_have_no_ascii_question_placeholders_or_mojibake(self):
        suspicious = []
        mojibake_fragments = ("宸插", "畬鎴", "缁?", "锛", "銆", "鐨勬")
        for path in sorted(SRC.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                value = node.value
                if "?" in value or "�" in value or any(part in value for part in mojibake_fragments):
                    suspicious.append(f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)} {value!r}")
        self.assertEqual(suspicious, [])


if __name__ == "__main__":
    unittest.main()

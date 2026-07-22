import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"


class StorageIsolationTests(unittest.TestCase):
    def test_explicit_data_dir_does_not_import_legacy_data(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            isolated_dir = root / "isolated"
            fake_home = root / "home"
            fake_appdata = root / "appdata"
            legacy_dirs = [
                fake_home / ".carb_cycle_recorder_mobile",
                fake_appdata / "CarbCycleRecorderMobile",
            ]
            for index, legacy_dir in enumerate(legacy_dirs):
                legacy_dir.mkdir(parents=True)
                (legacy_dir / "daily_records.json").write_text(
                    f'{{"legacy_marker": {index}}}', encoding="utf-8"
                )

            env = os.environ.copy()
            env.update({
                "CARBS_KING_DATA_DIR": str(isolated_dir),
                "APPDATA": str(fake_appdata),
                "HOME": str(fake_home),
                "USERPROFILE": str(fake_home),
                "PYTHONPATH": str(SRC_DIR),
            })
            subprocess.run(
                [sys.executable, "-c", "import main"],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertTrue(isolated_dir.is_dir())
            self.assertEqual(list(isolated_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

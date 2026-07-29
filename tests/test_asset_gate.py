import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from asset_gate import AssetGateError, compare_trees, verify_apk, verify_tree  # noqa: E402


class AssetGateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "assets"
        self.source.mkdir()
        (self.source / "exercise.gif").write_bytes(b"GIF89a" + b"gif-data")
        (self.source / "sound.mp3").write_bytes(b"ID3" + b"audio-data")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_source_rejects_lfs_pointer_disguised_as_gif(self):
        (self.source / "exercise.gif").write_bytes(
            b"version https://git-lfs.github.com/spec/v1\n"
        )

        with self.assertRaisesRegex(AssetGateError, "Git LFS pointer"):
            verify_tree(self.source)

    def test_mirror_requires_matching_paths_sizes_and_hashes(self):
        destination = self.root / "src-assets"
        destination.mkdir()
        (destination / "exercise.gif").write_bytes(b"GIF89a" + b"gif-data")
        (destination / "sound.mp3").write_bytes(b"ID3" + b"audio-data")

        result = compare_trees(self.source, destination)
        self.assertTrue(result["hashes_match"])

        (destination / "sound.mp3").write_bytes(b"ID3" + b"wrong-data")
        with self.assertRaisesRegex(AssetGateError, "hash mismatch"):
            compare_trees(self.source, destination)

    def test_apk_gate_checks_inner_app_zip_bytes(self):
        inner_bytes = io.BytesIO()
        with zipfile.ZipFile(inner_bytes, "w") as inner:
            for path in self.source.iterdir():
                inner.writestr(f"assets/{path.name}", path.read_bytes())
        apk = self.root / "app.apk"
        with zipfile.ZipFile(apk, "w") as outer:
            outer.writestr("assets/flutter_assets/app/app.zip", inner_bytes.getvalue())

        result = verify_apk(self.source, apk)

        self.assertEqual(result["packaged_files"], 2)
        self.assertEqual(result["media"], {".gif": 1, ".mp3": 1})


if __name__ == "__main__":
    unittest.main()

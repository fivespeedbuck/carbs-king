import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apk_update_download import ApkUpdateError, download_apk  # noqa: E402
from profile_update_views import build_update_panel  # noqa: E402


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int) -> bytes:
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


class ApkUpdateDownloadTests(unittest.TestCase):
    def test_download_streams_progress_and_verifies_size_and_digest(self):
        payload = b"apk-bytes" * 1000
        progress = []
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "carbs_king.apk"
            artifact = download_apk(
                "https://example.invalid/carbs_king.apk",
                target,
                expected_size=len(payload),
                expected_sha256=hashlib.sha256(payload).hexdigest(),
                opener=lambda _request, timeout: _Response(payload),
                on_progress=lambda current, total: progress.append((current, total)),
            )

            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(artifact.path, target)
            self.assertEqual(artifact.bytes_downloaded, len(payload))
            self.assertEqual(progress[-1], (len(payload), len(payload)))

    def test_download_rejects_tampered_file_and_leaves_no_partial_apk(self):
        payload = b"not-the-advertised-apk"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "carbs_king.apk"
            with self.assertRaisesRegex(ApkUpdateError, "哈希"):
                download_apk(
                    "https://example.invalid/carbs_king.apk",
                    target,
                    expected_sha256="0" * 64,
                    opener=lambda _request, timeout: _Response(payload),
                )
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".apk.part").exists())

    def test_update_panel_exposes_in_app_progress_and_manual_install_action(self):
        downloading = build_update_panel(
            current_version="1.2.3", current_build=78, status="downloading",
            latest={"build": 79, "apk_url": "https://example.invalid/app.apk"},
            on_check=lambda _event: None, on_download=lambda _event: None,
            downloaded_bytes=25, total_bytes=100,
        )
        self.assertIn("正在下载 0.0 MB / 0.0 MB（25%）", downloading.content.controls[2].value)
        self.assertEqual(downloading.content.controls[3].value, 0.25)

        downloaded = build_update_panel(
            current_version="1.2.3", current_build=78, status="downloaded",
            latest={"build": 79, "apk_url": "https://example.invalid/app.apk"},
            on_check=lambda _event: None, on_download=lambda _event: None,
            on_install=lambda _event: None,
        )
        self.assertEqual(downloaded.content.controls[-1].controls[-1].content.controls[-1].value, "打开安装界面")


if __name__ == "__main__":
    unittest.main()

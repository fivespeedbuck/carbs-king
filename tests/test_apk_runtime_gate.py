import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from apk_runtime_gate import ApkRuntimeGateError, verify_outputs, verify_sources  # noqa: E402


class ApkRuntimeGateTests(unittest.TestCase):
    def test_outputs_require_manifest_resource_and_dex_contracts(self):
        manifest = " ".join((
            "android.permission.POST_NOTIFICATIONS",
            "android.permission.VIBRATE",
            "android.permission.WAKE_LOCK",
            "android.permission.USE_EXACT_ALARM",
            "android.permission.SYSTEM_ALERT_WINDOW",
            "android.permission.FOREGROUND_SERVICE",
            "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
            "android.permission.REQUEST_INSTALL_PACKAGES",
            "com.chenyang.carbs_king.restalarm.RestAlarmReceiver",
            "com.chenyang.carbs_king.restalarm.RestOverlayService",
            "com.chenyang.carbs_king.REST_ALARM",
            "androidx.core.content.FileProvider",
        ))
        result = verify_outputs(
            manifest,
            "resource raw/rest_coin",
            "RestAlarmReceiver RestOverlayService CarbsKingRestAlarmPlugin",
        )
        self.assertEqual(result["raw_sound"], "raw/rest_coin")

        with self.assertRaisesRegex(ApkRuntimeGateError, "raw/rest_coin"):
            verify_outputs(manifest, "no raw sound", "RestAlarmReceiver RestOverlayService CarbsKingRestAlarmPlugin")

    def test_sources_require_static_resource_reference_matching_v3_channel_and_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receiver = root / "android/rest_alarm_plugin/android/src/main/kotlin/com/chenyang/carbs_king/restalarm/RestAlarmReceiver.kt"
            overlay = root / "android/rest_alarm_plugin/android/src/main/kotlin/com/chenyang/carbs_king/restalarm/RestOverlayService.kt"
            adapter = root / "src/rest_notification.py"
            installer = root / "src/apk_update_download.py"
            native = root / "android/rest_alarm_plugin/android/src/main/res/raw/rest_coin.mp3"
            flet = root / "assets/rest_coin.mp3"
            manifest = root / "android/rest_alarm_plugin/android/src/main/AndroidManifest.xml"
            for path in (receiver, overlay, adapter, installer, native, flet, manifest):
                path.parent.mkdir(parents=True, exist_ok=True)
            receiver.write_text("R.raw.rest_coin rest_cycle_native_alerts_v1", encoding="utf-8")
            overlay.write_text("class RestOverlayService", encoding="utf-8")
            adapter.write_text("rest_cycle_alerts_v3", encoding="utf-8")
            installer.write_text('FileProvider.getUriForFile f"{package_name}.provider"', encoding="utf-8")
            manifest.write_text(
                "REQUEST_INSTALL_PACKAGES SYSTEM_ALERT_WINDOW "
                "FOREGROUND_SERVICE_SPECIAL_USE .RestOverlayService",
                encoding="utf-8",
            )
            native.write_bytes(b"sound")
            flet.write_bytes(b"sound")

            result = verify_sources(root)

            self.assertEqual(result["foreground_channel_id"], "rest_cycle_alerts_v3")
            self.assertEqual(result["native_channel_id"], "rest_cycle_native_alerts_v1")


if __name__ == "__main__":
    unittest.main()

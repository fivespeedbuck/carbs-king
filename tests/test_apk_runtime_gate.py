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
            "com.chenyang.carbs_king.restalarm.RestAlarmReceiver",
            "com.chenyang.carbs_king.REST_ALARM",
        ))
        result = verify_outputs(
            manifest,
            "resource raw/rest_coin",
            "RestAlarmReceiver CarbsKingRestAlarmPlugin",
        )
        self.assertEqual(result["raw_sound"], "raw/rest_coin")

        with self.assertRaisesRegex(ApkRuntimeGateError, "raw/rest_coin"):
            verify_outputs(manifest, "no raw sound", "RestAlarmReceiver CarbsKingRestAlarmPlugin")

    def test_sources_require_static_resource_reference_matching_v3_channel_and_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receiver = root / "android/rest_alarm_plugin/android/src/main/kotlin/com/chenyang/carbs_king/restalarm/RestAlarmReceiver.kt"
            adapter = root / "src/rest_notification.py"
            native = root / "android/rest_alarm_plugin/android/src/main/res/raw/rest_coin.mp3"
            flet = root / "assets/rest_coin.mp3"
            for path in (receiver, adapter, native, flet):
                path.parent.mkdir(parents=True, exist_ok=True)
            receiver.write_text("R.raw.rest_coin rest_cycle_alerts_v3", encoding="utf-8")
            adapter.write_text("rest_cycle_alerts_v3", encoding="utf-8")
            native.write_bytes(b"sound")
            flet.write_bytes(b"sound")

            result = verify_sources(root)

            self.assertEqual(result["channel_id"], "rest_cycle_alerts_v3")


if __name__ == "__main__":
    unittest.main()

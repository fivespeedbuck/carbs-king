"""Verify Android runtime pieces that the inner Flet asset gate cannot see."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RECEIVER_CLASS = "com.chenyang.carbs_king.restalarm.RestAlarmReceiver"
PLUGIN_CLASS = "com.chenyang.carbs_king.restalarm.CarbsKingRestAlarmPlugin"
UPDATE_PROVIDER_CLASS = "androidx.core.content.FileProvider"
ACTION = "com.chenyang.carbs_king.REST_ALARM"
CHANNEL_ID = "rest_cycle_alerts_v3"
PERMISSIONS = (
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.VIBRATE",
    "android.permission.WAKE_LOCK",
    "android.permission.USE_EXACT_ALARM",
    "android.permission.REQUEST_INSTALL_PACKAGES",
)


class ApkRuntimeGateError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _find_packaged_blob(apk: Path, expected: bytes) -> str:
    expected_hash = hashlib.sha256(expected).digest()
    with zipfile.ZipFile(apk) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.file_size != len(expected):
                continue
            if hashlib.sha256(archive.read(info)).digest() == expected_hash:
                return info.filename
    raise ApkRuntimeGateError("final APK does not contain the native rest sound bytes")


def verify_outputs(manifest: str, resources: str, dex: str) -> dict[str, object]:
    missing_manifest = [
        token
        for token in (*PERMISSIONS, RECEIVER_CLASS, ACTION, UPDATE_PROVIDER_CLASS)
        if token not in manifest
    ]
    if missing_manifest:
        raise ApkRuntimeGateError(
            "manifest is missing: " + ", ".join(missing_manifest)
        )
    if not re.search(r"raw[/\\:]rest_coin|raw\s+rest_coin", resources):
        raise ApkRuntimeGateError("final APK resource table is missing raw/rest_coin")
    missing_dex = [token for token in ("RestAlarmReceiver", "CarbsKingRestAlarmPlugin") if token not in dex]
    if missing_dex:
        raise ApkRuntimeGateError("DEX is missing: " + ", ".join(missing_dex))
    return {
        "permissions": list(PERMISSIONS),
        "receiver": RECEIVER_CLASS,
        "action": ACTION,
        "raw_sound": "raw/rest_coin",
        "dex_classes": [RECEIVER_CLASS, PLUGIN_CLASS],
    }


def verify_sources(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    receiver = repo_root / "android/rest_alarm_plugin/android/src/main/kotlin/com/chenyang/carbs_king/restalarm/RestAlarmReceiver.kt"
    python_adapter = repo_root / "src/rest_notification.py"
    update_installer = repo_root / "src/apk_update_download.py"
    native_sound = repo_root / "android/rest_alarm_plugin/android/src/main/res/raw/rest_coin.mp3"
    flet_sound = repo_root / "assets/rest_coin.mp3"
    update_manifest = repo_root / "android/rest_alarm_plugin/android/src/main/AndroidManifest.xml"
    for path in (receiver, python_adapter, update_installer, native_sound, flet_sound, update_manifest):
        if not path.is_file():
            raise ApkRuntimeGateError(f"required source is missing: {path}")
    receiver_text = receiver.read_text(encoding="utf-8")
    adapter_text = python_adapter.read_text(encoding="utf-8")
    if "R.raw.rest_coin" not in receiver_text:
        raise ApkRuntimeGateError("Kotlin receiver does not statically retain R.raw.rest_coin")
    if CHANNEL_ID not in receiver_text or CHANNEL_ID not in adapter_text:
        raise ApkRuntimeGateError(f"Kotlin and Python must both use {CHANNEL_ID}")
    if native_sound.read_bytes() != flet_sound.read_bytes():
        raise ApkRuntimeGateError("native and Flet rest sounds differ")
    manifest_text = update_manifest.read_text(encoding="utf-8")
    installer_text = update_installer.read_text(encoding="utf-8")
    if "REQUEST_INSTALL_PACKAGES" not in manifest_text:
        raise ApkRuntimeGateError("Android APK installer permission is missing")
    if "FileProvider.getUriForFile" not in installer_text or 'f"{package_name}.provider"' not in installer_text:
        raise ApkRuntimeGateError("APK installer does not reuse Flet's content URI provider")
    return {"channel_id": CHANNEL_ID, "sound_sha256": _sha256(native_sound)}


def _sdk_root() -> Path:
    candidates = [
        os.getenv("ANDROID_SDK_ROOT"),
        os.getenv("ANDROID_HOME"),
        str(Path(os.getenv("LOCALAPPDATA", "")) / "Android" / "Sdk"),
    ]
    for value in candidates:
        if value and Path(value).is_dir():
            return Path(value)
    raise ApkRuntimeGateError("Android SDK was not found")


def _version_key(path: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", path.name))


def _tools() -> tuple[Path, Path]:
    sdk = _sdk_root()
    build_tools = sorted(
        (path for path in (sdk / "build-tools").iterdir() if path.is_dir()),
        key=_version_key,
        reverse=True,
    )
    for directory in build_tools:
        for name in ("aapt2.exe", "aapt.exe", "aapt2", "aapt"):
            candidate = directory / name
            if candidate.is_file():
                aapt = candidate
                break
        else:
            continue
        break
    else:
        raise ApkRuntimeGateError("aapt/aapt2 was not found")
    analyzer_names = ("apkanalyzer.bat", "apkanalyzer")
    analyzer = next(
        (
            sdk / "cmdline-tools" / "latest" / "bin" / name
            for name in analyzer_names
            if (sdk / "cmdline-tools" / "latest" / "bin" / name).is_file()
        ),
        None,
    )
    if analyzer is None:
        raise ApkRuntimeGateError("apkanalyzer was not found")
    return aapt, analyzer


def _run(command: list[str]) -> str:
    actual = command
    if os.name == "nt" and command[0].lower().endswith(".bat"):
        actual = ["cmd.exe", "/d", "/c", *command]
    completed = subprocess.run(actual, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return completed.stdout


def verify_apk(apk: Path, repo_root: Path = REPO_ROOT) -> dict[str, object]:
    if not apk.is_file():
        raise ApkRuntimeGateError(f"APK does not exist: {apk}")
    aapt, analyzer = _tools()
    if aapt.name.lower().startswith("aapt2"):
        manifest_cmd = [str(aapt), "dump", "xmltree", str(apk), "--file", "AndroidManifest.xml"]
    else:
        manifest_cmd = [str(aapt), "dump", "xmltree", str(apk), "AndroidManifest.xml"]
    manifest = _run(manifest_cmd)
    resources = _run([str(aapt), "dump", "resources", str(apk)])
    dex = _run([str(analyzer), "dex", "packages", "--defined-only", str(apk)])
    result = verify_outputs(manifest, resources, dex)
    result["source"] = verify_sources(repo_root)
    native_sound = repo_root / "android/rest_alarm_plugin/android/src/main/res/raw/rest_coin.mp3"
    result["native_sound_entry"] = _find_packaged_blob(apk, native_sound.read_bytes())
    shrink_report = repo_root / "build/flutter/build/app/outputs/mapping/release/resources.txt"
    if shrink_report.is_file():
        report = shrink_report.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"raw/rest_coin\s*:\s*reachable=(true|false)", report)
        if not match or match.group(1) != "true":
            raise ApkRuntimeGateError("resource shrinker did not retain raw/rest_coin")
        result["shrinker_reachable"] = True
    result.update({"apk": str(apk), "apk_bytes": apk.stat().st_size, "sha256": _sha256(apk)})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_apk(args.apk.resolve())
    except (ApkRuntimeGateError, OSError, subprocess.CalledProcessError) as exc:
        print(f"APK RUNTIME GATE FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

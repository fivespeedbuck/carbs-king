"""Download a verified APK in-app and hand it to Android's installer."""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


CHUNK_SIZE = 256 * 1024
APK_MIME_TYPE = "application/vnd.android.package-archive"


class ApkUpdateError(RuntimeError):
    """The update file could not be safely downloaded or opened."""


@dataclass(frozen=True)
class DownloadedApk:
    path: Path
    bytes_downloaded: int
    total_bytes: int
    sha256: str


def _safe_filename(value: str) -> str:
    name = Path(str(value or "carbs_king.apk")).name
    return name if name.casefold().endswith(".apk") else "carbs_king.apk"


def default_apk_destination(apk_name: str) -> Path:
    """Return app-private external downloads on Android, temp elsewhere."""
    filename = _safe_filename(apk_name)
    activity_class = os.getenv("MAIN_ACTIVITY_HOST_CLASS_NAME")
    if activity_class:
        try:
            from jnius import autoclass  # type: ignore

            activity = autoclass(activity_class).mActivity
            Environment = autoclass("android.os.Environment")
            directory = activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            if directory is not None:
                return Path(str(directory.getAbsolutePath())) / filename
        except Exception:
            # The caller reports an installer limitation after the verified
            # local download; source and desktop tests intentionally use temp.
            pass
    return Path(tempfile.gettempdir()) / "carbs-king-updates" / filename


def download_apk(
    url: str,
    destination: Path,
    *,
    expected_size: int = 0,
    expected_sha256: str = "",
    opener: Callable[..., Any] = urllib.request.urlopen,
    on_progress: Callable[[int, int], None] | None = None,
) -> DownloadedApk:
    """Stream an APK to a temporary file, verify it, then atomically publish it."""
    if not str(url or "").startswith(("https://", "http://")):
        raise ApkUpdateError("安装包下载地址无效")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(str(url), headers={"Accept": APK_MIME_TYPE})
    downloaded = 0
    hasher = hashlib.sha256()
    total = max(0, int(expected_size or 0))
    try:
        with opener(request, timeout=30) as response, temporary.open("wb") as output:
            header_total = getattr(response, "headers", {}).get("Content-Length")
            if not total and header_total:
                try:
                    total = int(header_total)
                except (TypeError, ValueError):
                    pass
            while chunk := response.read(CHUNK_SIZE):
                output.write(chunk)
                hasher.update(chunk)
                downloaded += len(chunk)
                if on_progress is not None:
                    on_progress(downloaded, total)
        if expected_size and downloaded != int(expected_size):
            raise ApkUpdateError(f"下载大小不一致：收到 {downloaded} 字节")
        digest = hasher.hexdigest().upper()
        expected = str(expected_sha256 or "").replace("sha256:", "").upper()
        if expected and digest != expected:
            raise ApkUpdateError("下载校验失败：APK 哈希不匹配")
        os.replace(temporary, destination)
        if on_progress is not None:
            on_progress(downloaded, total or downloaded)
        return DownloadedApk(destination, downloaded, total or downloaded, digest)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def open_android_installer(path: Path) -> str:
    """Open the system installer, or its required unknown-source permission page."""
    activity_class = os.getenv("MAIN_ACTIVITY_HOST_CLASS_NAME")
    if not activity_class:
        raise ApkUpdateError("仅 Android 安装包支持直接打开系统安装界面")
    if not Path(path).is_file():
        raise ApkUpdateError("下载的安装包不存在，请重新下载")
    try:
        from jnius import autoclass  # type: ignore

        activity = autoclass(activity_class).mActivity
        BuildVersion = autoclass("android.os.Build$VERSION")
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        File = autoclass("java.io.File")
        FileProvider = autoclass("androidx.core.content.FileProvider")
        package_name = str(activity.getPackageName())
        sdk_int = int(BuildVersion.SDK_INT)
        package_manager = activity.getPackageManager()
        if sdk_int >= 26 and not bool(package_manager.canRequestPackageInstalls()):
            Settings = autoclass("android.provider.Settings")
            permission_intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES)
            permission_intent.setData(Uri.parse(f"package:{package_name}"))
            activity.startActivity(permission_intent)
            return "permission"
        uri = FileProvider.getUriForFile(
            activity,
            # Flet's generated Android host already owns this provider and its
            # paths cover app-private external downloads. Reuse it so manifest
            # merging stays compatible with the generated host.
            f"{package_name}.provider",
            File(str(Path(path).resolve())),
        )
        install_intent = Intent(Intent.ACTION_VIEW)
        install_intent.setDataAndType(uri, APK_MIME_TYPE)
        install_intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        activity.startActivity(install_intent)
        return "installer"
    except ApkUpdateError:
        raise
    except Exception as exc:
        raise ApkUpdateError(f"无法打开系统安装界面：{exc}") from exc


__all__ = [
    "APK_MIME_TYPE",
    "ApkUpdateError",
    "DownloadedApk",
    "default_apk_destination",
    "download_apk",
    "open_android_installer",
]

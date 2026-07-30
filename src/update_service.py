"""GitHub Release update metadata retrieval and comparison."""

from __future__ import annotations

import json
import re
import time
import urllib.request
from urllib.error import HTTPError, URLError
from collections.abc import Callable
from typing import Any

from app_version import BUILD_NUMBER, VERSION_NAME


REPOSITORY = "fivespeedbuck/carbs-king"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases/latest"
RELEASE_MANIFEST_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/update_manifest.json"
_CACHE_TTL_SECONDS = 900
_CACHE: dict[str, Any] = {"checked_at": 0.0, "release": None}


def parse_build_number(*values: Any) -> int | None:
    """Return the first explicit Build number from release metadata."""
    for value in values:
        match = re.search(r"\bBuild[-#：:\s]*(\d+)\b", str(value or ""), flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def parse_release(payload: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    apk = next(
        (
            item for item in assets
            if isinstance(item, dict) and str(item.get("name") or "").casefold().endswith(".apk")
        ),
        {},
    )
    build = parse_build_number(payload.get("name"), payload.get("body"), payload.get("tag_name"))
    digest = str(apk.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        digest = digest.split(":", 1)[1].upper()
    return {
        "tag": str(payload.get("tag_name") or ""),
        "title": str(payload.get("name") or payload.get("tag_name") or "最新版本"),
        "build": build,
        "page_url": str(payload.get("html_url") or RELEASES_URL),
        "apk_url": str(apk.get("browser_download_url") or ""),
        "apk_name": str(apk.get("name") or ""),
        "size": int(apk.get("size") or 0),
        "sha256": digest,
    }


def _read_json(opener: Callable[..., Any], url: str, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": f"carbs-king/{VERSION_NAME} Build {BUILD_NUMBER}",
        },
    )
    with opener(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("更新元数据格式无效")
    return payload


def fetch_latest_release(
    *,
    timeout: float = 5.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
    use_cache: bool = True,
) -> dict[str, Any]:
    now = time.monotonic()
    cached = _CACHE.get("release")
    if use_cache and isinstance(cached, dict) and now - float(_CACHE.get("checked_at") or 0) < _CACHE_TTL_SECONDS:
        return dict(cached)
    try:
        payload = _read_json(opener, LATEST_RELEASE_API, timeout=timeout)
        release = parse_release(payload)
    except (HTTPError, URLError, TimeoutError, ValueError):
        # Some mobile VPN exits are allowed to github.com but receive 403
        # from api.github.com. The public manifest is served by raw GitHub and
        # contains only the release fields the app needs, so update checks can
        # continue without embedding a GitHub token in the APK.
        manifest = _read_json(opener, RELEASE_MANIFEST_URL, timeout=timeout)
        release = parse_release(manifest)
    _CACHE["checked_at"] = now
    _CACHE["release"] = dict(release)
    return release


def update_available(release: dict[str, Any], current_build: int = BUILD_NUMBER) -> bool:
    latest_build = release.get("build")
    return isinstance(latest_build, int) and latest_build > int(current_build)


__all__ = [
    "LATEST_RELEASE_API",
    "RELEASE_MANIFEST_URL",
    "RELEASES_URL",
    "fetch_latest_release",
    "parse_build_number",
    "parse_release",
    "update_available",
]

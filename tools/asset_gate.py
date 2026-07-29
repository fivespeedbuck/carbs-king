"""Verify the canonical asset tree, build mirror, and packaged APK assets."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ASSETS = REPO_ROOT / "assets"
PACKAGE_ASSETS = REPO_ROOT / "src" / "assets"
APP_ZIP_PATH = "assets/flutter_assets/app/app.zip"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
GIF_HEADERS = {b"GIF87a", b"GIF89a"}
MEDIA_SUFFIXES = {".gif", ".jpg", ".jpeg", ".mp3", ".wav"}


class AssetGateError(RuntimeError):
    pass


def _files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        raise AssetGateError(f"asset directory does not exist: {root}")
    result = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }
    if not result:
        raise AssetGateError(f"asset directory is empty: {root}")
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_tree(root: Path) -> dict[str, object]:
    files = _files(root)
    counts: Counter[str] = Counter()
    total_bytes = 0
    pointers: list[str] = []
    bad_gifs: list[str] = []
    for relative, path in files.items():
        suffix = path.suffix.lower()
        counts[suffix or "<none>"] += 1
        total_bytes += path.stat().st_size
        with path.open("rb") as stream:
            prefix = stream.read(200)
        if prefix.startswith(LFS_POINTER_PREFIX):
            pointers.append(relative)
        if suffix == ".gif" and prefix[:6] not in GIF_HEADERS:
            bad_gifs.append(relative)

    if pointers:
        raise AssetGateError(
            f"found {len(pointers)} Git LFS pointer files; first: {pointers[0]}"
        )
    if bad_gifs:
        raise AssetGateError(
            f"found {len(bad_gifs)} GIF files with invalid headers; first: {bad_gifs[0]}"
        )
    if counts[".gif"] == 0:
        raise AssetGateError("no GIF assets were found")

    return {
        "path": str(root),
        "files": len(files),
        "bytes": total_bytes,
        "gif": counts[".gif"],
        "jpg": counts[".jpg"] + counts[".jpeg"],
        "mp3": counts[".mp3"],
        "wav": counts[".wav"],
    }


def verify_git_inventory(repo_root: Path = REPO_ROOT) -> dict[str, int]:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z", "--", "assets"],
        check=True,
        capture_output=True,
    )
    tracked = {
        item.decode("utf-8").replace("\\", "/")
        for item in completed.stdout.split(b"\0")
        if item
    }
    actual = {
        f"assets/{relative}"
        for relative in _files(repo_root / "assets")
    }
    missing = sorted(tracked - actual)
    untracked = sorted(actual - tracked)
    if missing or untracked:
        details = []
        if missing:
            details.append(f"missing tracked asset: {missing[0]}")
        if untracked:
            details.append(f"untracked asset: {untracked[0]}")
        raise AssetGateError("asset Git inventory mismatch: " + "; ".join(details))
    return {"tracked": len(tracked), "present": len(actual)}


def compare_trees(source: Path, destination: Path) -> dict[str, object]:
    source_stats = verify_tree(source)
    destination_stats = verify_tree(destination)
    source_files = _files(source)
    destination_files = _files(destination)
    if source_files.keys() != destination_files.keys():
        missing = sorted(source_files.keys() - destination_files.keys())
        extra = sorted(destination_files.keys() - source_files.keys())
        raise AssetGateError(
            "asset mirror path mismatch: "
            f"missing={missing[:1] or 'none'}, extra={extra[:1] or 'none'}"
        )
    for relative, source_path in source_files.items():
        destination_path = destination_files[relative]
        if source_path.stat().st_size != destination_path.stat().st_size:
            raise AssetGateError(f"asset mirror size mismatch: {relative}")
        if _sha256_file(source_path) != _sha256_file(destination_path):
            raise AssetGateError(f"asset mirror hash mismatch: {relative}")
    return {"source": source_stats, "destination": destination_stats, "hashes_match": True}


def verify_apk(source: Path, apk_path: Path) -> dict[str, object]:
    source_stats = verify_tree(source)
    source_files = _files(source)
    if not apk_path.is_file():
        raise AssetGateError(f"APK does not exist: {apk_path}")

    with zipfile.ZipFile(apk_path) as outer:
        if APP_ZIP_PATH not in outer.namelist():
            raise AssetGateError(f"APK does not contain {APP_ZIP_PATH}")
        app_zip_bytes = outer.read(APP_ZIP_PATH)

    with zipfile.ZipFile(io.BytesIO(app_zip_bytes)) as inner:
        packaged = {
            info.filename[len("assets/") :]: info
            for info in inner.infolist()
            if not info.is_dir() and info.filename.startswith("assets/")
        }
        expected = set(source_files)
        actual = set(packaged)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing or extra:
            raise AssetGateError(
                "packaged asset path mismatch: "
                f"missing={missing[:1] or 'none'}, extra={extra[:1] or 'none'}"
            )

        media_counts: Counter[str] = Counter()
        packaged_bytes = 0
        for relative, source_path in source_files.items():
            info = packaged[relative]
            source_size = source_path.stat().st_size
            if info.file_size != source_size:
                raise AssetGateError(f"packaged asset size mismatch: {relative}")
            blob = inner.read(info)
            if blob.startswith(LFS_POINTER_PREFIX):
                raise AssetGateError(f"packaged asset is an LFS pointer: {relative}")
            if source_path.suffix.lower() == ".gif" and blob[:6] not in GIF_HEADERS:
                raise AssetGateError(f"packaged GIF has an invalid header: {relative}")
            if hashlib.sha256(blob).hexdigest() != _sha256_file(source_path):
                raise AssetGateError(f"packaged asset hash mismatch: {relative}")
            packaged_bytes += len(blob)
            if source_path.suffix.lower() in MEDIA_SUFFIXES:
                media_counts[source_path.suffix.lower()] += 1

    return {
        "apk": str(apk_path),
        "apk_bytes": apk_path.stat().st_size,
        "app_zip_bytes": len(app_zip_bytes),
        "source": source_stats,
        "packaged_files": len(packaged),
        "packaged_bytes": packaged_bytes,
        "media": dict(sorted(media_counts.items())),
        "sha256": _sha256_file(apk_path),
    }


def _print_result(result: dict[str, object]) -> None:
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify-source")
    subparsers.add_parser("verify-mirror")
    apk_parser = subparsers.add_parser("verify-apk")
    apk_parser.add_argument("apk", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-source":
            result = {
                "tree": verify_tree(SOURCE_ASSETS),
                "git": verify_git_inventory(),
            }
        elif args.command == "verify-mirror":
            result = compare_trees(SOURCE_ASSETS, PACKAGE_ASSETS)
        else:
            result = verify_apk(SOURCE_ASSETS, args.apk.resolve())
    except (AssetGateError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"ASSET GATE FAILED: {exc}", file=sys.stderr)
        return 1
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

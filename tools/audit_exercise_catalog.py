"""Audit and optionally reconcile the bundled exercise catalog with upstream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from assemble_exercise_catalog import CANONICAL_RECORD_OVERRIDES, category_for, subgroup_for


def source_id(item: dict) -> str:
    value = str(item.get("id") or "")
    return value.removeprefix("dataset:").zfill(4)


def media_id_from_local(item: dict) -> str:
    return Path(str(item.get("gif") or "")).stem.split("-", 1)[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_json", type=Path, help="Upstream data/exercises.json")
    parser.add_argument("--local", type=Path, default=Path("src/exercise_catalog_data.json"))
    parser.add_argument("--assets-root", type=Path, default=Path("assets"))
    parser.add_argument("--apply", action="store_true", help="Apply reviewed category/name repairs")
    args = parser.parse_args()

    upstream = json.loads(args.source_json.read_text(encoding="utf-8"))
    local = json.loads(args.local.read_text(encoding="utf-8"))
    upstream_by_id = {str(item["id"]).zfill(4): item for item in upstream}
    local_by_id = {source_id(item): item for item in local}

    missing = sorted(set(upstream_by_id) - set(local_by_id))
    extra = sorted(set(local_by_id) - set(upstream_by_id))
    media_mismatches = []
    missing_files = []
    category_repairs = []

    for item_id in sorted(set(upstream_by_id) & set(local_by_id)):
        source = upstream_by_id[item_id]
        target = local_by_id[item_id]
        if str(source.get("media_id") or "").casefold() != media_id_from_local(target).casefold():
            media_mismatches.append(item_id)
        for key in ("image", "gif"):
            path = args.assets_root / str(target.get(key) or "")
            if not path.is_file():
                missing_files.append(str(path))
        expected_category = category_for(source)
        expected_subgroup = subgroup_for(source, expected_category)
        if (target.get("category"), target.get("subgroup")) != (expected_category, expected_subgroup):
            category_repairs.append((item_id, target.get("category"), expected_category))
            if args.apply:
                target["category"] = expected_category
                target["subgroup"] = expected_subgroup
        if args.apply:
            target.update(CANONICAL_RECORD_OVERRIDES.get(item_id, {}))

    print(f"upstream={len(upstream)} local={len(local)}")
    print(f"missing_ids={len(missing)} extra_ids={len(extra)} media_mismatches={len(media_mismatches)}")
    print(f"missing_asset_files={len(missing_files)} category_repairs={len(category_repairs)}")
    if missing:
        print("missing:", ",".join(missing))
    if extra:
        print("extra:", ",".join(extra))
    if media_mismatches:
        print("media:", ",".join(media_mismatches))
    if missing_files:
        print("files:", *missing_files, sep="\n")

    if args.apply:
        args.local.write_text(json.dumps(local, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"applied={len(category_repairs)} output={args.local}")

    return 1 if missing or extra or media_mismatches or missing_files else 0


if __name__ == "__main__":
    raise SystemExit(main())

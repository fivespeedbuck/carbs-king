"""Convert the offline Chinese food-composition JSON files into app data."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def number(value: object) -> float:
    text = str(value or "").strip()
    if text in {"", "—", "-", "Tr", "tr"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def category_for(path: Path) -> tuple[str, str]:
    stem = path.stem.removeprefix("merged_")
    main, _, subgroup = stem.partition("-")
    return main or "其他", subgroup or "其他"


def main(source_dir: Path, output: Path) -> None:
    foods: list[dict[str, object]] = []
    seen: set[str] = set()
    for file in sorted(source_dir.glob("*.json")):
        category, subgroup = category_for(file)
        rows = json.loads(file.read_text(encoding="utf-8"))
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("foodName") or "").strip()
            code = str(row.get("foodCode") or "").strip()
            if not name or not code or code in seen:
                continue
            seen.add(code)
            foods.append({
                "id": f"cnfc:{code}", "food_code": code, "name": name,
                "category": category, "subgroup": subgroup,
                "unit": "g", "method": "每 100g 可食部分", "base_qty": 100,
                "kcal": number(row.get("energyKCal")), "carb": number(row.get("CHO")),
                "protein": number(row.get("protein")), "fat": number(row.get("fat")),
                "fiber": number(row.get("dietaryFiber")), "cholesterol": number(row.get("cholesterol")),
                "sodium": number(row.get("Na")), "potassium": number(row.get("K")),
                "calcium": number(row.get("Ca")), "remark": str(row.get("remark") or "").strip("— "),
            })
    output.write_text(json.dumps(foods, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"生成 {len(foods)} 条食物：{output}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: assemble_food_catalog.py <source_dir> <output_json>")
    main(Path(sys.argv[1]), Path(sys.argv[2]))

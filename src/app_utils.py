"""Small dependency-free formatting and nutrition helpers."""

from __future__ import annotations


def to_float(value, default=0.0):
    try:
        if value is None:
            return default
        text = str(value).strip()
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def compact_range_text(min_value, max_value, unit="g"):
    try:
        low = int(round(float(min_value)))
        high = int(round(float(max_value)))
        return f"{low}-{high}{unit}"
    except Exception:
        return f"{min_value}-{max_value}{unit}"


def calc_item(food, qty):
    base = to_float(food.get("base_qty"), 100)
    factor = to_float(qty) / base if base else 0
    return {
        "kcal": round(to_float(food.get("kcal")) * factor, 1),
        "carb": round(to_float(food.get("carb")) * factor, 1),
        "protein": round(to_float(food.get("protein")) * factor, 1),
        "fat": round(to_float(food.get("fat")) * factor, 1),
    }


__all__ = ["calc_item", "compact_range_text", "to_float"]

# -*- coding: utf-8 -*-
import json
import os
import shutil
import sys
import datetime
import re
from pathlib import Path
from datetime import date
import flet as ft

APP_NAME = "碳水大王"
MEALS = ["早餐", "午餐", "晚餐", "练后", "偷吃"]

DAY_TYPES = {
    # 碳水按当前体重 g/kg 计算，再按体脂、年龄做轻微修正。
    # interval 为上下容差，避免区间过宽。
    "高碳日": {"calorie_factor": 0.80, "carb_gkg": 2.90, "carb_interval": 15, "fat_gkg_min": 0.70, "fat_gkg_max": 0.85},
    "中碳日": {"calorie_factor": 0.72, "carb_gkg": 2.30, "carb_interval": 12, "fat_gkg_min": 0.80, "fat_gkg_max": 0.95},
    "低碳日": {"calorie_factor": 0.65, "carb_gkg": 1.40, "carb_interval": 10, "fat_gkg_min": 0.95, "fat_gkg_max": 1.10},
}

TRAINING_TARGETS = ["胸", "背", "肩", "腿", "手臂", "腹", "爬坡", "跑步", "徒步", "游泳", "骑行", "打球", "休息", "其他"]
ABS_ACTIONS = ["仰卧抬腿", "悬垂举腿", "卷腹", "平板支撑", "其他"]
FATIGUE_OPTIONS = ["状态好", "状态一般", "状态差"]

DEFAULT_FOODS = [
    {"name": "燕麦", "category": "主食", "unit": "g", "method": "干重", "base_qty": 100, "kcal": 380, "carb": 67, "protein": 13, "fat": 7},
    {"name": "米饭", "category": "主食", "unit": "g", "method": "熟米饭重量", "base_qty": 100, "kcal": 116, "carb": 25.9, "protein": 2.6, "fat": 0.3},
    {"name": "玉米", "category": "主食", "unit": "g", "method": "带芯重量", "base_qty": 100, "kcal": 58, "carb": 12, "protein": 1.8, "fat": 0.7},
    {"name": "红薯", "category": "主食", "unit": "g", "method": "可食熟重", "base_qty": 100, "kcal": 86, "carb": 20.1, "protein": 1.6, "fat": 0.1},
    {"name": "土豆", "category": "主食", "unit": "g", "method": "可食熟重", "base_qty": 100, "kcal": 77, "carb": 17.5, "protein": 2, "fat": 0.1},
    {"name": "全麦面包", "category": "主食", "unit": "g", "method": "可食重量", "base_qty": 100, "kcal": 246, "carb": 41, "protein": 8.5, "fat": 3.6},
    {"name": "意面", "category": "主食", "unit": "g", "method": "熟重", "base_qty": 100, "kcal": 158, "carb": 30.9, "protein": 5.8, "fat": 0.9},
    {"name": "鸡胸肉", "category": "蛋白", "unit": "g", "method": "可食用生重", "base_qty": 100, "kcal": 110, "carb": 0, "protein": 23, "fat": 1.5},
    {"name": "瘦牛肉", "category": "蛋白", "unit": "g", "method": "可食用生重", "base_qty": 100, "kcal": 135, "carb": 0, "protein": 20, "fat": 7},
    {"name": "活虾", "category": "蛋白", "unit": "g", "method": "带壳重量，约55%可食率", "base_qty": 100, "kcal": 47, "carb": 0, "protein": 9.9, "fat": 0.7},
    {"name": "虾仁", "category": "蛋白", "unit": "g", "method": "可食用生重", "base_qty": 100, "kcal": 85, "carb": 0, "protein": 18, "fat": 1.2},
    {"name": "鲈鱼", "category": "蛋白", "unit": "g", "method": "可食用生重", "base_qty": 100, "kcal": 95, "carb": 0, "protein": 19, "fat": 2},
    {"name": "三文鱼", "category": "蛋白", "unit": "g", "method": "可食用生重", "base_qty": 100, "kcal": 208, "carb": 0, "protein": 20, "fat": 13},
    {"name": "金枪鱼罐头", "category": "蛋白", "unit": "g", "method": "沥干重量", "base_qty": 100, "kcal": 116, "carb": 0, "protein": 25, "fat": 1},
    {"name": "鸡蛋", "category": "蛋白/脂肪", "unit": "个", "method": "按个数，约50g/个", "base_qty": 1, "kcal": 70, "carb": 0.6, "protein": 6.5, "fat": 5},
    {"name": "蛋清", "category": "蛋白", "unit": "个", "method": "按个数", "base_qty": 1, "kcal": 17, "carb": 0.2, "protein": 3.6, "fat": 0},
    {"name": "无糖酸奶", "category": "蛋白", "unit": "g", "method": "可食重量", "base_qty": 100, "kcal": 60, "carb": 4.7, "protein": 5.5, "fat": 2.5},
    {"name": "乳清蛋白粉", "category": "补剂/蛋白", "unit": "勺", "method": "约30g/勺", "base_qty": 1, "kcal": 120, "carb": 3, "protein": 24, "fat": 2},
    {"name": "黄瓜", "category": "蔬菜", "unit": "g", "method": "可食重量", "base_qty": 100, "kcal": 16, "carb": 3.6, "protein": 0.7, "fat": 0.1},
    {"name": "小番茄", "category": "蔬菜", "unit": "g", "method": "可食重量", "base_qty": 100, "kcal": 22, "carb": 4.8, "protein": 1, "fat": 0.2},
    {"name": "西兰花", "category": "蔬菜", "unit": "g", "method": "可食重量", "base_qty": 100, "kcal": 34, "carb": 6.6, "protein": 2.8, "fat": 0.4},
    {"name": "生菜", "category": "蔬菜", "unit": "g", "method": "可食重量", "base_qty": 100, "kcal": 15, "carb": 2.9, "protein": 1.4, "fat": 0.2},
    {"name": "菠菜", "category": "蔬菜", "unit": "g", "method": "可食重量", "base_qty": 100, "kcal": 23, "carb": 3.6, "protein": 2.9, "fat": 0.4},
    {"name": "香蕉", "category": "水果", "unit": "g", "method": "可食重量", "base_qty": 100, "kcal": 93, "carb": 22, "protein": 1.4, "fat": 0.2},
    {"name": "苹果", "category": "水果", "unit": "g", "method": "可食重量", "base_qty": 100, "kcal": 52, "carb": 13.8, "protein": 0.3, "fat": 0.2},
    {"name": "橄榄油", "category": "脂肪", "unit": "g", "method": "重量", "base_qty": 10, "kcal": 90, "carb": 0, "protein": 0, "fat": 10},
    {"name": "花生酱", "category": "脂肪", "unit": "g", "method": "重量", "base_qty": 100, "kcal": 588, "carb": 20, "protein": 25, "fat": 50},
    {"name": "杏仁", "category": "脂肪", "unit": "g", "method": "重量", "base_qty": 100, "kcal": 579, "carb": 21.6, "protein": 21.2, "fat": 49.9},
]

DEFAULT_SUPPLEMENTS = [
    {"name": "肌酸", "default_amount": "5", "unit": "g"},
    {"name": "乳清蛋白粉", "default_amount": "1", "unit": "勺"},
    {"name": "咖啡因", "default_amount": "100-200", "unit": "mg"},
    {"name": "氮泵", "default_amount": "1", "unit": "份"},
    {"name": "鱼油", "default_amount": "1-2", "unit": "粒"},
    {"name": "复合维生素", "default_amount": "1", "unit": "片"},
    {"name": "电解质", "default_amount": "1", "unit": "份"},
]

BG = "#F7F7F7"
CARD = "#FFFFFF"
PRIMARY = "#42D0A3"
TEXT = "#303030"
SUB = "#7A7A7A"
RED = "#C62828"
ORANGE = "#EF6C00"
GREEN = "#2E7D32"
SKY_BLUE = "#29B6F6"
BAR_BG = "#E9ECEF"
YELLOW = "#F9A825"


# ---- Flet compatibility layer ----
# Avoid hard dependency on APIs that changed across Flet versions.
_THEME_LIGHT = getattr(getattr(ft, "ThemeMode", object()), "LIGHT", "light")
_SCROLL_AUTO = getattr(getattr(ft, "ScrollMode", object()), "AUTO", "auto")
_KEYBOARD_NUMBER = getattr(getattr(ft, "KeyboardType", object()), "NUMBER", None)

_EVENT_KWARGS = {
    "on_click", "on_change", "on_submit", "on_focus", "on_blur",
    "on_select", "on_dismiss", "on_tap", "on_long_press"
}

def _make_flet_compat_factory(original_cls, aliases=None):
    """
    Flet 0.85.x changed several control constructor signatures.
    This factory strips unsupported keyword arguments from __init__ and applies
    them as object attributes after construction.
    """
    aliases = aliases or {}

    def factory(*args, **kwargs):
        post_attrs = {}

        # Handle aliases first.
        for old_key, new_key in aliases.items():
            if old_key in kwargs:
                post_attrs[new_key] = kwargs.pop(old_key)

        # Events are safest when assigned after construction.
        for key in list(kwargs.keys()):
            if key in _EVENT_KWARGS:
                post_attrs[key] = kwargs.pop(key)

        # Iteratively strip unexpected kwargs and apply as attributes.
        # This prevents one incompatible keyword from killing the app.
        local_kwargs = dict(kwargs)
        stripped = {}
        for _ in range(30):
            try:
                ctrl = original_cls(*args, **local_kwargs)
                for k, v in {**stripped, **post_attrs}.items():
                    try:
                        setattr(ctrl, k, v)
                    except Exception:
                        pass
                return ctrl
            except TypeError as ex:
                msg = str(ex)
                m = re.search(r"unexpected keyword argument '([^']+)'", msg)
                if not m:
                    raise
                bad_key = m.group(1)
                if bad_key in local_kwargs:
                    stripped[bad_key] = local_kwargs.pop(bad_key)
                    continue
                raise

        ctrl = original_cls(*args)
        for k, v in {**stripped, **post_attrs}.items():
            try:
                setattr(ctrl, k, v)
            except Exception:
                pass
        return ctrl

    return factory

# Patch only the controls used in this app.
# This keeps the rest of Flet untouched.
for _name, _aliases in {
    "Container": {},
    "IconButton": {},
    "TextField": {},
    "Dropdown": {},
    "Checkbox": {},
    "DatePicker": {},
    "AlertDialog": {},
    "SnackBar": {},
    "Row": {},
    "Column": {},
    "Text": {"selectable": "enable_interactive_selection"},
    "Divider": {},
    "ListView": {},
    "SafeArea": {},
}.items():
    if hasattr(ft, _name):
        setattr(ft, _name, _make_flet_compat_factory(getattr(ft, _name), _aliases))


SCRIPT_DIR = Path(__file__).resolve().parent

def get_app_dir() -> Path:
    try:
        if sys.platform.startswith("win"):
            root = Path(os.environ.get("APPDATA", str(Path.home())))
            app_dir = root / "CarbCycleRecorderMobile"
        else:
            app_dir = Path.home() / ".carb_cycle_recorder_mobile"
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir
    except Exception:
        return SCRIPT_DIR

APP_DIR = get_app_dir()
FOOD_FILE = APP_DIR / "food_library.json"
SUPP_FILE = APP_DIR / "supplement_library.json"
RECORD_FILE = APP_DIR / "daily_records.json"
PROFILE_FILE = APP_DIR / "user_profile.json"

def migrate_legacy_data():
    if APP_DIR == SCRIPT_DIR:
        return
    for filename in ["food_library.json", "supplement_library.json", "daily_records.json"]:
        old_path = SCRIPT_DIR / filename
        new_path = APP_DIR / filename
        try:
            if old_path.exists() and not new_path.exists():
                shutil.copy2(old_path, new_path)
        except Exception:
            pass

migrate_legacy_data()

def load_json(path: Path, default):
    if not path.exists():
        save_json(path, default)
        return default
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if data else default
    except Exception:
        return default

def save_json(path: Path, data):
    with path.open("w", encoding="utf-8-sig") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_user_profile():
    default = {
        "height": "170",
        "age": "30",
        "sex": "男",
        "activity_habit": "规律训练",
        "waist_cm": "",
        "arm_cm": "",
        "profile_inited": False,
    }
    data = load_json(PROFILE_FILE, default)
    if not isinstance(data, dict):
        data = default
    for k, v in default.items():
        data.setdefault(k, v)
    return data

def save_user_profile(data):
    save_json(PROFILE_FILE, data)

def to_float(value, default=0.0):
    try:
        if value is None:
            return default
        s = str(value).strip()
        if not s:
            return default
        return float(s)
    except Exception:
        return default

def compact_range_text(min_value, max_value, unit="g"):
    """Show target ranges compactly in small mobile cards."""
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

def make_button(text, on_click=None, icon=None, bgcolor=None, color=None, expand=False):
    """Light, compact button closer to common mobile app styles."""
    fg = color or "#FFFFFF"
    bg = bgcolor or PRIMARY
    children = []
    if icon is not None:
        children.append(ft.Icon(icon, size=15, color=fg))
    children.append(ft.Text(text, size=12, weight="bold", color=fg))

    btn = ft.Container(
        content=ft.Row(children, alignment="center", spacing=4),
        height=38,
        padding=8,
        bgcolor=bg,
        border_radius=8,
        on_click=on_click,
    )
    btn.expand = expand
    return btn


def card(content, padding=12, margin_bottom=8):
    return ft.Container(
        content=content,
        bgcolor=CARD,
        border_radius=0,
        padding=padding,
        margin=margin_bottom,
    )

def section_title(text):
    return ft.Text(text, size=15, weight="bold", color=TEXT)

def small_text(text, color=SUB):
    return ft.Text(text, size=11, color=color)

def labeled_plain_field(label, value="", width=None, keyboard_type=None, expand=False, height=46):
    field = plain_number_field(value=value, width=width, keyboard_type=keyboard_type, expand=expand, height=height)
    box = ft.Column([small_text(label), field], spacing=3)
    if expand:
        box.expand = True
    return box, field

def mobile_text_field(label, value="", width=None, keyboard_type=None, on_change=None, expand=False, height=52):
    fld = ft.TextField(label=label, value=value, width=width, height=height, keyboard_type=keyboard_type)
    try:
        fld.text_size = 14
        fld.dense = True
        fld.border_radius = 8
        fld.bgcolor = "#FFFFFF"
        fld.border_color = "#DDE3EA"
        fld.focused_border_color = PRIMARY
        fld.cursor_color = PRIMARY
        fld.content_padding = 12
    except Exception:
        pass
    if on_change:
        fld.on_change = on_change
    if expand:
        fld.expand = True
    return fld

def mobile_dropdown(label, value, options, width=None, on_change=None, expand=False):
    dd = ft.Dropdown(label=label, value=value, options=options, width=width, height=52)
    try:
        dd.text_size = 14
        dd.dense = True
        dd.border_radius = 8
        dd.bgcolor = "#FFFFFF"
        dd.border_color = "#DDE3EA"
        dd.focused_border_color = PRIMARY
        dd.content_padding = 12
    except Exception:
        pass
    if on_change:
        dd.on_change = on_change
    if expand:
        dd.expand = True
    return dd

def plain_number_field(value="", width=None, keyboard_type=None, on_change=None, expand=False, height=46):
    fld = ft.TextField(value=value, width=width, height=height, keyboard_type=keyboard_type)
    try:
        fld.text_size = 14
        fld.dense = True
        fld.border_radius = 8
        fld.bgcolor = "#FFFFFF"
        fld.border_color = "#DDE3EA"
        fld.focused_border_color = PRIMARY
        fld.cursor_color = PRIMARY
        fld.content_padding = 12
    except Exception:
        pass
    if on_change:
        fld.on_change = on_change
    if expand:
        fld.expand = True
    return fld

def custom_progress_bar(label, current, target_text, ratio, color, width=420):
    """Thick custom progress bar; width is calculated from current page size."""
    try:
        ratio = max(0, min(float(ratio), 1))
    except Exception:
        ratio = 0

    width = int(width or 420)
    height = 14
    radius = 8
    fill_width = max(0, int(width * ratio))
    empty_width = max(0, width - fill_width)

    return ft.Column([
        ft.Container(
            content=ft.Row([
                ft.Text(label, size=13, color=TEXT, weight="bold"),
                ft.Text(target_text, size=13, color=SUB),
            ], alignment="spaceBetween"),
            width=width,
        ),
        ft.Container(
            content=ft.Row([
                ft.Container(width=fill_width, height=height, bgcolor=color, border_radius=radius),
                ft.Container(width=empty_width, height=height),
            ], spacing=0),
            width=width,
            height=height,
            bgcolor=BAR_BG,
            border_radius=radius,
        ),
    ], spacing=6)

def macro_progress_bar(label, current, target_value=None, target_min=None, target_max=None, kind="carb", width=300):
    current = to_float(current)

    if target_min is not None and target_max is not None:
        min_target = to_float(target_min)
        max_target = to_float(target_max)
        target_text = f"{current:g} / {min_target:g}-{max_target:g}g"

        if current < min_target:
            ratio = current / min_target if min_target > 0 else 0
        else:
            ratio = 1

        if kind == "carb":
            warn_gap = 20
        elif kind == "protein":
            warn_gap = 25
        else:
            warn_gap = 10

        if current <= max_target:
            color = GREEN
        elif current <= max_target + warn_gap:
            color = YELLOW
        else:
            color = RED

        return custom_progress_bar(label, current, target_text, ratio, color, width=width)

    target = to_float(target_value)
    target_text = f"{current:g} / {target:g}g"
    ratio = current / target if target > 0 else 0
    color = GREEN if current <= target else YELLOW
    return custom_progress_bar(label, current, target_text, ratio, color, width=width)

def water_progress_bar(total_ml, target_ml=2000, width=300):
    total_ml = to_float(total_ml)
    color = SKY_BLUE if total_ml >= target_ml else GREEN
    ratio = total_ml / target_ml if target_ml > 0 else 0
    return custom_progress_bar("饮水进度", total_ml, f"{int(total_ml)} / {target_ml} ml", ratio, color, width=width)

def pill(text, color=PRIMARY):
    return ft.Container(
        content=ft.Text(text, size=12, color=color, weight="bold"),
        bgcolor="#EEF9F5",
        border_radius=12,
        padding=6,
    )

def main(page: ft.Page):
    page.title = APP_NAME
    page.bgcolor = BG
    page.theme_mode = _THEME_LIGHT
    try:
        page.theme = ft.Theme(font_family="Microsoft YaHei")
    except Exception:
        try:
            page.theme.font_family = "Microsoft YaHei"
        except Exception:
            pass
    page.scroll = None
    try:
        page.window_width = 430
        page.window_height = 860
    except Exception:
        pass

    def open_control(control):
        if control not in page.overlay:
            page.overlay.append(control)
        control.open = True
        page.update()

    def close_control(control):
        control.open = False
        page.update()

    def snack(message):
        # Flet 0.85.3 compatibility:
        # page.snack_bar may not visibly open in this build, so put SnackBar in overlay.
        sb = ft.SnackBar(content=ft.Text(message, size=13, color="#FFFFFF"))
        try:
            sb.duration = 1600
        except Exception:
            pass
        try:
            sb.bgcolor = PRIMARY
        except Exception:
            pass
        if sb not in page.overlay:
            page.overlay.append(sb)
        sb.open = True
        page.update()

    def responsive_bar_width():
        """Fit progress bars to the current card content width.

        The previous version used fixed buckets such as 760/980px.
        This version calculates from the real page width so the bar follows
        window resizing and aligns closer to the card's inner border.
        """
        raw_width = None
        for attr in ["width", "window_width"]:
            try:
                value = getattr(page, attr, None)
                if value:
                    raw_width = float(value)
                    break
            except Exception:
                pass

        if raw_width is None:
            raw_width = 430

        # Mobile-first width. Avoid desktop-width bars on Android.
        content_width = int(raw_width - 72)

        if content_width < 230:
            content_width = 230
        if content_width > 640:
            content_width = 640

        return content_width

    # State
    foods = load_json(FOOD_FILE, DEFAULT_FOODS)
    supplements = load_json(SUPP_FILE, DEFAULT_SUPPLEMENTS)
    records = load_json(RECORD_FILE, {})

    state = {
        "date": date.today().isoformat(),
        "weight": "62.5",
        "bodyfat": "13",
        "height": "170",
        "age": "30",
        "sex": "男",
        "activity_habit": "规律训练",
        "waist_cm": "",
        "arm_cm": "",
        "profile_inited": False,
        "day_type": "高碳日",
        "meals": {m: [] for m in MEALS},
        "training": {
            "total_duration_min": "",
            "total_calories_kcal": "",
            "fatigue_status": "状态一般",
            "summary_note": "",
            "targets": [],
        },
        "water": [],
        "supplements": [],
        "sleep": {"bed_time": "", "wake_time": "", "naps": []},
        "current_view": "today",
        "selected_meal": "汇总",
    }

    saved_profile = load_user_profile()
    state["height"] = str(saved_profile.get("height", state["height"]))
    state["age"] = str(saved_profile.get("age", state["age"]))
    state["sex"] = str(saved_profile.get("sex", state["sex"]))
    state["activity_habit"] = str(saved_profile.get("activity_habit", state["activity_habit"]))
    state["waist_cm"] = str(saved_profile.get("waist_cm", state.get("waist_cm", "")))
    state["arm_cm"] = str(saved_profile.get("arm_cm", state.get("arm_cm", "")))
    state["profile_inited"] = bool(saved_profile.get("profile_inited", False))

    def body_composition():
        weight = to_float(state["weight"], 62.5)
        bodyfat = to_float(state["bodyfat"], 13)
        height = to_float(state.get("height"), 170)
        age = to_float(state.get("age"), 30)
        sex = state.get("sex", "男")

        if bodyfat < 3 or bodyfat > 60:
            bodyfat = 13
        if height < 120 or height > 230:
            height = 170
        if age < 10 or age > 90:
            age = 30

        lean_mass = round(weight * (1 - bodyfat / 100), 1)
        fat_mass = round(weight - lean_mass, 1)

        # Mifflin-St Jeor BMR
        bmr = 10 * weight + 6.25 * height - 5 * age + (5 if sex == "男" else -161)
        bmr = round(bmr, 0)

        activity_habit = state.get("activity_habit", "规律训练")
        activity_factor_map = {
            "久坐少动": 1.25,
            "偶尔运动": 1.35,
            "规律训练": 1.45,
            "高频训练": 1.60,
        }
        activity_factor = activity_factor_map.get(activity_habit, 1.45)
        tdee = round(bmr * activity_factor, 0)

        return {
            "weight": round(weight, 1),
            "bodyfat": round(bodyfat, 1),
            "height": round(height, 1),
            "age": round(age, 0),
            "sex": sex,
            "lean_mass": lean_mass,
            "fat_mass": fat_mass,
            "bmr": bmr,
            "tdee": tdee,
            "activity_habit": activity_habit,
            "activity_factor": activity_factor,
        }

    def get_targets():
        comp = body_composition()
        weight = comp["weight"]
        lean_mass = comp["lean_mass"]
        bodyfat = comp["bodyfat"]
        age = comp["age"]
        sex = comp["sex"]
        cfg = DAY_TYPES.get(state["day_type"], DAY_TYPES["高碳日"])

        calorie_target = round(comp["tdee"] * cfg["calorie_factor"], 0)

        # 蛋白：按去脂体重区间估算，2.0-2.3g/kg LBM。
        protein_min = round(lean_mass * 2.0, 1)
        protein_max = round(lean_mass * 2.3, 1)

        # 脂肪：高碳低脂，低碳略高脂；按体重估算。
        fat_min = round(weight * cfg["fat_gkg_min"], 1)
        fat_max = round(weight * cfg["fat_gkg_max"], 1)

        # 碳水：高/中/低碳日 g/kg 核心值 + 合理容差。
        carb_gkg = cfg["carb_gkg"]
        if sex == "男":
            if bodyfat >= 18:
                carb_gkg -= 0.15
            elif bodyfat <= 12:
                carb_gkg += 0.10
        else:
            if bodyfat >= 28:
                carb_gkg -= 0.15
            elif bodyfat <= 20:
                carb_gkg += 0.10

        if age >= 45:
            carb_gkg -= 0.10
        elif age <= 25:
            carb_gkg += 0.05

        carb_center = max(30, round(weight * carb_gkg, 1))
        carb_interval = cfg["carb_interval"]
        carb_min = max(30, round(carb_center - carb_interval, 1))
        carb_max = round(carb_center + carb_interval, 1)

        if state["day_type"] == "高碳日":
            carb_min = max(carb_min, round(weight * 2.5, 1))
            carb_max = min(carb_max, round(weight * 3.4, 1))
        elif state["day_type"] == "中碳日":
            carb_min = max(carb_min, round(weight * 1.8, 1))
            carb_max = min(carb_max, round(weight * 2.7, 1))
        else:
            carb_min = max(carb_min, round(weight * 0.9, 1))
            carb_max = min(carb_max, round(weight * 1.7, 1))

        if carb_max < carb_min:
            carb_max = carb_min + 10

        return {
            "carb_min": round(carb_min, 1),
            "carb_max": round(carb_max, 1),
            "carb": round((carb_min + carb_max) / 2, 1),
            "protein_min": protein_min,
            "protein_max": protein_max,
            "protein": round((protein_min + protein_max) / 2, 1),
            "fat_min": fat_min,
            "fat_max": fat_max,
            "lean_mass": lean_mass,
            "fat_mass": comp["fat_mass"],
            "bodyfat": comp["bodyfat"],
            "height": comp["height"],
            "age": comp["age"],
            "sex": comp["sex"],
            "bmr": comp["bmr"],
            "tdee": comp["tdee"],
            "calorie_target": calorie_target,
            "activity_habit": comp["activity_habit"],
            "activity_factor": comp["activity_factor"],
        }

    def daily_total():
        total = {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}
        for items in state["meals"].values():
            for item in items:
                for k in total:
                    total[k] += to_float(item.get(k))
        return {k: round(v, 1) for k, v in total.items()}

    def parse_time_minutes(value):
        """Parse HH:MM / H:MM / HHMM / H into minutes from 00:00."""
        s = str(value or "").strip()
        if not s:
            return None
        try:
            if ":" in s:
                parts = s.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            else:
                digits = "".join(ch for ch in s if ch.isdigit())
                if not digits:
                    return None
                if len(digits) <= 2:
                    hour = int(digits)
                    minute = 0
                else:
                    hour = int(digits[:-2])
                    minute = int(digits[-2:])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour * 60 + minute
        except Exception:
            return None
        return None

    def duration_between(start, end):
        sm = parse_time_minutes(start)
        em = parse_time_minutes(end)
        if sm is None or em is None:
            return 0
        diff = em - sm
        if diff < 0:
            diff += 24 * 60
        return diff

    def sleep_total_minutes():
        sl = state.get("sleep", {})
        total = duration_between(sl.get("bed_time", ""), sl.get("wake_time", ""))
        for nap in sl.get("naps", []):
            total += duration_between(nap.get("start", ""), nap.get("end", ""))
        return int(total)

    def format_minutes(total):
        total = int(total or 0)
        h = total // 60
        m = total % 60
        if h and m:
            return f"{h}小时{m}分"
        if h:
            return f"{h}小时"
        if m:
            return f"{m}分"
        return "未记录"

    def evaluate(total=None):
        if total is None:
            total = daily_total()
        targets = get_targets()
        carb = to_float(total.get("carb"))
        protein = to_float(total.get("protein"))
        fat = to_float(total.get("fat"))
        kcal = to_float(total.get("kcal"))

        def range_msg(value, low, high):
            if low <= value <= high:
                return "达标"
            return "偏高" if value > high else "偏低"

        carb_ok = targets["carb_min"] <= carb <= targets["carb_max"]
        protein_ok = targets["protein_min"] <= protein <= targets["protein_max"]
        fat_ok = targets["fat_min"] <= fat <= targets["fat_max"]

        kcal_target = targets["calorie_target"]
        kcal_diff = round(kcal - kcal_target, 1)

        warnings = []
        if carb < targets["carb_min"] - 10:
            warnings.append(f"碳水不足 {round(targets['carb_min'] - carb, 1):g}g")
        if carb > targets["carb_max"] + 10:
            warnings.append(f"碳水超出 {round(carb - targets['carb_max'], 1):g}g")
        if protein < targets["protein_min"] - 5:
            warnings.append(f"蛋白不足 {round(targets['protein_min'] - protein, 1):g}g")
        if protein > targets["protein_max"] + 15:
            warnings.append(f"蛋白超出 {round(protein - targets['protein_max'], 1):g}g")
        if fat < targets["fat_min"] - 5:
            warnings.append(f"脂肪不足 {round(targets['fat_min'] - fat, 1):g}g")
        if fat > targets["fat_max"] + 5:
            warnings.append(f"脂肪超出 {round(fat - targets['fat_max'], 1):g}g")
        if kcal_diff > 150:
            warnings.append(f"热量超出约 {kcal_diff:g} kcal")

        return {
            "status": "达标" if carb_ok and protein_ok and fat_ok else "未达标",
            "carb_msg": range_msg(carb, targets["carb_min"], targets["carb_max"]),
            "protein_msg": range_msg(protein, targets["protein_min"], targets["protein_max"]),
            "fat_msg": range_msg(fat, targets["fat_min"], targets["fat_max"]),
            "kcal_target": kcal_target,
            "warning_text": "；".join(warnings) if warnings else "无明显超出/不足项",
        }

    def record_payload():
        total = daily_total()
        eva = evaluate(total)
        targets = get_targets()
        meal_totals = {}
        for m in MEALS:
            t = {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}
            for item in state["meals"].get(m, []):
                for k in t:
                    t[k] += to_float(item.get(k))
            meal_totals[m] = {k: round(v, 1) for k, v in t.items()}

        return {
            "date": state["date"],
            "profile": {
                "weight_kg": state["weight"],
                "bodyfat_percent": state["bodyfat"],
                "height_cm": state.get("height", "170"),
                "age": state.get("age", "30"),
                "sex": state.get("sex", "男"),
                "activity_habit": state.get("activity_habit", "规律训练"),
                "waist_cm": state.get("waist_cm", ""),
                "arm_cm": state.get("arm_cm", ""),
                "day_type": state["day_type"],
                "targets": targets,
                "compliance": eva,
            },
            "meals": {m: list(items) for m, items in state["meals"].items()},
            "meal_totals": meal_totals,
            "daily_total": total,
            "training": {
                "total_duration_min": state["training"].get("total_duration_min", ""),
                "total_calories_kcal": state["training"].get("total_calories_kcal", ""),
                "fatigue_status": state["training"].get("fatigue_status", "状态一般"),
                "summary_note": state["training"].get("summary_note", ""),
                "targets": list(state["training"].get("targets", [])),
            },
            "water": {
                "records_ml": list(state["water"]),
                "total_ml": int(sum(state["water"])),
                "target_ml": 2000,
                "status": "达标" if sum(state["water"]) >= 2000 else "未达标",
            },
            "supplements": list(state["supplements"]),
            "sleep": {
                "bed_time": state.get("sleep", {}).get("bed_time", ""),
                "wake_time": state.get("sleep", {}).get("wake_time", ""),
                "naps": list(state.get("sleep", {}).get("naps", [])),
                "total_minutes": sleep_total_minutes(),
                "total_text": format_minutes(sleep_total_minutes()),
            },
        }

    def save_current(show=False):
        records[state["date"]] = record_payload()
        save_json(RECORD_FILE, records)
        if show:
            snack("已保存")

    def load_record_for_date(target_date, autosave=False, show=False):
        state["date"] = target_date
        rec = records.get(target_date)
        if rec:
            p = rec.get("profile", {})
            state["weight"] = str(p.get("weight_kg", state["weight"]))
            state["bodyfat"] = str(p.get("bodyfat_percent", state["bodyfat"]))
            if not state.get("profile_inited"):
                state["height"] = str(p.get("height_cm", state.get("height", "170")))
                state["age"] = str(p.get("age", state.get("age", "30")))
                state["sex"] = str(p.get("sex", state.get("sex", "男")))
                state["activity_habit"] = str(p.get("activity_habit", state.get("activity_habit", "规律训练")))
                state["waist_cm"] = str(p.get("waist_cm", state.get("waist_cm", "")))
                state["arm_cm"] = str(p.get("arm_cm", state.get("arm_cm", "")))
            state["day_type"] = p.get("day_type", "高碳日")
            saved_meals = rec.get("meals", {})
            state["meals"] = {m: list(saved_meals.get(m, [])) for m in MEALS}

            tr = rec.get("training", {})
            if isinstance(tr, dict):
                state["training"] = {
                    "total_duration_min": str(tr.get("total_duration_min", "")),
                    "total_calories_kcal": str(tr.get("total_calories_kcal", "")),
                    "fatigue_status": tr.get("fatigue_status", "状态一般"),
                    "summary_note": str(tr.get("summary_note", "")),
                    "targets": list(tr.get("targets", [])),
                }
            elif isinstance(tr, list):
                state["training"] = {"total_duration_min": "", "total_calories_kcal": "", "fatigue_status": "状态一般", "summary_note": "", "targets": list(tr)}
            else:
                state["training"] = {"total_duration_min": "", "total_calories_kcal": "", "fatigue_status": "状态一般", "summary_note": "", "targets": []}

            water = rec.get("water", {})
            if isinstance(water, dict):
                state["water"] = [to_float(x) for x in water.get("records_ml", [])]
            else:
                state["water"] = []
            state["supplements"] = list(rec.get("supplements", []))
            saved_sleep = rec.get("sleep", {})
            if isinstance(saved_sleep, dict):
                state["sleep"] = {
                    "bed_time": str(saved_sleep.get("bed_time", "")),
                    "wake_time": str(saved_sleep.get("wake_time", "")),
                    "naps": list(saved_sleep.get("naps", [])),
                }
            else:
                state["sleep"] = {"bed_time": "", "wake_time": "", "naps": []}
        else:
            state["day_type"] = "高碳日"
            state["meals"] = {m: [] for m in MEALS}
            state["training"] = {"total_duration_min": "", "total_calories_kcal": "", "fatigue_status": "状态一般", "summary_note": "", "targets": []}
            state["water"] = []
            state["supplements"] = []
            state["sleep"] = {"bed_time": "", "wake_time": "", "naps": []}
        if autosave:
            save_current()
        refresh()
        if show:
            snack(f"已加载 {target_date}")

    def get_previous_body_info():
        current_date = state.get("date", "")
        candidates = []
        for d, rec in records.items():
            if not d or d >= current_date:
                continue
            p = rec.get("profile", {}) if isinstance(rec, dict) else {}
            w = to_float(p.get("weight_kg"), None)
            bf = to_float(p.get("bodyfat_percent"), None)
            if w is None and bf is None:
                continue
            candidates.append((d, w, bf))

        if not candidates:
            return None

        prev_date, prev_weight, prev_bodyfat = sorted(candidates, key=lambda x: x[0])[-1]
        current_weight = to_float(state.get("weight"), None)
        current_bodyfat = to_float(state.get("bodyfat"), None)

        weight_diff = round(current_weight - prev_weight, 1) if current_weight is not None and prev_weight is not None else None
        bodyfat_diff = round(current_bodyfat - prev_bodyfat, 1) if current_bodyfat is not None and prev_bodyfat is not None else None

        return {
            "date": prev_date,
            "weight": prev_weight,
            "bodyfat": prev_bodyfat,
            "weight_diff": weight_diff,
            "bodyfat_diff": bodyfat_diff,
        }

    def format_date_label():
        today = date.today().isoformat()
        try:
            dt = datetime.datetime.strptime(state["date"], "%Y-%m-%d")
            text = f"{dt.year}年{dt.month:02d}月{dt.day:02d}日"
        except Exception:
            text = state["date"]
        return text

    def shift_date(delta):
        dt = datetime.datetime.strptime(state["date"], "%Y-%m-%d") + datetime.timedelta(days=delta)
        load_record_for_date(dt.strftime("%Y-%m-%d"), show=False)

    def open_calendar_picker():
        picker = ft.DatePicker()

        def on_change(e=None):
            value = getattr(picker, "value", None)
            if value:
                try:
                    chosen = value.date().isoformat()
                except Exception:
                    try:
                        chosen = value.isoformat()[:10]
                    except Exception:
                        chosen = None
                if chosen:
                    load_record_for_date(chosen, show=True)
            close_control(picker)

        def on_dismiss(e=None):
            try:
                close_control(picker)
            except Exception:
                pass

        try:
            current_dt = datetime.datetime.strptime(state["date"], "%Y-%m-%d")
            picker.value = current_dt
        except Exception:
            pass

        try:
            picker.on_change = on_change
        except Exception:
            pass
        try:
            picker.on_dismiss = on_dismiss
        except Exception:
            pass

        open_control(picker)

    def delete_history_record(target_date):
        if target_date in records:
            del records[target_date]
            save_json(RECORD_FILE, records)

            if state["date"] == target_date:
                # Keep the selected date, but clear the form since that day's saved record is gone.
                load_record_for_date(target_date, autosave=False, show=False)

            refresh()
            snack(f"已删除 {target_date}")

    # ---------- dialogs ----------
    def dialog_base(title, content, actions=None, on_close=None):
        actions = actions or []
        title_row = ft.Row([
            ft.Text(title, size=18, weight="bold", color=TEXT, expand=True),
            ft.IconButton(icon=ft.Icons.CLOSE_ROUNDED, icon_size=20, tooltip="关闭", on_click=on_close),
        ], spacing=6, vertical_alignment="center")

        return ft.AlertDialog(
            title=title_row,
            content=content,
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.CENTER,
        )

    def open_add_food_dialog(default_meal="午餐"):
        dialog_width = 340

        meal_dd = mobile_dropdown("餐次", default_meal, [ft.dropdown.Option(m) for m in MEALS], width=dialog_width)
        search = mobile_text_field("搜索食物", width=dialog_width)
        food_dd = mobile_dropdown("食物", None, [ft.dropdown.Option(f["name"]) for f in foods], width=dialog_width)

        def current_unit():
            food = next((f for f in foods if f.get("name") == food_dd.value), None)
            return food.get("unit", "g") if food else "g"

        qty = mobile_text_field(f"数量（{current_unit()}）", width=dialog_width, keyboard_type=_KEYBOARD_NUMBER)

        def update_qty_label():
            try:
                qty.label = f"数量（{current_unit()}）"
            except Exception:
                pass

        def apply_filter(e=None):
            kw = (search.value or "").strip().lower()
            filtered = [f for f in foods if not kw or kw in f.get("name", "").lower() or kw in f.get("category", "").lower()]
            food_dd.options = [ft.dropdown.Option(f["name"]) for f in filtered]
            if len(filtered) == 1:
                food_dd.value = filtered[0]["name"]
            update_qty_label()
            page.update()

        def food_changed(e=None):
            update_qty_label()
            page.update()

        search.on_change = apply_filter
        food_dd.on_change = food_changed

        dlg = None

        def confirm(e):
            if not food_dd.value or not qty.value:
                snack("请选择食物并填写数量")
                return
            food = next((f for f in foods if f["name"] == food_dd.value), None)
            q = to_float(qty.value)
            if not food or q <= 0:
                snack("食物或数量不正确")
                return
            item = {"food": food["name"], "qty": q, "unit": food.get("unit", "g"), "method": food.get("method", ""), **calc_item(food, q)}
            state["meals"][meal_dd.value].append(item)
            close_control(dlg)
            save_current()
            refresh()
            snack(f"已添加：{food['name']} {q}{item['unit']}")

        content = ft.Column([
            meal_dd,
            search,
            food_dd,
            qty,
        ], width=dialog_width, height=310, spacing=12)

        dlg = dialog_base(
            "添加饮食",
            content,
            [ft.Container(content=make_button("保存", on_click=confirm, expand=True), width=dialog_width)],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def open_training_dialog():
        if len(state["training"]["targets"]) >= 3:
            snack("每天最多记录 3 个训练目标")
            return

        dialog_width = 340
        dlg = None

        def target_button(name):
            return ft.Container(
                content=ft.Text(name, size=14, weight="bold", color=TEXT, text_align="center"),
                bgcolor="#FFFFFF",
                border_radius=8,
                padding=12,
                on_click=lambda e, n=name: (close_control(dlg), open_training_detail_dialog(n)),
                expand=True,
            )

        rows = []
        for i in range(0, len(TRAINING_TARGETS), 3):
            row_items = TRAINING_TARGETS[i:i+3]
            rows.append(ft.Row([target_button(x) for x in row_items], spacing=8))

        content = ft.Column(rows, width=dialog_width, height=360, spacing=8, scroll=_SCROLL_AUTO)

        dlg = dialog_base(
            "选择训练目标",
            content,
            [],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def open_training_detail_dialog(selected_target):
        dialog_width = 340
        cardio_targets = ["跑步", "徒步", "游泳", "骑行", "打球"]
        dlg = None

        note = mobile_text_field("备注", width=dialog_width)

        incline = mobile_text_field("坡度 %", keyboard_type=_KEYBOARD_NUMBER, expand=True)
        speed = mobile_text_field("速度 km/h", keyboard_type=_KEYBOARD_NUMBER, expand=True)
        climb_minutes = mobile_text_field("时长 min", keyboard_type=_KEYBOARD_NUMBER, expand=True)

        abs_action = mobile_dropdown("腹部动作", "仰卧抬腿", [ft.dropdown.Option(x) for x in ABS_ACTIONS], width=dialog_width)
        reps = mobile_text_field("次数/组数", width=dialog_width)

        cardio_minutes = mobile_text_field("时长 min", keyboard_type=_KEYBOARD_NUMBER, width=dialog_width)

        controls = [ft.Text(selected_target, size=16, weight="bold", color=PRIMARY)]

        if selected_target == "爬坡":
            controls.extend([
                small_text("爬坡参数"),
                ft.Row([incline, speed], spacing=8),
                climb_minutes,
            ])
        elif selected_target == "腹":
            controls.extend([
                small_text("腹部参数"),
                abs_action,
                reps,
            ])
        elif selected_target in cardio_targets:
            controls.extend([
                small_text("运动参数"),
                cardio_minutes,
            ])

        controls.append(note)

        def confirm(e):
            note_text = (note.value or "").strip()
            detail = selected_target

            if selected_target == "爬坡":
                parts = []
                if incline.value:
                    parts.append(f"坡度 {incline.value}%")
                if speed.value:
                    parts.append(f"速度 {speed.value} km/h")
                if climb_minutes.value:
                    parts.append(f"{climb_minutes.value} 分钟")
                detail = "，".join(parts) if parts else "爬坡"
            elif selected_target == "腹":
                detail = abs_action.value or "腹部训练"
                if reps.value:
                    detail += f"：{reps.value}"
            elif selected_target in cardio_targets:
                detail = f"{cardio_minutes.value} 分钟" if cardio_minutes.value else selected_target
            elif selected_target in ["休息", "其他"] and note_text:
                detail = note_text
                note_text = ""

            state["training"]["targets"].append({
                "target": selected_target,
                "detail": detail,
                "note": note_text,
            })
            close_control(dlg)
            save_current()
            refresh()
            snack("训练已添加")

        content = ft.Column(controls, width=dialog_width, height=360, spacing=12, scroll=_SCROLL_AUTO)

        dlg = dialog_base(
            f"{selected_target}记录",
            content,
            [ft.Container(content=make_button("保存", on_click=confirm, expand=True), width=dialog_width)],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def open_food_library_dialog(edit_index=None):
        editing = edit_index is not None
        dialog_width = 340
        item = foods[edit_index] if editing else {
            "name": "",
            "category": "",
            "unit": "g",
            "method": "",
            "base_qty": 100,
            "kcal": 0,
            "carb": 0,
            "protein": 0,
            "fat": 0,
        }

        field_labels = {
            "name": "食物名称",
            "category": "分类",
            "unit": "单位",
            "method": "计量口径",
            "base_qty": "基准数量",
            "kcal": "热量 kcal",
            "carb": "碳水 g",
            "protein": "蛋白 g",
            "fat": "脂肪 g",
        }

        fields = {}
        for key in ["name", "category", "unit", "method", "base_qty", "kcal", "carb", "protein", "fat"]:
            fields[key] = mobile_text_field(
                field_labels[key],
                value=str(item.get(key, "")),
                width=dialog_width if key not in ["unit", "base_qty"] else None,
                keyboard_type=_KEYBOARD_NUMBER if key in ["base_qty", "kcal", "carb", "protein", "fat"] else None,
                expand=key in ["unit", "base_qty"],
            )

        dlg = None

        def confirm(e):
            name = (fields["name"].value or "").strip()
            if not name:
                snack("食物名称不能为空")
                return

            data = {k: (fields[k].value or "").strip() for k in ["name", "category", "unit", "method"]}
            for k in ["base_qty", "kcal", "carb", "protein", "fat"]:
                data[k] = to_float(fields[k].value)

            if editing:
                foods[edit_index] = data
            else:
                if any(f.get("name") == name for f in foods):
                    snack("食物已存在")
                    return
                foods.append(data)

            save_json(FOOD_FILE, foods)
            close_control(dlg)
            refresh()
            snack("食物库已保存")

        content = ft.Column([
            fields["name"],
            fields["category"],
            ft.Row([fields["unit"], fields["base_qty"]], spacing=8),
            fields["method"],
            fields["kcal"],
            fields["carb"],
            fields["protein"],
            fields["fat"],
        ], width=dialog_width, height=540, spacing=10, scroll=_SCROLL_AUTO)

        dlg = dialog_base(
            "修改食物" if editing else "新增食物",
            content,
            [ft.Container(content=make_button("保存", on_click=confirm, expand=True), width=dialog_width)],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def open_supp_library_dialog(edit_index=None):
        editing = edit_index is not None
        dialog_width = 340
        item = supplements[edit_index] if editing else {"name": "", "default_amount": "", "unit": ""}
        name = mobile_text_field("补剂名称", value=str(item.get("name", "")), width=dialog_width)
        amount = mobile_text_field("默认用量", value=str(item.get("default_amount", "")), width=dialog_width)
        unit = mobile_text_field("单位", value=str(item.get("unit", "")), width=dialog_width)
        dlg = None

        def confirm(e):
            if not name.value.strip():
                snack("补剂名称不能为空")
                return
            data = {"name": name.value.strip(), "default_amount": amount.value.strip(), "unit": unit.value.strip()}
            if editing:
                supplements[edit_index] = data
            else:
                if any(s.get("name") == data["name"] for s in supplements):
                    snack("补剂已存在")
                    return
                supplements.append(data)
            save_json(SUPP_FILE, supplements)
            close_control(dlg)
            refresh()

        content = ft.Column([name, amount, unit], width=dialog_width, height=230, spacing=12)

        dlg = dialog_base(
            "修改补剂" if editing else "新增补剂",
            content,
            [ft.Container(content=make_button("保存", on_click=confirm, expand=True), width=dialog_width)],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def open_record_detail(record_date):
        rec = records.get(record_date)
        if not rec:
            return
        text = format_record_detail(rec)
        dlg = None
        content = ft.Container(ft.Text(text, size=13, selectable=True), height=500, width=340)
        dlg = dialog_base(
            f"{record_date} 详情",
            content,
            [ft.Container(content=make_button("加载到今日页", on_click=lambda e: (close_control(dlg), load_record_for_date(record_date, show=True), set_view("today")), expand=True), width=340)],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def format_record_detail(rec):
        p = rec.get("profile", {})
        total = rec.get("daily_total", {})
        comp = p.get("compliance", {})
        targets = p.get("targets", {})
        lines = []
        lines.append(f"日期：{rec.get('date','')}")
        lines.append(f"类型：{p.get('day_type','')}")
        lines.append(f"体重：{p.get('weight_kg','')} kg")
        lines.append(f"体脂率：{p.get('bodyfat_percent','')} %")
        lines.append("")
        lines.append("【达标情况】")
        lines.append(f"总体：{comp.get('status','')}")
        lines.append(f"碳水：{total.get('carb',0)}g / 目标 {targets.get('carb','')}g，{comp.get('carb_msg','')}")
        lines.append(f"蛋白：{total.get('protein',0)}g / 目标 {targets.get('protein','')}g，{comp.get('protein_msg','')}")
        lines.append(f"脂肪：{total.get('fat',0)}g / 目标 {targets.get('fat_min','')}-{targets.get('fat_max','')}g，{comp.get('fat_msg','')}")
        lines.append(f"热量：{total.get('kcal',0)} kcal / 估算目标 {comp.get('kcal_target','')}")
        lines.append(f"提示：{comp.get('warning_text','无明显超出/不足项')}")
        lines.append("")
        tr = rec.get("training", {})
        lines.append("【训练】")
        lines.append(f"总时长：{tr.get('total_duration_min','')} min")
        lines.append(f"总消耗：{tr.get('total_calories_kcal','')} kcal")
        lines.append(f"疲劳：{tr.get('fatigue_status','')}")
        for i, t in enumerate(tr.get("targets", []), 1):
            lines.append(f"{i}. {t.get('target','')} {t.get('detail','')} {t.get('note','')}")
        lines.append("")
        lines.append("【饮食】")
        meals = rec.get("meals", {})
        for meal in MEALS:
            if meals.get(meal):
                lines.append(f"{meal}：")
                for item in meals[meal]:
                    lines.append(f"- {item.get('food','')} {item.get('qty','')}{item.get('unit','')}，{item.get('kcal',0)} kcal")
        lines.append("")
        w = rec.get("water", {})
        lines.append(f"饮水：{w.get('total_ml',0)} ml，{w.get('status','')}")
        if rec.get("supplements"):
            lines.append("补剂：" + "、".join([f"{s.get('name','')} {s.get('amount','')}{s.get('unit','')}" for s in rec.get("supplements", [])]))
        sl = rec.get("sleep", {})
        if isinstance(sl, dict):
            lines.append(f"睡眠：{sl.get('bed_time','')} - {sl.get('wake_time','')}，共 {sl.get('total_text','')}")
            naps = sl.get("naps", [])
            if naps:
                lines.append("小睡：" + "、".join([f"{n.get('start','')}-{n.get('end','')}" for n in naps]))
        return "\n".join(lines)

    def delete_meal_item(meal, idx):
        try:
            state["meals"][meal].pop(idx)
            save_current()
            refresh()
        except Exception:
            pass

    def add_water(amount):
        state["water"].append(float(amount))
        save_current()
        refresh()

    def delete_water(idx):
        if 0 <= idx < len(state["water"]):
            state["water"].pop(idx)
            save_current()
            refresh()

    def delete_last_water():
        if state["water"]:
            state["water"].pop()
            save_current()
            refresh()
        else:
            snack("暂无饮水记录")

    def delete_water_amount(amount):
        try:
            remain = float(amount or 0)
        except Exception:
            remain = 0
        if remain <= 0:
            snack("请输入要删除的饮水量")
            return
        if not state["water"]:
            snack("暂无饮水记录")
            return

        while remain > 0 and state["water"]:
            last = float(state["water"][-1])
            if last <= remain + 1e-9:
                remain -= last
                state["water"].pop()
            else:
                state["water"][-1] = round(last - remain, 1)
                remain = 0

        save_current()
        refresh()

    def add_nap(start, end):
        if duration_between(start, end) <= 0:
            snack("请填写正确的小睡时间")
            return
        state.setdefault("sleep", {"bed_time": "", "wake_time": "", "naps": []})
        state["sleep"].setdefault("naps", []).append({"start": str(start or "").strip(), "end": str(end or "").strip()})
        save_current()
        refresh()

    def delete_nap(idx):
        naps = state.get("sleep", {}).get("naps", [])
        if 0 <= idx < len(naps):
            naps.pop(idx)
            save_current()
            refresh()

    def delete_training(idx):
        if 0 <= idx < len(state["training"]["targets"]):
            state["training"]["targets"].pop(idx)
            save_current()
            refresh()

    def delete_food(idx):
        if 0 <= idx < len(foods):
            foods.pop(idx)
            save_json(FOOD_FILE, foods)
            refresh()

    def delete_supp(idx):
        if 0 <= idx < len(supplements):
            name = supplements[idx].get("name")
            supplements.pop(idx)
            state["supplements"] = [s for s in state["supplements"] if s.get("name") != name]
            save_json(SUPP_FILE, supplements)
            save_current()
            refresh()

    def set_view(name):
        state["current_view"] = name
        refresh()

    # ---------- render ----------
    def render_top():
        is_today = state["date"] == date.today().isoformat()
        tag = "今日" if is_today else "历史"
        return card(ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED, icon_size=17, on_click=lambda e: shift_date(-1)),
                ft.Container(
                    content=ft.Row([
                        ft.Text(format_date_label(), size=17, weight="bold", color=TEXT),
                        ft.Container(),
                    ], alignment="center", spacing=6),
                    expand=True,
                ),
                ft.IconButton(icon=ft.Icons.CALENDAR_MONTH_OUTLINED, icon_size=19, icon_color=PRIMARY, on_click=lambda e: open_calendar_picker()),
                ft.IconButton(icon=ft.Icons.ARROW_FORWARD_IOS_ROUNDED, icon_size=17, on_click=lambda e: shift_date(1)),
            ], alignment="spaceBetween", vertical_alignment="center"),
            ft.Row([
                make_button("今日", on_click=lambda e: load_record_for_date(date.today().isoformat()), bgcolor="#E8F5E9", color=GREEN, expand=True),
                make_button("保存", on_click=lambda e: save_current(True), expand=True),
            ], spacing=8),
        ], spacing=8), padding=12, margin_bottom=8)

    def render_profile():
        targets = get_targets()
        total = daily_total()

        weight_field = mobile_text_field(label="体重 kg", value=state["weight"], keyboard_type=_KEYBOARD_NUMBER, expand=True)
        bodyfat_field = mobile_text_field(label="体脂 %", value=state["bodyfat"], keyboard_type=_KEYBOARD_NUMBER, expand=True)

        prev_info = get_previous_body_info()
        if prev_info:
            w = "" if prev_info.get("weight") is None else f"{prev_info['weight']:g} kg"
            bf = "" if prev_info.get("bodyfat") is None else f"{prev_info['bodyfat']:g}%"
            parts = []
            if prev_info.get("weight_diff") is not None:
                d = prev_info["weight_diff"]
                parts.append(f"体重 {'+' if d > 0 else ''}{d:g} kg")
            if prev_info.get("bodyfat_diff") is not None:
                d = prev_info["bodyfat_diff"]
                parts.append(f"体脂 {'+' if d > 0 else ''}{d:g}%")
            diff_text = "｜".join(parts) if parts else "暂无变化"
            diff_color = RED if ("+" in diff_text) else GREEN if "-" in diff_text else SUB
            prev_date_text = prev_info["date"]
        else:
            w = "-"
            bf = "-"
            diff_text = "保存今天记录后自动对比"
            diff_color = SUB
            prev_date_text = "-"

        def apply_profile(e=None):
            state["weight"] = weight_field.value or state["weight"]
            state["bodyfat"] = bodyfat_field.value or state["bodyfat"]
            save_current()
            refresh()
            snack("已更新基础信息")

        def set_day_type(day_type):
            state["day_type"] = day_type
            save_current()
            refresh()

        def day_type_button(day_type):
            selected = state["day_type"] == day_type
            return make_button(day_type.replace("日", ""), on_click=lambda e, d=day_type: set_day_type(d), bgcolor=PRIMARY if selected else "#E8F5E9", color="#FFFFFF" if selected else GREEN, expand=True)

        def target_box(label, value):
            value_text = ft.Text(value, size=15, weight="bold", color=TEXT, text_align="center")
            try:
                value_text.no_wrap = True
            except Exception:
                pass
            return ft.Container(
                content=ft.Column([small_text(label), value_text], horizontal_alignment="center", spacing=1),
                bgcolor="#F8FAFC",
                border_radius=8,
                padding=8,
                expand=True,
            )

        bar_width = responsive_bar_width()
        macro_bars = ft.Column([
            macro_progress_bar("碳水", total["carb"], target_min=targets["carb_min"], target_max=targets["carb_max"], kind="carb", width=bar_width),
            macro_progress_bar("蛋白", total["protein"], target_min=targets["protein_min"], target_max=targets["protein_max"], kind="protein", width=bar_width),
            macro_progress_bar("脂肪", total["fat"], target_min=targets["fat_min"], target_max=targets["fat_max"], kind="fat", width=bar_width),
        ], spacing=7)

        prev_box = ft.Container(
            content=ft.Row([
                ft.Column([small_text("上次记录"), ft.Text(f"{w} | {bf}", size=14, weight="bold", color=TEXT)], spacing=2, expand=True),
                ft.Column([small_text("变化"), ft.Text(diff_text, size=13, weight="bold", color=diff_color)], spacing=2, expand=True),
                ft.Column([small_text("日期"), ft.Text(prev_date_text, size=12, color=SUB)], spacing=2, expand=True),
            ], spacing=8, alignment="spaceBetween", vertical_alignment="center"),
            bgcolor="#F8FAFC",
            border_radius=8,
            padding=12,
        )

        return card(ft.Column([
            ft.Row([section_title("基础信息 / 目标"), make_button("更新", on_click=apply_profile, bgcolor="#E8F5E9", color=GREEN)], alignment="spaceBetween"),
            ft.Row([weight_field, bodyfat_field], spacing=8),
            prev_box,
            ft.Row([day_type_button("高碳日"), day_type_button("中碳日"), day_type_button("低碳日")], spacing=7),
            ft.Row([
                target_box("碳水", compact_range_text(targets["carb_min"], targets["carb_max"])),
                target_box("蛋白", compact_range_text(targets["protein_min"], targets["protein_max"])),
                target_box("脂肪", compact_range_text(targets["fat_min"], targets["fat_max"]))
            ], spacing=7),
            macro_bars,
        ], spacing=8))

    def render_diet():
        total = daily_total()
        selected_meal = state.get("selected_meal", "汇总")

        def set_selected_meal(meal):
            state["selected_meal"] = meal
            refresh()

        def meal_count(meal):
            if meal == "汇总":
                return sum(len(state["meals"].get(m, [])) for m in MEALS)
            return len(state["meals"].get(meal, []))

        def meal_button(meal):
            selected = selected_meal == meal
            count = meal_count(meal)
            label = meal if count == 0 else f"{meal} {count}"
            return ft.Container(content=ft.Text(label, size=12, weight="bold", color="#FFFFFF" if selected else GREEN, text_align="center"), bgcolor=PRIMARY if selected else "#E8F5E9", border_radius=15, padding=8, expand=True, on_click=lambda e, m=meal: set_selected_meal(m))

        def meal_totals(meal):
            t = {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}
            for item in state["meals"].get(meal, []):
                for k in t:
                    t[k] += to_float(item.get(k))
            return {k: round(v, 1) for k, v in t.items()}

        content_rows = []
        if selected_meal == "汇总":
            any_record = False
            for meal in MEALS:
                items = state["meals"].get(meal, [])
                if not items:
                    continue
                any_record = True
                mt = meal_totals(meal)
                names = "、".join([str(x.get("food", "")) for x in items[:3]])
                if len(items) > 3:
                    names += "…"
                content_rows.append(ft.Container(content=ft.Column([
                    ft.Row([ft.Text(meal, size=13, weight="bold", color=TEXT), small_text(f"{mt['kcal']} kcal｜碳{mt['carb']} 蛋{mt['protein']} 脂{mt['fat']}")], alignment="spaceBetween"),
                    ft.Text(names, size=11, color=SUB) if names else ft.Container(),
                ], spacing=2), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))
            if not any_record:
                content_rows.append(ft.Container(content=small_text("暂无饮食记录"), bgcolor="#FAFAFA", border_radius=12, padding=10))
            header_right = f"{total['kcal']} kcal｜碳 {total['carb']}g｜蛋白 {total['protein']}g｜脂肪 {total['fat']}g"
        else:
            meal_items = state["meals"].get(selected_meal, [])
            mt = meal_totals(selected_meal)
            header_right = f"{mt['kcal']} kcal｜碳 {mt['carb']}g｜蛋白 {mt['protein']}g｜脂肪 {mt['fat']}g"
            if meal_items:
                for idx, item in enumerate(meal_items):
                    content_rows.append(ft.Container(content=ft.Row([
                        ft.Column([ft.Text(f"{item.get('food')} {item.get('qty')}{item.get('unit')}", size=13, weight="bold", color=TEXT), small_text(f"{item.get('kcal')} kcal｜碳 {item.get('carb')}｜蛋 {item.get('protein')}｜脂 {item.get('fat')}")], expand=True, spacing=2),
                        ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, icon_size=18, on_click=lambda e, m=selected_meal, i=idx: delete_meal_item(m, i)),
                    ], alignment="spaceBetween"), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))
            else:
                content_rows.append(ft.Container(content=small_text("暂无记录"), bgcolor="#FAFAFA", border_radius=12, padding=10))

        return card(ft.Column([
            ft.Row([section_title("饮食记录"), make_button("添加", on_click=lambda e, m=("早餐" if selected_meal=="汇总" else selected_meal): open_add_food_dialog(m), icon=ft.Icons.ADD, expand=False)], alignment="spaceBetween"),
            ft.Row([meal_button("汇总"), meal_button("早餐"), meal_button("午餐")], spacing=6),
            ft.Row([meal_button("晚餐"), meal_button("练后"), meal_button("偷吃")], spacing=6),
            ft.Container(content=ft.Column([ft.Row([ft.Text(selected_meal, size=13, weight="bold", color=TEXT), small_text(header_right)], alignment="spaceBetween"), ft.Column(content_rows, spacing=1)], spacing=6), bgcolor="#FFFFFF", border_radius=8, padding=8),
        ], spacing=8))

    def render_training():
        tr = state["training"]
        target_controls = []
        for idx, t in enumerate(tr.get("targets", [])):
            target_controls.append(ft.Container(content=ft.Row([
                ft.Column([ft.Text(f"{t.get('target','')}", size=13, weight="bold"), small_text(f"{t.get('detail','')}" + (f"｜{t.get('note','')}" if t.get("note") else ""))], expand=True, spacing=1),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, icon_size=18, on_click=lambda e, i=idx: delete_training(i)),
            ]), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))
        if not target_controls:
            target_controls.append(ft.Container(content=small_text("暂无训练目标"), bgcolor="#FAFAFA", border_radius=12, padding=10))

        duration_field = mobile_text_field(label="时长 min", value=tr.get("total_duration_min", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True, on_change=lambda e: (tr.update({"total_duration_min": e.control.value}), save_current()))
        calories_field = mobile_text_field(label="消耗 kcal", value=tr.get("total_calories_kcal", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True, on_change=lambda e: (tr.update({"total_calories_kcal": e.control.value}), save_current()))
        note_field = mobile_text_field(label="训练备注", value=tr.get("summary_note", ""), expand=True, on_change=lambda e: (tr.update({"summary_note": e.control.value}), save_current()))
        fatigue_dd = mobile_dropdown(label="状态", value=tr.get("fatigue_status", "状态一般"), options=[ft.dropdown.Option(x) for x in FATIGUE_OPTIONS], on_change=lambda e: (tr.update({"fatigue_status": e.control.value}), save_current(), refresh()), expand=True)

        return card(ft.Column([
            ft.Row([section_title("训练记录"), make_button("添加", on_click=lambda e: open_training_dialog(), icon=ft.Icons.ADD)], alignment="spaceBetween"),
            ft.Row([duration_field, calories_field], spacing=8),
            note_field,
            fatigue_dd,
            ft.Column(target_controls, spacing=2),
        ], spacing=8))

    def _split_time_parts(value, default_hour="23", default_minute="00"):
        text = str(value or "").strip()
        if ":" in text:
            hh, mm = text.split(":", 1)
            if hh.isdigit() and mm.isdigit():
                return hh.zfill(2), mm.zfill(2)
        return default_hour, default_minute

    def _build_time_value(hour_value, minute_value):
        return f"{str(hour_value or '00').zfill(2)}:{str(minute_value or '00').zfill(2)}"

    def time_display_button(text, on_click):
        return ft.Container(
            content=ft.Text(text or "选择时间", size=20, weight="bold", color=TEXT, text_align="center"),
            bgcolor="#FAFAFA",
            border_radius=8,
            padding=14,
            on_click=on_click,
        )

    def time_line(label, value, on_click):
        return ft.Container(
            content=ft.Row([
                ft.Text(label, size=13, color=TEXT, weight="bold"),
                ft.Container(content=time_display_button(value, on_click), expand=True),
            ], spacing=12, vertical_alignment="center"),
            bgcolor="#FFFFFF",
            border_radius=8,
            padding=6,
        )

    def open_time_wheel(title, current_value, default_hour, default_minute, on_save):
        selected = {"hour": default_hour, "minute": default_minute}
        selected["hour"], selected["minute"] = _split_time_parts(current_value, default_hour, default_minute)

        dlg = None
        hour_col = ft.Column(spacing=4, scroll=_SCROLL_AUTO)
        minute_col = ft.Column(spacing=4, scroll=_SCROLL_AUTO)

        def option_cell(value, kind):
            active = selected[kind] == value
            return ft.Container(
                content=ft.Text(value, size=20, weight="bold" if active else "normal", color=PRIMARY if active else TEXT, text_align="center"),
                bgcolor="#E8F5E9" if active else "#FFFFFF",
                border_radius=8,
                padding=12,
                on_click=lambda e, v=value, k=kind: choose(k, v),
            )

        def rebuild():
            hour_col.controls.clear()
            minute_col.controls.clear()
            for i in range(24):
                hour_col.controls.append(option_cell(f"{i:02d}", "hour"))
            for i in range(60):
                minute_col.controls.append(option_cell(f"{i:02d}", "minute"))

        def choose(kind, value):
            selected[kind] = value
            rebuild()
            page.update()

        def confirm(e=None):
            on_save(_build_time_value(selected["hour"], selected["minute"]))
            close_control(dlg)

        rebuild()

        content = ft.Column([
            ft.Row([
                ft.Container(content=ft.Column([small_text("时"), ft.Container(content=hour_col, height=380)], spacing=4), expand=True),
                ft.Container(content=ft.Column([small_text("分"), ft.Container(content=minute_col, height=380)], spacing=4), expand=True),
            ], spacing=12),
        ], width=360, height=430, spacing=8)

        dlg = dialog_base(
            title,
            content,
            [ft.Container(content=make_button("确定", on_click=confirm, expand=True), width=360)],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def render_sleep():
        sl = state.setdefault("sleep", {"bed_time": "", "wake_time": "", "naps": []})

        nap_temp = state.setdefault("sleep_temp", {
            "nap_start": "13:00",
            "nap_end": "14:00",
        })

        def save_bed(value):
            sl["bed_time"] = value
            save_current()
            refresh()

        def save_wake(value):
            sl["wake_time"] = value
            save_current()
            refresh()

        def set_nap_start(value):
            nap_temp["nap_start"] = value
            refresh()

        def set_nap_end(value):
            nap_temp["nap_end"] = value
            refresh()

        def add_nap_from_current(e=None):
            add_nap(nap_temp.get("nap_start", "13:00"), nap_temp.get("nap_end", "14:00"))

        nap_rows = []
        for idx, nap in enumerate(sl.get("naps", [])):
            mins = duration_between(nap.get("start", ""), nap.get("end", ""))
            nap_rows.append(ft.Container(content=ft.Row([
                ft.Text(f"{nap.get('start','')} - {nap.get('end','')}", size=13, color=TEXT),
                ft.Row([
                    small_text(format_minutes(mins)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=RED, on_click=lambda e, i=idx: delete_nap(i)),
                ], spacing=4),
            ], alignment="spaceBetween"), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))

        if not nap_rows:
            nap_rows.append(ft.Container(content=small_text("暂无小睡记录"), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))

        total_minutes = sleep_total_minutes()
        total_text = format_minutes(total_minutes)

        return card(ft.Column([
            ft.Row([section_title("睡眠记录"), ft.Text(total_text, size=20, weight="bold", color=SKY_BLUE if total_minutes >= 420 else TEXT)], alignment="spaceBetween"),
            small_text("夜间睡眠"),
            time_line("入睡", sl.get("bed_time", "") or "23:00", lambda e: open_time_wheel("选择入睡时间", sl.get("bed_time", "23:00"), "23", "00", save_bed)),
            time_line("起床", sl.get("wake_time", "") or "07:00", lambda e: open_time_wheel("选择起床时间", sl.get("wake_time", "07:00"), "07", "00", save_wake)),
            small_text("小睡时间"),
            time_line("开始", nap_temp.get("nap_start", "13:00"), lambda e: open_time_wheel("选择小睡开始", nap_temp.get("nap_start", "13:00"), "13", "00", set_nap_start)),
            time_line("结束", nap_temp.get("nap_end", "14:00"), lambda e: open_time_wheel("选择小睡结束", nap_temp.get("nap_end", "14:00"), "14", "00", set_nap_end)),
            make_button("添加小睡", on_click=add_nap_from_current, expand=True),
            ft.Column(nap_rows, spacing=0),
        ], spacing=10))

    def render_water():
        water_total = int(sum(state["water"]))
        custom_water = plain_number_field(value="250", width=114, keyboard_type=_KEYBOARD_NUMBER, height=48)

        input_box = ft.Row([
            ft.Container(content=custom_water, width=114, ),
            ft.Text("ml", size=16, color=SUB, weight="bold"),
        ], spacing=6, vertical_alignment="center")

        return card(ft.Column([
            ft.Row([section_title("饮水记录"), small_text("目标 2000 ml")], alignment="spaceBetween"),
            ft.Row([
                ft.Text(f"{water_total} ml", size=22, weight="bold", color=SKY_BLUE if water_total >= 2000 else GREEN),
                make_button("+250", on_click=lambda e: add_water(250), bgcolor="#E8F5E9", color=GREEN),
                make_button("+375", on_click=lambda e: add_water(375), bgcolor="#E8F5E9", color=GREEN),
                make_button("+500", on_click=lambda e: add_water(500), bgcolor="#E8F5E9", color=GREEN),
            ], alignment="spaceBetween"),
            water_progress_bar(water_total, 2000, width=responsive_bar_width()),
            ft.Row([
                input_box,
                make_button("记录", on_click=lambda e: add_water(to_float(custom_water.value, 250)), expand=True),
                make_button("删除", on_click=lambda e: delete_water_amount(to_float(custom_water.value, 250)), bgcolor="#FDECEC", color=RED, expand=True),
            ], spacing=8, vertical_alignment="center"),
        ], spacing=10))

    def render_supp_today():
        supp_controls = []
        selected_map = {s.get("name"): s for s in state["supplements"]}

        for supp in supplements:
            name = supp.get("name", "")
            checked = name in selected_map
            amount_value = selected_map.get(name, {}).get("amount", supp.get("default_amount", ""))

            cb = ft.Checkbox(value=checked)
            amount = plain_number_field(value=str(amount_value), width=84, height=44)

            def on_change(e=None, s=supp, amount_field=amount, cb_ref=cb):
                existing = [x for x in state["supplements"] if x.get("name") != s.get("name")]
                if cb_ref.value:
                    existing.append({"name": s.get("name"), "amount": amount_field.value, "unit": s.get("unit", "")})
                state["supplements"] = existing
                save_current()
                refresh()

            cb.on_change = on_change
            amount.on_change = on_change

            bg = "#EDF9F4" if checked else "#FAFAFA"
            supp_controls.append(ft.Container(content=ft.Row([
                ft.Container(width=4, height=42, bgcolor=PRIMARY if checked else "#DDDDDD", border_radius=3),
                ft.Row([cb], width=34),
                ft.Text(name, size=13, weight="bold", color=TEXT, expand=True),
                amount,
                ft.Text(supp.get("unit", ""), size=15, color=SUB, weight="bold"),
            ], alignment="spaceBetween", vertical_alignment="center", spacing=8), bgcolor=bg, border_radius=8, padding=8, margin=3))

        if not supp_controls:
            supp_controls.append(ft.Container(content=small_text("暂无补剂"), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))

        selected_count = len(state["supplements"])
        return card(ft.Column([
            ft.Row([ft.Text(f"补剂记录 {selected_count}", size=15, weight="bold"), make_button("管理", on_click=lambda e: set_view("supplements"), bgcolor="#E8F5E9", color=GREEN)], alignment="spaceBetween"),
            ft.Column(supp_controls, spacing=2),
        ], spacing=8))

    def render_food_library():
        search = ft.TextField(label="搜索食物", value="", width=360)
        list_box = ft.Column(spacing=4)

        def rebuild_list(e=None):
            kw = (search.value or "").strip().lower()
            list_box.controls.clear()
            filtered = [(i, f) for i, f in enumerate(foods) if not kw or kw in f.get("name", "").lower() or kw in f.get("category", "").lower()]
            for idx, f in filtered:
                list_box.controls.append(card(ft.Row([
                    ft.Column([
                        ft.Text(f"{f.get('name')}｜{f.get('category')}", size=14, weight="bold"),
                        small_text(f"{f.get('method')}｜基准 {f.get('base_qty')}{f.get('unit')}｜{f.get('kcal')} kcal｜碳 {f.get('carb')} 蛋白 {f.get('protein')} 脂肪 {f.get('fat')}")
                    ], expand=True, spacing=2),
                    ft.IconButton(icon=ft.Icons.EDIT, icon_color=PRIMARY, on_click=lambda e, i=idx: open_food_library_dialog(i)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, on_click=lambda e, i=idx: delete_food(i)),
                ]), padding=10, margin_bottom=6))
            page.update()

        search.on_change = rebuild_list
        rebuild_list()
        return ft.Column([
            card(ft.Row([section_title("食物库"), make_button("新增", on_click=lambda e: open_food_library_dialog(), icon=ft.Icons.ADD)], alignment="spaceBetween")),
            card(search, padding=10),
            list_box,
        ], spacing=0)

    def render_supp_library():
        controls = []
        for idx, s in enumerate(supplements):
            controls.append(card(ft.Row([
                ft.Column([ft.Text(s.get("name", ""), size=14, weight="bold"), small_text(f"默认：{s.get('default_amount','')}{s.get('unit','')}")], expand=True),
                ft.IconButton(icon=ft.Icons.EDIT, icon_color=PRIMARY, on_click=lambda e, i=idx: open_supp_library_dialog(i)),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, on_click=lambda e, i=idx: delete_supp(i)),
            ]), padding=10, margin_bottom=6))
        return ft.Column([
            card(ft.Row([section_title("补剂库"), make_button("新增", on_click=lambda e: open_supp_library_dialog(), icon=ft.Icons.ADD)], alignment="spaceBetween")),
            ft.Column(controls, spacing=0),
        ])

    def render_me():
        targets = get_targets()

        weight_box, weight_field = labeled_plain_field("体重 kg", state.get("weight", "62.5"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        bodyfat_box, bodyfat_field = labeled_plain_field("体脂 %", state.get("bodyfat", "13"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        height_box, height_field = labeled_plain_field("身高 cm", state.get("height", "170"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        age_box, age_field = labeled_plain_field("年龄", state.get("age", "30"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        waist_box, waist_field = labeled_plain_field("腰围 cm", state.get("waist_cm", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        arm_box, arm_field = labeled_plain_field("臂围 cm", state.get("arm_cm", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)

        def persist_profile(weight_value=None, bodyfat_value=None, height_value=None, age_value=None, sex_value=None, habit_value=None, waist_value=None, arm_value=None):
            state["weight"] = weight_value if weight_value is not None else state.get("weight", "62.5")
            state["bodyfat"] = bodyfat_value if bodyfat_value is not None else state.get("bodyfat", "13")
            state["height"] = height_value if height_value is not None else state.get("height", "170")
            state["age"] = age_value if age_value is not None else state.get("age", "30")
            state["sex"] = sex_value if sex_value is not None else state.get("sex", "男")
            state["activity_habit"] = habit_value if habit_value is not None else state.get("activity_habit", "规律训练")
            state["waist_cm"] = waist_value if waist_value is not None else state.get("waist_cm", "")
            state["arm_cm"] = arm_value if arm_value is not None else state.get("arm_cm", "")
            state["profile_inited"] = True
            save_user_profile({
                "height": state["height"],
                "age": state["age"],
                "sex": state["sex"],
                "activity_habit": state["activity_habit"],
                "waist_cm": state["waist_cm"],
                "arm_cm": state["arm_cm"],
                "profile_inited": True,
            })
            save_current()

        def save_profile_fields(e=None):
            persist_profile(
                weight_value=weight_field.value or state.get("weight", "62.5"),
                bodyfat_value=bodyfat_field.value or state.get("bodyfat", "13"),
                height_value=height_field.value or state.get("height", "170"),
                age_value=age_field.value or state.get("age", "30"),
                waist_value=waist_field.value or "",
                arm_value=arm_field.value or "",
            )
            refresh()
            snack("已保存个人信息")

        def set_sex(value):
            persist_profile(
                weight_value=weight_field.value or state.get("weight", "62.5"),
                bodyfat_value=bodyfat_field.value or state.get("bodyfat", "13"),
                height_value=height_field.value or state.get("height", "170"),
                age_value=age_field.value or state.get("age", "30"),
                sex_value=value,
                waist_value=waist_field.value or "",
                arm_value=arm_field.value or "",
            )
            refresh()

        def set_activity(value):
            persist_profile(
                weight_value=weight_field.value or state.get("weight", "62.5"),
                bodyfat_value=bodyfat_field.value or state.get("bodyfat", "13"),
                height_value=height_field.value or state.get("height", "170"),
                age_value=age_field.value or state.get("age", "30"),
                habit_value=value,
                waist_value=waist_field.value or "",
                arm_value=arm_field.value or "",
            )
            refresh()

        def option_button(label, current, setter):
            selected = current == label
            return make_button(label, on_click=lambda e, v=label: setter(v), bgcolor=PRIMARY if selected else "#E8F5E9", color="#FFFFFF" if selected else GREEN, expand=True)

        info_box = ft.Container(
            content=ft.Column([
                ft.Row([small_text("去脂体重"), ft.Text(f"{targets['lean_mass']} kg", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
                ft.Row([small_text("BMR"), ft.Text(f"{int(targets['bmr'])} kcal", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
                ft.Row([small_text("TDEE"), ft.Text(f"≈ {int(targets['tdee'])} kcal", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
                ft.Row([small_text("活动系数"), ft.Text(f"{targets['activity_factor']}", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
                ft.Row([small_text("目标热量"), ft.Text(f"{int(targets['calorie_target'])} kcal", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
            ], spacing=6),
            bgcolor="#F8FAFC",
            border_radius=8,
            padding=12,
        )

        return card(ft.Column([
            ft.Row([section_title("我"), make_button("保存", on_click=save_profile_fields, bgcolor="#E8F5E9", color=GREEN)], alignment="spaceBetween"),
            ft.Row([weight_box, bodyfat_box], spacing=8),
            ft.Row([height_box, age_box], spacing=8),
            ft.Row([waist_box, arm_box], spacing=8),
            small_text("性别"),
            ft.Row([
                option_button("男", state.get("sex", "男"), set_sex),
                option_button("女", state.get("sex", "男"), set_sex),
            ], spacing=8),
            small_text("运动习惯"),
            ft.Row([
                option_button("久坐少动", state.get("activity_habit", "规律训练"), set_activity),
                option_button("偶尔运动", state.get("activity_habit", "规律训练"), set_activity),
            ], spacing=8),
            ft.Row([
                option_button("规律训练", state.get("activity_habit", "规律训练"), set_activity),
                option_button("高频训练", state.get("activity_habit", "规律训练"), set_activity),
            ], spacing=8),
            info_box,
            ft.Container(content=small_text("腰围、臂围只做记录，不参与碳循环公式。今日页仍保留体重、体脂，方便每日更新。"), bgcolor="#FAFAFA", border_radius=8, padding=10),
        ], spacing=10))

    def render_history():
        records_local = load_json(RECORD_FILE, {})
        keys = sorted(records_local.keys(), reverse=True)
        controls = []
        if not keys:
            controls.append(card(small_text("暂无历史记录")))
        for d in keys:
            rec = records_local[d]
            p = rec.get("profile", {})
            total = rec.get("daily_total", {})
            comp = p.get("compliance", {})
            controls.append(card(ft.Row([
                ft.Column([
                    ft.Text(f"{d}｜{p.get('day_type','')}", size=14, weight="bold"),
                    small_text(f"{comp.get('status','')}｜{total.get('kcal',0)} kcal｜碳 {total.get('carb',0)} 蛋白 {total.get('protein',0)} 脂肪 {total.get('fat',0)}"),
                    small_text(f"体重 {p.get('weight_kg','')} kg｜体脂 {p.get('bodyfat_percent','')}%")
                ], expand=True, spacing=2),
                ft.Row([
                    ft.IconButton(icon=ft.Icons.DESCRIPTION_OUTLINED, icon_color=PRIMARY, on_click=lambda e, x=d: open_record_detail(x)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, on_click=lambda e, x=d: delete_history_record(x)),
                ], spacing=0),
            ]), padding=10, margin_bottom=6))
        return ft.Column([
            card(ft.Row([section_title("历史记录"), make_button("刷新", on_click=lambda e: refresh(), bgcolor="#E8F5E9", color=GREEN)], alignment="spaceBetween")),
            ft.Column(controls, spacing=0)
        ])

    def render_nav():
        items = [
            ("today", "今日", ft.Icons.TODAY),
            ("foods", "食物", ft.Icons.RESTAURANT_MENU),
            ("supplements", "补剂", ft.Icons.MEDICATION_OUTLINED),
            ("history", "历史", ft.Icons.HISTORY),
            ("me", "我", ft.Icons.PERSON_OUTLINE),
        ]

        tabs = []
        for key, label, icon in items:
            selected = state["current_view"] == key
            tabs.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(icon, size=22, color=PRIMARY if selected else SUB),
                        ft.Text(label, size=11, color=PRIMARY if selected else SUB, weight="bold" if selected else "normal"),
                    ], horizontal_alignment="center", spacing=2),
                    on_click=lambda e, k=key: set_view(k),
                    expand=True,
                    padding=6,
                    bgcolor="#FFFFFF",
                )
            )

        return ft.Container(
            content=ft.Row(tabs, spacing=0, alignment="spaceAround"),
            padding=6,
            bgcolor="#FFFFFF",
            
        )

    main_column = ft.Column(spacing=0, scroll=_SCROLL_AUTO, expand=True)
    nav_holder = ft.Container(bgcolor="#FFFFFF")

    def refresh_soft():
        # Used for text field change where a full rebuild while typing is disruptive.
        save_current()
        targets = get_targets()
        page.update()

    def refresh():
        main_column.controls.clear()
        view = state["current_view"]
        if view == "today":
            main_column.controls.extend([render_profile(), render_diet(), render_training(), render_water(), render_supp_today(), render_sleep(), render_top(), ft.Container(height=8)])
        elif view == "foods":
            main_column.controls.extend([render_food_library(), ft.Container(height=12)])
        elif view == "supplements":
            main_column.controls.extend([render_supp_library(), ft.Container(height=12)])
        elif view == "history":
            main_column.controls.extend([render_history(), ft.Container(height=12)])
        elif view == "me":
            main_column.controls.extend([render_me(), ft.Container(height=12)])
        nav_holder.content = render_nav()
        page.update()

    # Root layout:
    # - body_container expands and owns the vertical scroll
    # - nav_holder is outside body_container, so it stays fixed at the bottom
    body_container = ft.Container(content=main_column, padding=0, expand=True)
    root_layout = ft.Column(
        controls=[body_container, nav_holder],
        spacing=0,
        expand=True,
    )

    try:
        page.add(ft.SafeArea(content=root_layout, expand=True))
    except Exception:
        page.add(root_layout)

    def on_page_resize(e=None):
        # Rebuild progress bars after dragging the window border.
        try:
            refresh()
        except Exception:
            pass

    try:
        page.on_resize = on_page_resize
    except Exception:
        pass

    def open_first_profile_dialog():
        if state.get("profile_inited"):
            return

        dialog_width = 340
        weight_box, weight_field = labeled_plain_field("体重 kg", state.get("weight", "62.5"), keyboard_type=_KEYBOARD_NUMBER, width=dialog_width)
        bodyfat_box, bodyfat_field = labeled_plain_field("体脂 %", state.get("bodyfat", "13"), keyboard_type=_KEYBOARD_NUMBER, width=dialog_width)
        height_box, height_field = labeled_plain_field("身高 cm", state.get("height", "170"), keyboard_type=_KEYBOARD_NUMBER, width=dialog_width)
        age_box, age_field = labeled_plain_field("年龄", state.get("age", "30"), keyboard_type=_KEYBOARD_NUMBER, width=dialog_width)
        waist_box, waist_field = labeled_plain_field("腰围 cm", state.get("waist_cm", ""), keyboard_type=_KEYBOARD_NUMBER, width=dialog_width)
        arm_box, arm_field = labeled_plain_field("臂围 cm", state.get("arm_cm", ""), keyboard_type=_KEYBOARD_NUMBER, width=dialog_width)

        selected = {
            "sex": state.get("sex", "男"),
            "activity_habit": state.get("activity_habit", "规律训练"),
        }

        sex_row = ft.Row(spacing=8)
        act_row1 = ft.Row(spacing=8)
        act_row2 = ft.Row(spacing=8)

        def rebuild_buttons():
            sex_row.controls.clear()
            act_row1.controls.clear()
            act_row2.controls.clear()

            def btn(label, group):
                current = selected[group] == label
                return make_button(label, on_click=lambda e, l=label, g=group: choose(g, l), bgcolor=PRIMARY if current else "#E8F5E9", color="#FFFFFF" if current else GREEN, expand=True)

            sex_row.controls.extend([btn("男", "sex"), btn("女", "sex")])
            act_row1.controls.extend([btn("久坐少动", "activity_habit"), btn("偶尔运动", "activity_habit")])
            act_row2.controls.extend([btn("规律训练", "activity_habit"), btn("高频训练", "activity_habit")])

        def choose(group, value):
            selected[group] = value
            rebuild_buttons()
            page.update()

        rebuild_buttons()
        dlg = None

        def confirm(e=None):
            state["weight"] = weight_field.value or state.get("weight", "62.5")
            state["bodyfat"] = bodyfat_field.value or state.get("bodyfat", "13")
            state["height"] = height_field.value or "170"
            state["age"] = age_field.value or "30"
            state["waist_cm"] = waist_field.value or ""
            state["arm_cm"] = arm_field.value or ""
            state["sex"] = selected["sex"]
            state["activity_habit"] = selected["activity_habit"]
            state["profile_inited"] = True
            save_user_profile({
                "height": state["height"],
                "age": state["age"],
                "sex": state["sex"],
                "activity_habit": state["activity_habit"],
                "waist_cm": state["waist_cm"],
                "arm_cm": state["arm_cm"],
                "profile_inited": True,
            })
            save_current()
            close_control(dlg)
            refresh()
            snack("个人信息已保存")

        content = ft.Column([
            small_text("首次使用需要填写这些信息，用于计算 BMR/TDEE 和碳循环目标。以后可在底部“我”里修改。"),
            weight_box,
            bodyfat_box,
            height_box,
            age_box,
            waist_box,
            arm_box,
            small_text("性别"),
            sex_row,
            small_text("运动习惯"),
            act_row1,
            act_row2,
        ], width=dialog_width, height=460, spacing=10, scroll=_SCROLL_AUTO)

        title_row = ft.Row([ft.Text("完善个人信息", size=18, weight="bold", color=TEXT, expand=True)], spacing=6)
        dlg = ft.AlertDialog(
            title=title_row,
            content=content,
            actions=[ft.Container(content=make_button("开始使用", on_click=confirm, expand=True), width=dialog_width)],
            actions_alignment=ft.MainAxisAlignment.CENTER,
        )
        open_control(dlg)

    # Auto load today if saved; otherwise blank default.
    load_record_for_date(date.today().isoformat(), autosave=False, show=False)
    refresh()
    open_first_profile_dialog()

if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(main)

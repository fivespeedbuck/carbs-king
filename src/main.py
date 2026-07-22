# -*- coding: utf-8 -*-
import json
import os
import shutil
import sys
import datetime
import asyncio
import re
import uuid
from collections import Counter
from pathlib import Path
from datetime import date
import flet as ft

from analytics_service import make_body_measurement, normalize_body_measurement, summarize_daily_training
from achievement_service import evaluate_achievements
from achievement_views import achievement_view_models
from analytics_views import DataPageConfig, build_data_page_view
from diet_service import DietViewState, diet_route_for_view, normalize_diet_view
from diet_views import DietShellRenderers, build_diet_shell
from exercise_library import EXERCISE_CATEGORIES, EXERCISE_LIBRARY, get_exercise, search_exercises
from rest_notification import RestNotifier
from training_experience_service import (
    BODY_PART_ORDER,
    adjust_rest_cycle,
    copy_whole_session,
    exercise_usage_stats,
    finish_rest_cycle,
    history_training_cards,
    pause_rest_cycle,
    rest_remaining_seconds,
    resume_rest_cycle,
    skip_rest_cycle,
    sort_exercises,
    start_rest_cycle,
    undo_completed_set,
    undo_completed_set_result,
)
from training_models import SessionExercise, TrainingSession, TrainingSet
from training_service import (
    append_session_once,
    completed_set_count,
    find_active_daily_session,
    is_rapid_repeat,
    migrate_legacy_training,
    planned_set_count,
    recommend_carb_day,
    raw_training_sessions,
    session_progress,
    session_completion_state,
    session_summary_title,
    session_volume,
)

APP_NAME = "碳水大王"
APP_VERSION = "1.2.0"
MEALS = ["早餐", "午餐", "晚餐", "练前", "练后", "偷吃"]

DAY_TYPES = {
    # 碳水按当前体重 g/kg 计算，再按体脂、年龄做轻微修正。
    # interval 为上下容差，避免区间过宽。
    "高碳日": {"calorie_factor": 0.80, "carb_gkg": 2.90, "carb_interval": 15, "fat_gkg_min": 0.70, "fat_gkg_max": 0.85},
    "中碳日": {"calorie_factor": 0.72, "carb_gkg": 2.30, "carb_interval": 12, "fat_gkg_min": 0.80, "fat_gkg_max": 0.95},
    "低碳日": {"calorie_factor": 0.65, "carb_gkg": 1.40, "carb_interval": 10, "fat_gkg_min": 0.95, "fat_gkg_max": 1.10},
}

# 自定义模式使用一个中心倍数，仍沿用自动模式的合理上下浮动范围：
# 碳水、脂肪按当前体重计算，蛋白质按去脂体重计算。
DEFAULT_MACRO_MULTIPLIERS = {
    "高碳日": {"carb": 2.90, "protein": 2.15, "fat": 0.78},
    "中碳日": {"carb": 2.30, "protein": 2.15, "fat": 0.88},
    "低碳日": {"carb": 1.40, "protein": 2.15, "fat": 1.02},
}

TRAINING_TARGETS = ["胸", "背", "肩", "腿", "手臂", "腹", "爬坡", "跑步", "徒步", "游泳", "骑行", "打球", "休息", "其他"]
ABS_ACTIONS = ["仰卧抬腿", "悬垂举腿", "卷腹", "平板支撑", "其他"]
FATIGUE_OPTIONS = ["状态好", "状态一般", "状态差"]
INTENSITY_OPTIONS = ["恢复", "中等", "高强度"]

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

BG = "#F4F7F6"
CARD = "#FFFFFF"
PRIMARY = "#116E59"
PRIMARY_SOFT = "#F1F7F5"
TEXT = "#182420"
SUB = "#4F5D58"
RED = "#B83A3A"
ORANGE = "#B96A18"
GREEN = "#155A43"
SKY_BLUE = "#277EA8"
BAR_BG = "#E4EAE8"
YELLOW = "#B98518"
BORDER = "#CDD9D5"
SURFACE = "#F7FAF9"


class LabeledInput(ft.Column):
    """Keep labels above inputs so they never collide with the field border."""

    def __init__(self, label, field, width=None, expand=False):
        self.label_control = ft.Text(label, size=12, color=SUB, weight="bold", max_lines=1, overflow="ellipsis")
        super().__init__(
            controls=[
                ft.Container(
                    content=self.label_control,
                    height=18,
                    alignment=ft.Alignment.CENTER_LEFT,
                ),
                field,
            ],
            spacing=4,
            width=width,
            expand=expand,
        )
        self.field = field

    @property
    def label(self):
        return self.label_control.value

    @label.setter
    def label(self, value):
        self.label_control.value = value

    @property
    def label_text(self):
        return self.label_control.value

    @label_text.setter
    def label_text(self, value):
        self.label_control.value = value

    @property
    def value(self):
        return self.field.value

    @value.setter
    def value(self, value):
        self.field.value = value

    @property
    def on_change(self):
        return self.field.on_change

    @on_change.setter
    def on_change(self, handler):
        self.field.on_change = handler

    @property
    def on_blur(self):
        return self.field.on_blur

    @on_blur.setter
    def on_blur(self, handler):
        self.field.on_blur = handler

    @property
    def on_submit(self):
        return self.field.on_submit

    @on_submit.setter
    def on_submit(self, handler):
        self.field.on_submit = handler

    @property
    def options(self):
        return self.field.options

    @options.setter
    def options(self, value):
        self.field.options = value


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

DATA_FILENAMES = [
    "food_library.json",
    "supplement_library.json",
    "daily_records.json",
    "user_profile.json",
    "training_data.json",
]

def get_app_dir() -> Path:
    """Use Flet's update-safe data directory, with source-run fallbacks."""
    explicit_data_dir = os.environ.get("CARBS_KING_DATA_DIR", "").strip()
    if explicit_data_dir:
        app_dir = Path(explicit_data_dir)
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir

    candidates = []
    flet_storage = os.environ.get("FLET_APP_STORAGE_DATA", "").strip()
    if flet_storage:
        candidates.append(Path(flet_storage))
    if sys.platform.startswith("win"):
        candidates.append(Path(os.environ.get("APPDATA", str(Path.home()))) / "CarbCycleRecorderMobile")
    else:
        candidates.append(Path.home() / ".carb_cycle_recorder_mobile")

    for app_dir in candidates:
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
            return app_dir
        except Exception:
            continue
    return SCRIPT_DIR

APP_DIR = get_app_dir()
FOOD_FILE = APP_DIR / "food_library.json"
SUPP_FILE = APP_DIR / "supplement_library.json"
RECORD_FILE = APP_DIR / "daily_records.json"
PROFILE_FILE = APP_DIR / "user_profile.json"
TRAINING_FILE = APP_DIR / "training_data.json"

def migrate_legacy_data():
    """Move older-build data into Flet's persistent directory once."""
    if os.environ.get("CARBS_KING_DATA_DIR", "").strip():
        return

    legacy_dirs = [SCRIPT_DIR]
    try:
        legacy_dirs.append(Path.home() / ".carb_cycle_recorder_mobile")
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:
            legacy_dirs.append(Path(os.environ.get("APPDATA", str(Path.home()))) / "CarbCycleRecorderMobile")
        except Exception:
            pass

    seen = set()
    for old_dir in legacy_dirs:
        try:
            old_dir = old_dir.resolve()
        except Exception:
            pass
        if old_dir == APP_DIR or str(old_dir) in seen:
            continue
        seen.add(str(old_dir))
        for filename in DATA_FILENAMES:
            old_path = old_dir / filename
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
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8-sig") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    temp_path.replace(path)


def load_user_profile():
    default = {
        "weight": "62.5",
        "bodyfat": "13",
        "height": "170",
        "age": "30",
        "sex": "男",
        "activity_habit": "规律训练",
        "waist_cm": "",
        "arm_cm": "",
        "macro_mode": "auto",
        "macro_multipliers": DEFAULT_MACRO_MULTIPLIERS,
        "body_updated_at": "",
        "profile_inited": False,
    }
    data = load_json(PROFILE_FILE, default)
    if not isinstance(data, dict):
        data = default
    for k, v in default.items():
        data.setdefault(k, v)
    normalized = {}
    stored_multipliers = data.get("macro_multipliers", {})
    if not isinstance(stored_multipliers, dict):
        stored_multipliers = {}
    for day_type, defaults in DEFAULT_MACRO_MULTIPLIERS.items():
        saved_day = stored_multipliers.get(day_type, {})
        if not isinstance(saved_day, dict):
            saved_day = {}
        normalized[day_type] = {
            macro: to_float(saved_day.get(macro), default_value)
            for macro, default_value in defaults.items()
        }
    data["macro_multipliers"] = normalized
    if data.get("macro_mode") not in ["auto", "custom"]:
        data["macro_mode"] = "auto"
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

def make_button(text, on_click=None, icon=None, bgcolor=None, color=None, expand=False, height=48):
    """Readable mobile button with a clear touch target and visible boundary."""
    fg = color or "#FFFFFF"
    bg = bgcolor or PRIMARY
    children = []
    if icon is not None:
        children.append(ft.Icon(icon, size=18, color=fg))
    children.append(ft.Text(text, size=14, weight="bold", color=fg, max_lines=1, overflow="ellipsis"))

    btn = ft.Container(
        content=ft.Row(children, alignment="center", spacing=4),
        height=max(48, height),
        padding=ft.Padding(left=10, top=0, right=10, bottom=0),
        bgcolor=bg,
        border=thin_border(PRIMARY if bg == PRIMARY else BORDER),
        border_radius=8,
        ink=True,
        on_click=on_click,
    )
    btn.expand = expand
    return btn

def thin_border(color=BORDER):
    side = ft.BorderSide(width=1, color=color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


def card(content, padding=12, margin_bottom=8):
    return ft.Container(
        content=content,
        bgcolor=CARD,
        border=thin_border(),
        border_radius=8,
        padding=padding,
        margin=ft.Margin(left=8, top=0, right=8, bottom=margin_bottom),
    )

def section_title(text):
    return ft.Text(text, size=17, weight="bold", color=TEXT)

def small_text(text, color=SUB):
    return ft.Text(text, size=12, color=color)

def labeled_plain_field(label, value="", width=None, keyboard_type=None, expand=False, height=46):
    field = plain_number_field(value=value, width=width, keyboard_type=keyboard_type, expand=expand, height=height)
    label_box = ft.Container(content=small_text(label), height=18, alignment=ft.Alignment.CENTER_LEFT)
    box = ft.Column([label_box, field], spacing=4)
    if expand:
        box.expand = True
    return box, field

def mobile_text_field(label, value="", width=None, keyboard_type=None, on_change=None, on_blur=None, on_submit=None, expand=False, height=52):
    fld = ft.TextField(value=value, height=height, keyboard_type=keyboard_type, expand=True)
    try:
        fld.text_size = 16
        fld.dense = True
        fld.border_radius = 8
        fld.bgcolor = "#FFFFFF"
        fld.border_color = BORDER
        fld.focused_border_color = PRIMARY
        fld.cursor_color = PRIMARY
        fld.content_padding = 12
    except Exception:
        pass
    if on_change:
        fld.on_change = on_change
    if on_blur:
        fld.on_blur = on_blur
    if on_submit:
        fld.on_submit = on_submit
    return LabeledInput(label, fld, width=width, expand=expand)

def mobile_dropdown(label, value, options, width=None, on_change=None, expand=False):
    dd = ft.Dropdown(value=value, options=options, height=52, expand=True)
    try:
        dd.text_size = 16
        dd.dense = True
        dd.border_radius = 8
        dd.bgcolor = "#FFFFFF"
        dd.border_color = BORDER
        dd.focused_border_color = PRIMARY
        dd.content_padding = 12
    except Exception:
        pass
    if on_change:
        dd.on_change = on_change
    return LabeledInput(label, dd, width=width, expand=expand)

def plain_number_field(value="", width=None, keyboard_type=None, on_change=None, expand=False, height=46):
    fld = ft.TextField(value=value, width=width, height=height, keyboard_type=keyboard_type)
    try:
        fld.text_size = 16
        fld.dense = True
        fld.border_radius = 8
        fld.bgcolor = "#FFFFFF"
        fld.border_color = BORDER
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
                ft.Text(label, size=14, color=TEXT, weight="bold"),
                ft.Text(target_text, size=14, color=SUB, weight="bold"),
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
        content=ft.Text(text, size=13, color=color, weight="bold"),
        bgcolor="#FFFFFF",
        border=thin_border(color),
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

    # FilePicker is a Service in Flet 0.85.x. Android export uses src_bytes,
    # so the system file chooser can write into shared storage safely.
    file_picker = ft.FilePicker()
    try:
        page.services.append(file_picker)
    except Exception:
        # Compatibility fallback for builds where services still live in overlay.
        if file_picker not in page.overlay:
            page.overlay.append(file_picker)

    def open_control(control):
        if control not in page.overlay:
            page.overlay.append(control)
        control.open = True
        page.update()

    def close_control(control):
        control.open = False
        page.update()

    active_snack = {"control": None}

    def snack(message, action_label=None, action=None):
        # Flet 0.85.3 compatibility:
        # Keep only one SnackBar in overlay. Accumulated/overlapping SnackBars can
        # make repeated save/update prompts appear intermittently on Android.
        previous = active_snack.get("control")
        if previous is not None:
            try:
                previous.open = False
            except Exception:
                pass
            try:
                if previous in page.overlay:
                    page.overlay.remove(previous)
            except Exception:
                pass

        content_controls = [ft.Text(message, size=13, color="#FFFFFF", expand=True)]
        if action_label and action:
            content_controls.append(ft.Container(
                content=ft.Text(action_label, size=13, weight="bold", color="#FFFFFF"),
                padding=8,
                on_click=lambda e: action(),
            ))
        sb = ft.SnackBar(content=ft.Row(content_controls, spacing=8))
        try:
            sb.duration = 2200
        except Exception:
            pass
        try:
            sb.bgcolor = PRIMARY
        except Exception:
            pass
        page.overlay.append(sb)
        active_snack["control"] = sb
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

    def page_is_mobile():
        """Flet mobile save paths are document URIs, not Python file paths."""
        try:
            platform = getattr(page, "platform", None)
            is_mobile = getattr(platform, "is_mobile", None)
            if callable(is_mobile):
                return bool(is_mobile())
            platform_name = str(getattr(platform, "value", platform) or "").lower()
            return platform_name in ["android", "ios"]
        except Exception:
            return False

    def meal_for_current_time():
        hour = datetime.datetime.now().hour
        if hour < 10:
            return "早餐"
        if hour < 15:
            return "午餐"
        return "晚餐"

    # State
    foods = load_json(FOOD_FILE, DEFAULT_FOODS)
    supplements = load_json(SUPP_FILE, DEFAULT_SUPPLEMENTS)
    records = load_json(RECORD_FILE, {})
    foods = foods if isinstance(foods, list) else list(DEFAULT_FOODS)
    foods = [item for item in foods if isinstance(item, dict)]
    supplements = supplements if isinstance(supplements, list) else list(DEFAULT_SUPPLEMENTS)
    supplements = [item for item in supplements if isinstance(item, dict)]
    records = records if isinstance(records, dict) else {}

    def responsive_width(max_width=340):
        raw_width = to_float(getattr(page, "width", None), 430)
        return max(260, min(max_width, int(raw_width) - 56))

    def food_shortcuts(meal_name, limit=4):
        """Return meal-aware frequent foods and true recent foods with last quantity."""
        today = date.today()
        cutoff = today - datetime.timedelta(days=29)
        meal_counts = Counter()
        global_counts = Counter()
        latest_items = {}
        latest_meal_items = {}
        recent_candidates = []
        known_names = {str(food.get("name", "")) for food in foods}

        for record_date in sorted(records.keys(), reverse=True):
            record = records.get(record_date, {})
            if not isinstance(record, dict):
                continue
            try:
                in_last_30_days = cutoff <= date.fromisoformat(record_date) <= today
            except (TypeError, ValueError):
                in_last_30_days = False
            meal_names_for_day = set()
            global_names_for_day = set()
            for meal in MEALS:
                saved_meals = record.get("meals", {})
                if not isinstance(saved_meals, dict):
                    continue
                meal_items = saved_meals.get(meal, [])
                if not isinstance(meal_items, list):
                    continue
                for index, item in enumerate(meal_items):
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("food", "")).strip()
                    if not name or name not in known_names:
                        continue
                    if in_last_30_days:
                        global_names_for_day.add(name)
                        if meal == meal_name:
                            meal_names_for_day.add(name)
                    sort_key = str(item.get("added_at") or f"{record_date}T{index:06d}")
                    if in_last_30_days and meal == meal_name:
                        recent_candidates.append((sort_key, item))
                    if name not in latest_items or sort_key > latest_items[name][0]:
                        latest_items[name] = (sort_key, item)
                    if meal == meal_name and (name not in latest_meal_items or sort_key > latest_meal_items[name][0]):
                        latest_meal_items[name] = (sort_key, item)
            global_counts.update(global_names_for_day)
            meal_counts.update(meal_names_for_day)

        source_counts = meal_counts or global_counts
        common_names = [name for name, _ in sorted(source_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]]
        common = []
        for name in common_names:
            latest = latest_meal_items.get(name) or latest_items.get(name)
            if latest:
                common.append(latest[1])

        recent = []
        seen = set()
        for _, item in sorted(recent_candidates, key=lambda pair: pair[0], reverse=True):
            name = str(item.get("food", "")).strip()
            if name in seen:
                continue
            seen.add(name)
            recent.append(item)
            if len(recent) >= limit:
                break
        return common, recent

    def training_signature():
        training = state.get("training", {})
        signature_data = {
            "summary_note": str(training.get("summary_note", "")),
            "targets": training.get("targets", []),
            "session": training.get("session"),
            "sessions": training.get("sessions", []),
        }
        return json.dumps(signature_data, ensure_ascii=False, sort_keys=True)

    def training_carb_warning():
        training = state.get("training", {})
        if training.get("carb_reminder_dismissed_signature") == training_signature():
            return ""
        recommended = recommend_carb_day(training)
        current = state.get("day_type")
        if recommended and recommended != current:
            summary = summarize_daily_training({"training": training})
            parts = summary.get("body_part_label") or "当前训练安排"
            return f"{parts}按你的碳循环规则更适合{recommended}，当前是{current}"
        return ""

    def latest_record_body(target_date=None):
        candidates = []
        for record_date, record in records.items():
            if target_date and record_date > target_date:
                continue
            measurement = normalize_body_measurement(record, record_date)
            if not measurement["is_measured"]:
                continue
            weight = measurement.get("weight_kg")
            bodyfat = measurement.get("bodyfat_percent")
            if weight is not None or bodyfat is not None:
                candidates.append((record_date, weight, bodyfat))
        if not candidates and target_date:
            return latest_record_body()
        if not candidates:
            return None
        record_date, weight, bodyfat = sorted(candidates, key=lambda item: item[0])[-1]
        return {"date": record_date, "weight": weight, "bodyfat": bodyfat}

    state = {
        "date": date.today().isoformat(),
        "weight": "62.5",
        "bodyfat": "13",
        "measurement": None,
        "circumference": None,
        "height": "170",
        "age": "30",
        "sex": "男",
        "activity_habit": "规律训练",
        "waist_cm": "",
        "arm_cm": "",
        "macro_mode": "auto",
        "macro_multipliers": json.loads(json.dumps(DEFAULT_MACRO_MULTIPLIERS)),
        "profile_inited": False,
        "day_type": "高碳日",
        "meals": {m: [] for m in MEALS},
        "training": {
            "total_duration_min": "",
            "total_calories_kcal": "",
            "fatigue_status": "状态一般",
            "summary_note": "",
            "targets": [],
            "carb_reminder_dismissed_signature": "",
            "session": None,
            "sessions": [],
        },
        "water": [],
        "supplements": [],
        "sleep": {"bed_time": "", "wake_time": "", "naps": []},
        "current_view": "today",
        "selected_meal": "汇总",
        "advice_expanded": False,
        "history_trend_expanded": False,
        "data_page": {
            "period_days": 7,
            "active_tab": "趋势",
            "chart_kind": "weight",
            "body_part_filter": "全部",
            "selected_date": date.today().isoformat(),
            "action_trend_open": False,
            "selected_exercise": None,
            "raw_expanded": False,
        },
        "training_exercise_index": 0,
        "training_set_index": 0,
        "last_complete_click_at": 0.0,
    }
    training_clock_refs = {"elapsed": None, "rest": None}
    rest_notifier = RestNotifier(
        page,
        notification_title="组间休息结束",
        notification_body="下一组可以开始了",
    )

    saved_profile = load_user_profile()
    latest_body = latest_record_body()
    if saved_profile.get("body_updated_at") or not latest_body:
        state["weight"] = str(saved_profile.get("weight", state["weight"]))
        state["bodyfat"] = str(saved_profile.get("bodyfat", state["bodyfat"]))
    else:
        if latest_body.get("weight") is not None:
            state["weight"] = f"{latest_body['weight']:g}"
        if latest_body.get("bodyfat") is not None:
            state["bodyfat"] = f"{latest_body['bodyfat']:g}"
    state["height"] = str(saved_profile.get("height", state["height"]))
    state["age"] = str(saved_profile.get("age", state["age"]))
    state["sex"] = str(saved_profile.get("sex", state["sex"]))
    state["activity_habit"] = str(saved_profile.get("activity_habit", state["activity_habit"]))
    state["waist_cm"] = str(saved_profile.get("waist_cm", state.get("waist_cm", "")))
    state["arm_cm"] = str(saved_profile.get("arm_cm", state.get("arm_cm", "")))
    state["macro_mode"] = saved_profile.get("macro_mode", "auto")
    state["macro_multipliers"] = json.loads(json.dumps(saved_profile.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS)))
    state["profile_inited"] = bool(saved_profile.get("profile_inited", False))

    def save_profile_from_state():
        save_user_profile({
            "weight": state.get("weight", "62.5"),
            "bodyfat": state.get("bodyfat", "13"),
            "height": state.get("height", "170"),
            "age": state.get("age", "30"),
            "sex": state.get("sex", "男"),
            "activity_habit": state.get("activity_habit", "规律训练"),
            "waist_cm": state.get("waist_cm", ""),
            "arm_cm": state.get("arm_cm", ""),
            "macro_mode": state.get("macro_mode", "auto"),
            "macro_multipliers": json.loads(json.dumps(state.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))),
            "body_updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "profile_inited": bool(state.get("profile_inited", False)),
        })

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
        day_type = state.get("day_type")
        if day_type not in DAY_TYPES:
            day_type = "高碳日"
        cfg = DAY_TYPES[day_type]

        calorie_target = round(comp["tdee"] * cfg["calorie_factor"], 0)

        macro_mode = state.get("macro_mode", "auto")
        if macro_mode == "custom":
            macro_multipliers = state.get("macro_multipliers", {})
            day_multipliers = macro_multipliers.get(day_type, {}) if isinstance(macro_multipliers, dict) else {}
            day_multipliers = day_multipliers if isinstance(day_multipliers, dict) else {}
            defaults = DEFAULT_MACRO_MULTIPLIERS.get(day_type, DEFAULT_MACRO_MULTIPLIERS["高碳日"])
            carb_gkg = to_float(day_multipliers.get("carb"), defaults["carb"])
            protein_gkg = to_float(day_multipliers.get("protein"), defaults["protein"])
            fat_gkg = to_float(day_multipliers.get("fat"), defaults["fat"])

            # 自定义值是区间中心：蛋白按去脂体重，其余按当前体重。
            protein_center = lean_mass * protein_gkg
            protein_min = round(max(0, protein_center - lean_mass * 0.15), 1)
            protein_max = round(protein_center + lean_mass * 0.15, 1)
            fat_center = weight * fat_gkg
            fat_min = round(max(0, fat_center - weight * 0.075), 1)
            fat_max = round(fat_center + weight * 0.075, 1)
            carb_center = max(30, round(weight * carb_gkg, 1))
            carb_interval = cfg["carb_interval"]
            carb_min = max(30, round(carb_center - carb_interval, 1))
            carb_max = round(carb_center + carb_interval, 1)
        else:
            # 蛋白：按去脂体重区间估算，2.0-2.3g/kg LBM。
            protein_min = round(lean_mass * 2.0, 1)
            protein_max = round(lean_mass * 2.3, 1)

            # 脂肪：高碳低脂，低碳略高脂；按体重估算。
            fat_min = round(weight * cfg["fat_gkg_min"], 1)
            fat_max = round(weight * cfg["fat_gkg_max"], 1)

            # 碳水：高/中/低碳日 g/kg 核心值 + 体脂、年龄修正。
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

            if day_type == "高碳日":
                carb_min = max(carb_min, round(weight * 2.5, 1))
                carb_max = min(carb_max, round(weight * 3.4, 1))
            elif day_type == "中碳日":
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
            "macro_mode": macro_mode,
        }

    def daily_total():
        total = {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}
        meals = state.get("meals", {})
        if not isinstance(meals, dict):
            meals = {}
        for items in meals.values():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
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
            items = state.get("meals", {}).get(m, []) if isinstance(state.get("meals"), dict) else []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
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
                "macro_mode": state.get("macro_mode", "auto"),
                "macro_multipliers": json.loads(json.dumps(state.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))),
                "day_type": state["day_type"],
                "targets": targets,
                "compliance": eva,
                "measurement": state.get("measurement"),
                "circumference": state.get("circumference"),
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
                "carb_reminder_dismissed_signature": state["training"].get("carb_reminder_dismissed_signature", ""),
                "session": state["training"].get("session"),
                "sessions": list(state["training"].get("sessions", [])),
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
        if not isinstance(rec, dict):
            rec = None
        if rec:
            p = rec.get("profile", {})
            if not isinstance(p, dict):
                p = {}
            current_profile = load_user_profile()
            if target_date == date.today().isoformat() and current_profile.get("body_updated_at"):
                state["weight"] = str(current_profile.get("weight", p.get("weight_kg", state["weight"])))
                state["bodyfat"] = str(current_profile.get("bodyfat", p.get("bodyfat_percent", state["bodyfat"])))
            else:
                state["weight"] = str(p.get("weight_kg", state["weight"]))
                state["bodyfat"] = str(p.get("bodyfat_percent", state["bodyfat"]))
            normalized_measurement = normalize_body_measurement(rec, target_date)
            state["measurement"] = p.get("measurement") if normalized_measurement["is_measured"] else None
            state["circumference"] = p.get("circumference") if isinstance(p.get("circumference"), dict) else None
            if not state.get("profile_inited"):
                state["height"] = str(p.get("height_cm", state.get("height", "170")))
                state["age"] = str(p.get("age", state.get("age", "30")))
                state["sex"] = str(p.get("sex", state.get("sex", "男")))
                state["activity_habit"] = str(p.get("activity_habit", state.get("activity_habit", "规律训练")))
                state["waist_cm"] = str(p.get("waist_cm", state.get("waist_cm", "")))
                state["arm_cm"] = str(p.get("arm_cm", state.get("arm_cm", "")))
            saved_day_type = p.get("day_type")
            state["day_type"] = saved_day_type if saved_day_type in DAY_TYPES else "高碳日"
            saved_meals = rec.get("meals", {})
            if not isinstance(saved_meals, dict):
                saved_meals = {}
            state["meals"] = {
                m: [item for item in saved_meals.get(m, []) if isinstance(item, dict)]
                if isinstance(saved_meals.get(m, []), list) else []
                for m in MEALS
            }

            tr = rec.get("training", {})
            if isinstance(tr, dict):
                saved_targets = tr.get("targets", [])
                if not isinstance(saved_targets, list):
                    saved_targets = []
                archived_sessions = [item for item in tr.get("sessions", []) if isinstance(item, dict)] if isinstance(tr.get("sessions", []), list) else []
                raw_session = tr.get("session") if isinstance(tr.get("session"), dict) else None
                if raw_session is None and archived_sessions:
                    raw_session = next((item for item in reversed(archived_sessions) if item.get("status") == "active"), archived_sessions[-1])
                if raw_session is None:
                    migrated = migrate_legacy_training(tr, target_date)
                    raw_session = migrated.to_dict() if migrated is not None else None
                state["training"] = {
                    "total_duration_min": str(tr.get("total_duration_min", "")),
                    "total_calories_kcal": str(tr.get("total_calories_kcal", "")),
                    "fatigue_status": tr.get("fatigue_status", "状态一般"),
                    "summary_note": str(tr.get("summary_note", "")),
                    "targets": [dict(item, intensity=item.get("intensity", "中等")) for item in saved_targets if isinstance(item, dict)],
                    "carb_reminder_dismissed_signature": str(tr.get("carb_reminder_dismissed_signature", "")),
                    "session": raw_session,
                    "sessions": archived_sessions,
                }
            elif isinstance(tr, list):
                migrated = migrate_legacy_training(tr, target_date)
                state["training"] = {"total_duration_min": "", "total_calories_kcal": "", "fatigue_status": "状态一般", "summary_note": "", "targets": [dict(item, intensity=item.get("intensity", "中等")) for item in tr if isinstance(item, dict)], "carb_reminder_dismissed_signature": "", "session": migrated.to_dict() if migrated else None, "sessions": []}
            else:
                state["training"] = {"total_duration_min": "", "total_calories_kcal": "", "fatigue_status": "状态一般", "summary_note": "", "targets": [], "carb_reminder_dismissed_signature": "", "session": None, "sessions": []}

            water = rec.get("water", {})
            if isinstance(water, dict):
                water_records = water.get("records_ml", [])
                state["water"] = [to_float(x) for x in water_records] if isinstance(water_records, list) else []
            else:
                state["water"] = []
            saved_supplements = rec.get("supplements", [])
            state["supplements"] = [item for item in saved_supplements if isinstance(item, dict)] if isinstance(saved_supplements, list) else []
            saved_sleep = rec.get("sleep", {})
            if isinstance(saved_sleep, dict):
                state["sleep"] = {
                    "bed_time": str(saved_sleep.get("bed_time", "")),
                    "wake_time": str(saved_sleep.get("wake_time", "")),
                    "naps": [item for item in saved_sleep.get("naps", []) if isinstance(item, dict)] if isinstance(saved_sleep.get("naps", []), list) else [],
                }
            else:
                state["sleep"] = {"bed_time": "", "wake_time": "", "naps": []}
        else:
            previous_body = latest_record_body(target_date)
            current_profile = load_user_profile()
            if current_profile.get("body_updated_at"):
                state["weight"] = str(current_profile.get("weight", state["weight"]))
                state["bodyfat"] = str(current_profile.get("bodyfat", state["bodyfat"]))
            elif previous_body:
                if previous_body.get("weight") is not None:
                    state["weight"] = f"{previous_body['weight']:g}"
                if previous_body.get("bodyfat") is not None:
                    state["bodyfat"] = f"{previous_body['bodyfat']:g}"
            state["day_type"] = "高碳日"
            state["measurement"] = None
            state["circumference"] = None
            state["meals"] = {m: [] for m in MEALS}
            state["training"] = {"total_duration_min": "", "total_calories_kcal": "", "fatigue_status": "状态一般", "summary_note": "", "targets": [], "carb_reminder_dismissed_signature": "", "session": None, "sessions": []}
            state["water"] = []
            state["supplements"] = []
            state["sleep"] = {"bed_time": "", "wake_time": "", "naps": []}
        restore_training_cursor()
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
            measurement = normalize_body_measurement(rec, d)
            if not measurement["is_measured"]:
                continue
            w = measurement.get("weight_kg")
            bf = measurement.get("bodyfat_percent")
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
            bgcolor="#F7FFFFFF",
            barrier_color="#520F1F1A",
        )

    def open_add_food_dialog(default_meal="午餐"):
        dialog_width = responsive_width()

        meal_dd = mobile_dropdown("餐次", default_meal, [ft.dropdown.Option(m) for m in MEALS], width=dialog_width)
        search = mobile_text_field("搜索食物", width=dialog_width)
        food_dd = mobile_dropdown("食物", None, [ft.dropdown.Option(f["name"]) for f in foods], width=dialog_width)

        def current_unit():
            food = next((f for f in foods if f.get("name") == food_dd.value), None)
            return food.get("unit", "g") if food else "g"

        qty = mobile_text_field(f"数量（{current_unit()}）", width=dialog_width, keyboard_type=_KEYBOARD_NUMBER)

        def update_qty_label():
            qty.label_text = f"数量（{current_unit()}）"

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

        def append_food(food, amount, meal_name, close_dialog=False):
            item = {
                "food": food["name"], "qty": amount, "unit": food.get("unit", "g"),
                "method": food.get("method", ""),
                "id": uuid.uuid4().hex,
                "added_at": datetime.datetime.now().isoformat(timespec="microseconds"),
                **calc_item(food, amount),
            }
            original_date = state["date"]
            item_id = item["id"]
            state["meals"].setdefault(meal_name, []).append(item)
            save_current()
            if close_dialog:
                close_control(dlg)
                refresh()

            def undo():
                original_record = records.get(original_date)
                if not isinstance(original_record, dict):
                    return
                original_meals = original_record.get("meals", {})
                if not isinstance(original_meals, dict):
                    return
                meal_items = original_meals.get(meal_name, [])
                if not isinstance(meal_items, list):
                    return
                index = next((i for i, saved in enumerate(meal_items) if isinstance(saved, dict) and saved.get("id") == item_id), None)
                if index is None:
                    return
                meal_items.pop(index)
                save_json(RECORD_FILE, records)
                if state.get("date") == original_date:
                    state["meals"].setdefault(meal_name, [])
                    state["meals"][meal_name] = [saved for saved in state["meals"][meal_name] if not isinstance(saved, dict) or saved.get("id") != item_id]
                    refresh()
                snack("已撤销快捷添加")

            snack(f"已添加 {food['name']} {amount:g}{food.get('unit', 'g')}", "撤销", undo)

        def select_shortcut(item):
            name = str(item.get("food", ""))
            food_dd.value = name
            search.value = ""
            qty.value = f"{to_float(item.get('qty')):g}"
            food_dd.options = [ft.dropdown.Option(f["name"]) for f in foods]
            update_qty_label()
            page.update()

        shortcut_mode = {"value": "common"}
        shortcut_list = ft.Column(spacing=6)
        shortcut_tabs = ft.Row(spacing=6)

        def shortcut_label(item):
            name = str(item.get("food", ""))
            qty_text = f"{to_float(item.get('qty')):g}{item.get('unit', '')}"
            return f"{name} · {qty_text}"

        def update_shortcuts(e=None):
            common_foods, recent_foods = food_shortcuts(meal_dd.value or default_meal)
            current = common_foods if shortcut_mode["value"] == "common" else recent_foods
            shortcut_list.controls.clear()
            if not current:
                shortcut_list.controls.append(small_text("记录几次后，这里会出现快捷食物"))
            for item in current:
                shortcut_list.controls.append(ft.Container(
                    content=ft.Row([
                        ft.Container(
                            content=ft.Text(shortcut_label(item), size=12, weight="bold", color=GREEN, max_lines=1, overflow="ellipsis"),
                            height=44, padding=ft.Padding(left=10, top=0, right=10, bottom=0),
                            alignment=ft.Alignment.CENTER_LEFT, expand=True,
                            on_click=lambda e, x=item: select_shortcut(x),
                        ),
                        ft.IconButton(icon=ft.Icons.ADD, icon_color="#FFFFFF", bgcolor=PRIMARY,
                                      icon_size=19, tooltip="按上次份量立即添加",
                                      on_click=lambda e, x=item: quick_add(x)),
                    ], spacing=4),
                    bgcolor=PRIMARY_SOFT, border=thin_border(), border_radius=8,
                    padding=ft.Padding(left=0, top=0, right=3, bottom=0),
                ))

            shortcut_tabs.controls = [
                make_button("常用", on_click=lambda e: set_shortcut_mode("common"), bgcolor=PRIMARY if shortcut_mode["value"] == "common" else PRIMARY_SOFT, color="#FFFFFF" if shortcut_mode["value"] == "common" else GREEN, expand=True),
                make_button("最近", on_click=lambda e: set_shortcut_mode("recent"), bgcolor=PRIMARY if shortcut_mode["value"] == "recent" else PRIMARY_SOFT, color="#FFFFFF" if shortcut_mode["value"] == "recent" else GREEN, expand=True),
            ]
            if e is not None:
                page.update()

        def set_shortcut_mode(mode):
            shortcut_mode["value"] = mode
            update_shortcuts(True)

        def quick_add(item):
            food = next((f for f in foods if f.get("name") == item.get("food")), None)
            amount = to_float(item.get("qty"), 0)
            if not food or amount <= 0:
                snack("快捷食物数据无效，请手动填写")
                return
            append_food(food, amount, meal_dd.value or default_meal, close_dialog=True)

        meal_dd.on_change = lambda e: update_shortcuts(True)
        update_shortcuts()

        def confirm(e):
            if not food_dd.value or not qty.value:
                snack("请选择食物并填写数量")
                return
            food = next((f for f in foods if f["name"] == food_dd.value), None)
            q = to_float(qty.value)
            if not food or q <= 0:
                snack("食物或数量不正确")
                return
            append_food(food, q, meal_dd.value or default_meal, close_dialog=True)

        content = ft.Column([
            meal_dd,
            shortcut_tabs,
            shortcut_list,
            search,
            food_dd,
            qty,
        ], width=dialog_width, height=390, spacing=10, scroll=_SCROLL_AUTO)

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

        raw_width = to_float(getattr(page, "width", None), 430)
        dialog_width = max(260, min(340, int(raw_width) - 56))
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
        raw_width = to_float(getattr(page, "width", None), 430)
        dialog_width = max(260, min(340, int(raw_width) - 56))
        cardio_targets = ["跑步", "徒步", "游泳", "骑行", "打球"]
        dlg = None

        note = mobile_text_field("备注", width=dialog_width)
        intensity = mobile_dropdown("训练强度", "恢复" if selected_target == "休息" else "中等", [ft.dropdown.Option(x) for x in INTENSITY_OPTIONS], width=dialog_width)

        incline = mobile_text_field("坡度 %", keyboard_type=_KEYBOARD_NUMBER, expand=True)
        speed = mobile_text_field("速度 km/h", keyboard_type=_KEYBOARD_NUMBER, expand=True)
        climb_minutes = mobile_text_field("时长 min", keyboard_type=_KEYBOARD_NUMBER, expand=True)

        abs_action = mobile_dropdown("腹部动作", "仰卧抬腿", [ft.dropdown.Option(x) for x in ABS_ACTIONS], width=dialog_width)
        reps = mobile_text_field("次数/组数", width=dialog_width)

        cardio_minutes = mobile_text_field("时长 min", keyboard_type=_KEYBOARD_NUMBER, width=dialog_width)

        controls = [ft.Text(selected_target, size=16, weight="bold", color=PRIMARY), intensity]

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
                "intensity": intensity.value or "中等",
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
        dialog_width = responsive_width()
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
            ft.Row([fields["unit"], fields["base_qty"]], spacing=8, vertical_alignment="start"),
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
        dialog_width = responsive_width()
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

        content = ft.Column([name, amount, unit], width=dialog_width, height=300, spacing=12, scroll=_SCROLL_AUTO)

        dlg = dialog_base(
            "修改补剂" if editing else "新增补剂",
            content,
            [ft.Container(content=make_button("保存", on_click=confirm, expand=True), width=dialog_width)],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def open_record_detail(record_date):
        rec = records.get(record_date)
        if not isinstance(rec, dict):
            return
        text = format_record_detail(rec)
        dlg = None
        dialog_width = responsive_width()
        content = ft.Column(
            [ft.Text(text, size=13, selectable=True)],
            height=500,
            width=dialog_width,
            scroll=_SCROLL_AUTO,
            spacing=0,
        )
        dlg = dialog_base(
            f"{record_date} 详情",
            content,
            [ft.Container(content=make_button("加载到今日页", on_click=lambda e: (close_control(dlg), load_record_for_date(record_date, show=True), set_view("today")), expand=True), width=dialog_width)],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def format_record_detail(rec):
        if not isinstance(rec, dict):
            return "记录格式无效"
        p = rec.get("profile", {})
        total = rec.get("daily_total", {})
        p = p if isinstance(p, dict) else {}
        total = total if isinstance(total, dict) else {}
        comp = p.get("compliance", {})
        targets = p.get("targets", {})
        comp = comp if isinstance(comp, dict) else {}
        targets = targets if isinstance(targets, dict) else {}
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
        if isinstance(tr, list):
            tr = {"targets": tr}
        elif not isinstance(tr, dict):
            tr = {}
        lines.append("【训练】")
        lines.append(f"总时长：{tr.get('total_duration_min','')} min")
        lines.append(f"总消耗：{tr.get('total_calories_kcal','')} kcal")
        lines.append(f"疲劳：{tr.get('fatigue_status','')}")
        training_targets = tr.get("targets", [])
        if not isinstance(training_targets, list):
            training_targets = []
        for i, t in enumerate(training_targets, 1):
            if not isinstance(t, dict):
                continue
            lines.append(f"{i}. {t.get('target','')} {t.get('detail','')} {t.get('note','')}")
        lines.append("")
        lines.append("【饮食】")
        meals = rec.get("meals", {})
        meals = meals if isinstance(meals, dict) else {}
        for meal in MEALS:
            if meals.get(meal):
                lines.append(f"{meal}：")
                for item in meals[meal] if isinstance(meals[meal], list) else []:
                    if not isinstance(item, dict):
                        continue
                    lines.append(f"- {item.get('food','')} {item.get('qty','')}{item.get('unit','')}，{item.get('kcal',0)} kcal")
        lines.append("")
        w = rec.get("water", {})
        w = w if isinstance(w, dict) else {}
        lines.append(f"饮水：{w.get('total_ml',0)} ml，{w.get('status','')}")
        saved_supplements = rec.get("supplements", [])
        if isinstance(saved_supplements, list) and saved_supplements:
            lines.append("补剂：" + "、".join([f"{s.get('name','')} {s.get('amount','')}{s.get('unit','')}" for s in saved_supplements if isinstance(s, dict)]))
        sl = rec.get("sleep", {})
        if isinstance(sl, dict):
            lines.append(f"睡眠：{sl.get('bed_time','')} - {sl.get('wake_time','')}，共 {sl.get('total_text','')}")
            naps = sl.get("naps", [])
            if naps:
                lines.append("小睡：" + "、".join([f"{n.get('start','')}-{n.get('end','')}" for n in naps if isinstance(n, dict)]))
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
        if name == "me":
            current_profile = load_user_profile()
            state["weight"] = str(current_profile.get("weight", state.get("weight", "62.5")))
            state["bodyfat"] = str(current_profile.get("bodyfat", state.get("bodyfat", "13")))
            state["height"] = str(current_profile.get("height", state.get("height", "170")))
            state["age"] = str(current_profile.get("age", state.get("age", "30")))
            state["sex"] = str(current_profile.get("sex", state.get("sex", "男")))
            state["activity_habit"] = str(current_profile.get("activity_habit", state.get("activity_habit", "规律训练")))
            state["waist_cm"] = str(current_profile.get("waist_cm", state.get("waist_cm", "")))
            state["arm_cm"] = str(current_profile.get("arm_cm", state.get("arm_cm", "")))
            state["macro_mode"] = current_profile.get("macro_mode", state.get("macro_mode", "auto"))
            state["macro_multipliers"] = json.loads(json.dumps(current_profile.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS)))
        state["current_view"] = name
        refresh()

    def session_data():
        value = state.get("training", {}).get("session")
        return value if isinstance(value, dict) else None

    def find_active_session_date():
        current = session_data()
        if current and current.get("status") == "active":
            return state.get("date")
        record_date, _ = find_active_daily_session(records)
        return record_date

    def resume_session_date(record_date):
        load_record_for_date(record_date)
        state["current_view"] = "training"
        refresh()

    def session_model():
        value = session_data()
        return TrainingSession.from_dict(value) if value else None

    def iso_now():
        return datetime.datetime.now().isoformat(timespec="seconds")

    def parse_iso(value):
        try:
            return datetime.datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def elapsed_seconds(session=None):
        session = session or session_data()
        if not session:
            return 0
        started = parse_iso(session.get("started_at"))
        if not started:
            return 0
        ended = parse_iso(session.get("ended_at")) if session.get("status") == "completed" else datetime.datetime.now()
        return max(0, int(((ended or datetime.datetime.now()) - started).total_seconds()))

    def clock_text(seconds):
        seconds = max(0, int(seconds or 0))
        hours, rest = divmod(seconds, 3600)
        minutes, secs = divmod(rest, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def persist_session(session):
        state["training"]["session"] = session
        save_current()

    def create_empty_session():
        training = state["training"]
        current = training.get("session")
        archive = training.setdefault("sessions", [])
        if isinstance(current, dict) and current.get("status") == "completed":
            training["sessions"] = append_session_once(archive, current)
        state["training"]["session"] = {
            "id": f"session_{uuid.uuid4().hex}",
            "date": state["date"],
            "status": "planned",
            "started_at": "",
            "ended_at": "",
            "total_duration_min": None,
            "exercises": [],
            "summary_note": "",
            "fatigue_status": state["training"].get("fatigue_status", "状态一般"),
            "rest_until": "",
            "rest_cycle": None,
            "incomplete": False,
        }
        state["training_exercise_index"] = 0
        state["training_set_index"] = 0
        save_current()

    def ensure_session():
        if not session_data() or session_data().get("status") == "completed":
            create_empty_session()
        return session_data()

    def open_add_exercise_dialog():
        ensure_session()
        dialog_width = responsive_width()
        selected = {"category": "胸", "sort": "frequent"}
        list_holder = ft.Column(spacing=8)
        category_rows = ft.Column(spacing=6)
        search = mobile_text_field("搜索动作名称、器械或目标肌群", "", width=dialog_width)
        library_dlg = None

        usage_stats = exercise_usage_stats(records)

        def previous_defaults(exercise_name, fallback):
            for record_date in sorted(records, reverse=True):
                record = records.get(record_date, {})
                training = record.get("training", {}) if isinstance(record, dict) else {}
                sessions = raw_training_sessions(training)
                for previous in reversed(sessions):
                    for exercise in previous.get("exercises", []) if isinstance(previous, dict) else []:
                        if exercise.get("name") != exercise_name:
                            continue
                        completed_sets = [item for item in exercise.get("sets", []) if item.get("completed")]
                        if completed_sets:
                            last = completed_sets[-1]
                            return last.get("weight_kg"), last.get("reps"), len(exercise.get("sets", []))
            return fallback.get("default_weight_kg"), fallback.get("default_reps"), fallback.get("default_sets", 4)

        def open_help(exercise):
            target = " · ".join(exercise.get("target_muscles", []))
            cues = [ft.Text(f"{index}. {text}", size=13, color=TEXT) for index, text in enumerate(exercise.get("cues", []), 1)]
            mistakes = [ft.Text(f"· {text}", size=13, color=SUB) for text in exercise.get("mistakes", [])]
            help_dlg = dialog_base(
                exercise.get("name", "动作说明"),
                ft.Column([
                    ft.Container(content=ft.Text(f"目标肌群 · {target}", size=13, color=GREEN, weight="bold"), bgcolor="#EAF7EF", border_radius=10, padding=10),
                    ft.Text("动作要点", size=15, weight="bold", color=TEXT),
                    *cues,
                    ft.Text("常见错误", size=15, weight="bold", color=ORANGE),
                    *mistakes,
                ], width=dialog_width, height=430, spacing=8, scroll=_SCROLL_AUTO),
                [ft.Container(content=make_button("知道了", on_click=lambda e: close_control(help_dlg), expand=True), width=dialog_width)],
                on_close=lambda e: close_control(help_dlg),
            )
            open_control(help_dlg)

        def open_setup(exercise):
            nonlocal library_dlg
            if library_dlg:
                close_control(library_dlg)
            fallback_weight, fallback_reps, fallback_sets = previous_defaults(exercise.get("name", ""), exercise)
            name = mobile_text_field("动作名称", exercise.get("name", ""), width=dialog_width)
            weight = mobile_text_field("重量 kg", "" if fallback_weight is None else f"{to_float(fallback_weight):g}", keyboard_type=_KEYBOARD_NUMBER, expand=True)
            reps = mobile_text_field("次数", "" if fallback_reps is None else str(int(to_float(fallback_reps))), keyboard_type=_KEYBOARD_NUMBER, expand=True)
            sets = mobile_text_field("组数", str(int(to_float(fallback_sets, 4))), keyboard_type=_KEYBOARD_NUMBER, expand=True)

            def confirm(e):
                session = ensure_session()
                action_name = (name.value or "").strip()
                set_count = max(1, min(12, int(to_float(sets.value, 4))))
                if not action_name:
                    snack("请填写动作名称")
                    return
                exercise_entry = {
                    "id": f"session_exercise_{uuid.uuid4().hex}",
                    "exercise_id": action_name,
                    "name": action_name,
                    "body_part": exercise.get("category", "自定义"),
                    "order": len(session.get("exercises", [])) + 1,
                    "sets": [{
                        "id": f"set_{uuid.uuid4().hex}",
                        "order": index + 1,
                        "weight_kg": max(0, to_float(weight.value)),
                        "reps": max(0, int(to_float(reps.value, 0))),
                        "completed": False,
                        "warmup": False,
                        "completed_at": "",
                    } for index in range(set_count)],
                    "note": "",
                }
                session.setdefault("exercises", []).append(exercise_entry)
                close_control(setup_dlg)
                persist_session(session)
                refresh()
                snack(f"已添加 {action_name}")

            setup_dlg = dialog_base(
                "设置动作",
                ft.Column([
                    name,
                    ft.Container(content=small_text("默认值仅用于首次添加；有历史时使用上次成绩，自重动作的重量可留空。"), bgcolor=SURFACE, border_radius=8, padding=8),
                    ft.Row([weight, reps, sets], spacing=8, vertical_alignment="start"),
                ], width=dialog_width, height=300, spacing=12, scroll=_SCROLL_AUTO),
                [ft.Container(content=make_button("加入训练", on_click=confirm, expand=True), width=dialog_width)],
                on_close=lambda e: close_control(setup_dlg),
            )
            open_control(setup_dlg)

        def exercise_row(exercise):
            weight = exercise.get("default_weight_kg")
            reps = exercise.get("default_reps")
            sets = exercise.get("default_sets")
            default_text = "自重" if weight is None else f"{to_float(weight):g} kg"
            default_text += " · 计时/距离" if reps is None else f" × {reps} 次 / {sets} 组"
            usage = usage_stats.get(str(exercise.get("name", "")).casefold(), {})
            usage_text = ""
            if usage.get("session_count"):
                usage_text = f" · 练过 {usage['session_count']} 次 · 最近 {usage['last_date']}"
            return ft.Container(
                content=ft.Row([
                    ft.Column([ft.Text(exercise["name"], size=14, weight="bold", color=TEXT), small_text(f"{exercise['equipment']} · {default_text}{usage_text}")], expand=True, spacing=2),
                    ft.IconButton(icon=ft.Icons.HELP_OUTLINE, tooltip="动作说明", icon_color=GREEN, width=48, height=48, on_click=lambda e, item=exercise: open_help(item)),
                    ft.IconButton(icon=ft.Icons.ADD, tooltip="加入训练", icon_color=GREEN, width=48, height=48, on_click=lambda e, item=exercise: open_setup(item)),
                ], spacing=4), bgcolor="#FFFFFF", border=thin_border(), border_radius=12, padding=10,
            )

        def rebuild_categories():
            category_rows.controls.clear()
            buttons = []
            for category in EXERCISE_CATEGORIES:
                is_selected = selected["category"] == category
                buttons.append(make_button(category, on_click=lambda e, c=category: choose_category(c), bgcolor=PRIMARY if is_selected else PRIMARY_SOFT, color="#FFFFFF" if is_selected else GREEN, expand=True))
            category_rows.controls.extend([ft.Row(buttons[:4], spacing=6), ft.Row(buttons[4:], spacing=6)])

        def choose_category(category):
            selected["category"] = category
            rebuild_categories()
            rebuild_list()
            page.update()

        def choose_sort(mode):
            selected["sort"] = mode
            rebuild_list()
            page.update()

        def rebuild_list(e=None):
            query = (search.value or "").strip()
            results = search_exercises(query, None if query else selected["category"])
            results = sort_exercises(results, usage_stats, selected["sort"])
            list_holder.controls.clear()
            list_holder.controls.extend(exercise_row(item) for item in results)
            if not results:
                list_holder.controls.append(ft.Container(content=small_text("没有匹配动作，可使用下方自定义动作"), bgcolor=SURFACE, border_radius=10, padding=12))
            if e is not None:
                page.update()

        search.on_change = rebuild_list
        rebuild_categories()
        rebuild_list()
        custom_item = {"name": "", "category": "自定义", "equipment": "自定义", "target_muscles": [], "cues": [], "mistakes": [], "default_weight_kg": None, "default_reps": 10, "default_sets": 4}
        sort_row = ft.Row([
            make_button("常练", on_click=lambda e: choose_sort("frequent"), bgcolor=PRIMARY, color="#FFFFFF", expand=True),
            make_button("最近", on_click=lambda e: choose_sort("recent"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
            make_button("名称", on_click=lambda e: choose_sort("name"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
        ], spacing=6)
        library_dlg = dialog_base(
            f"添加动作 · {len(EXERCISE_LIBRARY)} 个",
            ft.Column([search, sort_row, category_rows, list_holder, make_button("自定义动作", on_click=lambda e: open_setup(custom_item), icon=ft.Icons.EDIT, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True)], width=dialog_width, height=520, spacing=10, scroll=_SCROLL_AUTO),
            [],
            on_close=lambda e: close_control(library_dlg),
        )
        open_control(library_dlg)

    def reuse_history_session(e=None):
        dialog_width = responsive_width()
        selected = {"part": "全部"}
        cards_holder = ft.Column(spacing=8)
        filters_holder = ft.Column(spacing=6)
        history_dlg = None

        def apply_card(card_item, mode):
            current = session_data()
            copied = copy_whole_session(
                card_item["session"], current, mode=mode, new_date=state.get("date")
            )
            state["training"]["session"] = copied
            state["training_exercise_index"] = 0
            state["training_set_index"] = 0
            close_control(history_dlg)
            persist_session(copied)
            refresh()
            snack(f"已复用 {card_item['combination']} 训练")

        def choose_card(card_item):
            current = session_data()
            has_plan = bool(current and current.get("exercises"))
            if not has_plan:
                apply_card(card_item, "replace")
                return
            confirm_dlg = dialog_base(
                "当前计划已有动作",
                ft.Column([
                    ft.Text(f"复用 {card_item['combination']} · {card_item['date']}", size=15, weight="bold", color=TEXT),
                    small_text("请选择替换当前计划，或把整场历史训练追加到当前计划。"),
                ], width=dialog_width, spacing=8),
                [
                    make_button("取消", on_click=lambda e: close_control(confirm_dlg), bgcolor=SURFACE, color=SUB, expand=True),
                    make_button("整场追加", on_click=lambda e: (close_control(confirm_dlg), apply_card(card_item, "append")), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                    make_button("替换", on_click=lambda e: (close_control(confirm_dlg), apply_card(card_item, "replace")), expand=True),
                ],
                on_close=lambda e: close_control(confirm_dlg),
            )
            open_control(confirm_dlg)

        def rebuild_cards():
            part = None if selected["part"] == "全部" else selected["part"]
            cards = history_training_cards(records, part)
            cards_holder.controls.clear()
            for item in cards:
                cards_holder.controls.append(ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(item["combination"], size=16, weight="bold", color=TEXT),
                            small_text(f"最近 {item['date']} · {item['exercise_count']} 个动作"),
                        ], expand=True, spacing=3),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, color=GREEN),
                    ]),
                    bgcolor="#FFFFFF", border=thin_border(), border_radius=12, padding=14,
                    on_click=lambda e, card=item: choose_card(card),
                ))
            if not cards:
                cards_holder.controls.append(ft.Container(content=small_text("该部位还没有可复用的完整训练"), bgcolor=SURFACE, border_radius=10, padding=14))

        def choose_part(part):
            selected["part"] = part
            rebuild_filters()
            rebuild_cards()
            page.update()

        def rebuild_filters():
            buttons = []
            for part in ("全部", *BODY_PART_ORDER):
                active = selected["part"] == part
                buttons.append(make_button(part, on_click=lambda e, p=part: choose_part(p), bgcolor=PRIMARY if active else PRIMARY_SOFT, color="#FFFFFF" if active else GREEN, expand=True))
            filters_holder.controls[:] = [ft.Row(buttons[i:i + 3], spacing=6) for i in range(0, len(buttons), 3)]

        rebuild_filters()
        rebuild_cards()
        history_dlg = dialog_base(
            "复用历史训练",
            ft.Column([small_text("同一部位组合只显示最近一场"), filters_holder, cards_holder], width=dialog_width, height=520, spacing=10, scroll=_SCROLL_AUTO),
            [],
            on_close=lambda e: close_control(history_dlg),
        )
        open_control(history_dlg)

    def start_session(e=None):
        session = ensure_session()
        if not session.get("exercises"):
            open_add_exercise_dialog()
            return
        session.update({"status": "active", "started_at": session.get("started_at") or iso_now(), "ended_at": ""})
        persist_session(session)
        refresh()

    def delete_session_exercise(index):
        session = session_data()
        if not session or session.get("status") == "active":
            return
        exercises = session.get("exercises", [])
        if 0 <= index < len(exercises):
            exercises.pop(index)
        persist_session(session)
        refresh()

    def current_training_items():
        session = session_data()
        exercises = session.get("exercises", []) if session else []
        if not exercises:
            return session, None, None
        exercise_index = max(0, min(int(state.get("training_exercise_index", 0)), len(exercises) - 1))
        state["training_exercise_index"] = exercise_index
        exercise = exercises[exercise_index]
        sets = exercise.get("sets", [])
        if not sets:
            return session, exercise, None
        set_index = max(0, min(int(state.get("training_set_index", 0)), len(sets) - 1))
        state["training_set_index"] = set_index
        return session, exercise, sets[set_index]

    def restore_training_cursor():
        session = session_data()
        if not session or session.get("status") != "active":
            return
        for exercise_index, exercise in enumerate(session.get("exercises", [])):
            for set_index, item in enumerate(exercise.get("sets", [])):
                if not item.get("completed"):
                    state["training_exercise_index"] = exercise_index
                    state["training_set_index"] = set_index
                    return

    def adjust_current(field, delta):
        session, exercise, training_set = current_training_items()
        if not training_set or training_set.get("completed"):
            return
        current = to_float(training_set.get(field), 0)
        value = max(0, current + delta)
        training_set[field] = int(value) if field == "reps" else round(value, 1)
        persist_session(session)
        refresh()

    def undo_current_set(e=None):
        session, exercise, training_set = current_training_items()
        if not session or not training_set or not training_set.get("completed"):
            return
        result = undo_completed_set_result(session, str(training_set.get("id", "")))
        restored = result["session"]
        restored["rest_cycle"] = None
        restored["rest_until"] = ""
        persist_session(restored)
        refresh()
        snack("已撤销本组完成状态，可重新调整重量和次数")

    def move_training(direction):
        session, exercise, training_set = current_training_items()
        exercises = session.get("exercises", []) if session else []
        if not exercises:
            return
        index = max(0, min(len(exercises) - 1, state.get("training_exercise_index", 0) + direction))
        state["training_exercise_index"] = index
        next_sets = exercises[index].get("sets", [])
        state["training_set_index"] = next((i for i, item in enumerate(next_sets) if not item.get("completed")), 0)
        refresh()

    def complete_current_set(e=None):
        clicked_at = datetime.datetime.now().timestamp()
        if is_rapid_repeat(state.get("last_complete_click_at", 0), clicked_at):
            return
        state["last_complete_click_at"] = clicked_at
        session, exercise, training_set = current_training_items()
        if not training_set or training_set.get("completed"):
            return
        training_set["completed"] = True
        training_set["completed_at"] = iso_now()
        sets = exercise.get("sets", [])
        current_index = state.get("training_set_index", 0)
        if current_index + 1 < len(sets):
            state["training_set_index"] = current_index + 1
        else:
            exercises = session.get("exercises", [])
            current_exercise = state.get("training_exercise_index", 0)
            if current_exercise + 1 < len(exercises):
                state["training_exercise_index"] = current_exercise + 1
                state["training_set_index"] = next((i for i, item in enumerate(exercises[current_exercise + 1].get("sets", [])) if not item.get("completed")), 0)
        cycle = start_rest_cycle(90, datetime.datetime.now())
        session["rest_cycle"] = cycle
        session["rest_until"] = cycle["ends_at"]
        persist_session(session)
        rest_notifier.trigger_after(str(cycle.get("id", "")), 90)
        refresh()

    def complete_rest_if_elapsed(session, now=None):
        cycle = session.get("rest_cycle") if isinstance(session, dict) else None
        if not isinstance(cycle, dict):
            return False
        finished, should_notify = finish_rest_cycle(cycle, now or datetime.datetime.now())
        if finished == cycle:
            return False
        session["rest_cycle"] = finished
        session["rest_until"] = ""
        persist_session(session)
        if should_notify:
            rest_notifier.trigger(str(finished.get("id", "")))
        return True

    def adjust_rest(seconds):
        session = session_data()
        cycle = session.get("rest_cycle") if session else None
        if not session or not isinstance(cycle, dict):
            return
        cycle_id = str(cycle.get("id", ""))
        rest_notifier.cancel(cycle_id)
        session["rest_cycle"] = adjust_rest_cycle(cycle, seconds, datetime.datetime.now())
        session["rest_until"] = session["rest_cycle"].get("ends_at", "") if session["rest_cycle"].get("status") == "running" else ""
        persist_session(session)
        if not complete_rest_if_elapsed(session) and session["rest_cycle"].get("status") == "running":
            remaining = rest_remaining_seconds(session["rest_cycle"], datetime.datetime.now())
            rest_notifier.trigger_after(cycle_id, remaining)
        refresh()

    def toggle_rest_pause(e=None):
        session = session_data()
        cycle = session.get("rest_cycle") if session else None
        if not session or not isinstance(cycle, dict):
            return
        cycle_id = str(cycle.get("id", ""))
        rest_notifier.cancel(cycle_id)
        if cycle.get("status") == "paused":
            cycle = resume_rest_cycle(cycle, datetime.datetime.now())
        else:
            cycle = pause_rest_cycle(cycle, datetime.datetime.now())
        session["rest_cycle"] = cycle
        session["rest_until"] = cycle.get("ends_at", "") if cycle.get("status") == "running" else ""
        persist_session(session)
        if cycle.get("status") == "running":
            rest_notifier.trigger_after(cycle_id, rest_remaining_seconds(cycle, datetime.datetime.now()))
        refresh()

    def skip_rest(e=None):
        session = session_data()
        cycle = session.get("rest_cycle") if session else None
        if not session or not isinstance(cycle, dict):
            return
        rest_notifier.cancel(str(cycle.get("id", "")), release_claim=False)
        session["rest_cycle"] = skip_rest_cycle(cycle, datetime.datetime.now())
        session["rest_until"] = ""
        persist_session(session)
        refresh()

    def finalize_session(incomplete=False):
        session = session_data()
        if not session:
            return
        active_rest = session.get("rest_cycle") if isinstance(session.get("rest_cycle"), dict) else None
        if active_rest:
            rest_notifier.cancel(str(active_rest.get("id", "")), release_claim=False)
        session["status"] = "completed"
        session["incomplete"] = bool(incomplete)
        session["ended_at"] = iso_now()
        session["rest_until"] = ""
        session["rest_cycle"] = None
        session["total_duration_min"] = round(elapsed_seconds(session) / 60, 1)
        state["training"]["total_duration_min"] = str(session["total_duration_min"])
        state["training"]["sessions"] = append_session_once(state["training"].get("sessions", []), session)
        persist_session(session)
        refresh()
        snack("未完整训练已保存" if incomplete else "训练完成，成绩已保存")

    def finish_session(e=None):
        session = session_data()
        if not session:
            return
        completion = session_completion_state(session)
        remaining = completion["remaining_sets"]
        all_completed = completion["all_sets_completed"]
        dialog_width = responsive_width()
        confirm_dlg = dialog_base(
            "结束训练？",
            ft.Column([
                ft.Text(
                    "全部训练组已完成。" if all_completed else f"还有 {remaining} 组没有完成。",
                    size=14,
                    weight="bold",
                    color=TEXT,
                ),
                small_text("确认结束并保存本次成绩，避免误触。" if all_completed else "可以继续训练，也可以按未完整训练保存当前成绩。"),
            ], width=dialog_width, spacing=8, tight=True),
            [
                ft.Container(
                    content=ft.Row([
                        make_button("继续训练", on_click=lambda e: close_control(confirm_dlg), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                        make_button("确认结束", on_click=lambda e: (close_control(confirm_dlg), finalize_session(not all_completed)), bgcolor="#FCECEC", color=RED, expand=True),
                    ], spacing=8),
                    width=dialog_width,
                ),
            ],
            on_close=lambda e: close_control(confirm_dlg),
        )
        open_control(confirm_dlg)

    def repeat_session(e=None):
        previous = session_data()
        if not previous:
            return
        create_empty_session()
        session = session_data()
        for exercise in previous.get("exercises", []):
            copied = json.loads(json.dumps(exercise, ensure_ascii=False))
            copied["id"] = f"session_exercise_{uuid.uuid4().hex}"
            for index, item in enumerate(copied.get("sets", [])):
                item.update({"id": f"set_{uuid.uuid4().hex}", "order": index + 1, "completed": False, "completed_at": ""})
            session["exercises"].append(copied)
        persist_session(session)
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
                make_button("今日", on_click=lambda e: load_record_for_date(date.today().isoformat()), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
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
            state["profile_inited"] = True
            save_profile_from_state()
            save_current()
            refresh()
            snack("已更新基础信息")

        def set_day_type(day_type):
            state["day_type"] = day_type
            save_current()
            refresh()

        def day_type_button(day_type):
            selected = state["day_type"] == day_type
            return make_button(day_type.replace("日", ""), on_click=lambda e, d=day_type: set_day_type(d), bgcolor=PRIMARY if selected else PRIMARY_SOFT, color="#FFFFFF" if selected else GREEN, expand=True)

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

        items = []

        def add_item(text, color=TEXT):
            items.append({"text": text, "color": color})

        def macro_item(label, current, low, high):
            current = to_float(current)
            low = to_float(low)
            high = to_float(high)
            if current < low:
                add_item(f"{label}偏低，还差 {round(low - current, 1):g}g 到目标下限", ORANGE)
            elif current > high:
                add_item(f"{label}偏高，已超出 {round(current - high, 1):g}g", RED)

        carb_training_note = training_carb_warning()
        if carb_training_note:
            add_item(carb_training_note, ORANGE)

        is_today_record = state["date"] == date.today().isoformat()
        is_evening = is_today_record and datetime.datetime.now().hour >= 17
        evening_covers = set()
        if is_evening:
            carb = to_float(total["carb"])
            protein = to_float(total["protein"])
            dinner_recorded = bool(state.get("meals", {}).get("晚餐"))
            carb_near_limit = carb >= to_float(targets["carb_max"]) * 0.85
            carb_over = carb > to_float(targets["carb_max"])
            protein_low = protein < to_float(targets["protein_min"])
            carb_remaining = max(0, round(to_float(targets["carb_max"]) - carb, 1))
            carb_excess = max(0, round(carb - to_float(targets["carb_max"]), 1))
            protein_gap = max(0, round(to_float(targets["protein_min"]) - protein, 1))
            has_late_training = any(
                isinstance(item, dict) and item.get("intensity") == "高强度"
                for item in state.get("training", {}).get("targets", [])
            )
            if carb_over:
                training_text = "；高强度训练后按计划补给，避免额外增加主食" if has_late_training else "；后续避免额外增加主食"
                protein_text = f"；蛋白还差约 {protein_gap:g}g，优先瘦肉、蛋、奶或乳清" if protein_low else ""
                add_item(f"今天碳水已超 {carb_excess:g}g{training_text}{protein_text}", RED)
                evening_covers.add("carb")
                if protein_low:
                    evening_covers.add("protein")
            elif carb_near_limit and protein_low:
                prefix = "后续" if dinner_recorded else "今晚"
                add_item(f"{prefix}剩余碳水约 {carb_remaining:g}g；蛋白还差约 {protein_gap:g}g，优先瘦肉、蛋、奶或乳清", ORANGE)
                evening_covers.update({"carb", "protein"})
            elif carb_near_limit:
                prefix = "后续" if dinner_recorded else "今晚"
                add_item(f"{prefix}剩余碳水约 {carb_remaining:g}g，主食按余量控制，搭配蔬菜和瘦肉", ORANGE)
                evening_covers.add("carb")
            elif protein_low:
                prefix = "今天后续" if dinner_recorded else "晚餐"
                add_item(f"{prefix}优先补蛋白，还差 {protein_gap:g}g；选瘦肉、蛋、奶或乳清", ORANGE)
                evening_covers.add("protein")

        if "carb" not in evening_covers:
            macro_item("碳水", total["carb"], targets["carb_min"], targets["carb_max"])
        if "protein" not in evening_covers:
            macro_item("蛋白", total["protein"], targets["protein_min"], targets["protein_max"])
        macro_item("脂肪", total["fat"], targets["fat_min"], targets["fat_max"])
        water_total = int(sum(state.get("water", [])))
        if water_total < 2000:
            add_item(f"饮水未达标，还差 {2000 - water_total} ml", SKY_BLUE)

        sl = state.get("sleep", {})
        sleep_minutes = sleep_total_minutes()
        has_sleep_record = bool(sl.get("bed_time") or sl.get("wake_time") or sl.get("naps"))
        if not has_sleep_record:
            add_item("睡眠未记录", ORANGE)
        elif sleep_minutes < 420:
            add_item(f"睡眠少于 7 小时，目前 {format_minutes(sleep_minutes)}", ORANGE)

        tr = state.get("training", {})
        has_training_record = bool(
            str(tr.get("total_duration_min", "")).strip()
            or str(tr.get("total_calories_kcal", "")).strip()
            or str(tr.get("summary_note", "")).strip()
            or tr.get("targets")
            or tr.get("session")
            or tr.get("sessions")
        )
        if not has_training_record:
            add_item("训练未记录", SUB)

        advice_title = "今日执行建议" if is_today_record else "该日执行建议"
        pending_count = len(items)
        advice_box = ft.Container()
        if items:
            expanded = bool(state.get("advice_expanded", False))

            def toggle_advice(e=None):
                state["advice_expanded"] = not bool(state.get("advice_expanded", False))
                refresh()

            def keep_current_carb_day(e=None):
                state["training"]["carb_reminder_dismissed_signature"] = training_signature()
                save_current()
                refresh()

            def apply_recommended_carb_day(e=None):
                recommended = recommend_carb_day(state.get("training", {}))
                if recommended:
                    set_day_type(recommended)

            shown_items = items if expanded else items[:1]
            advice_parts = [
                ft.Text(
                    item["text"],
                    size=12,
                    color=item["color"],
                    max_lines=None if expanded else 1,
                    overflow=None if expanded else "ellipsis",
                )
                for item in shown_items
            ]
            header_controls = [
                small_text(advice_title, color=SUB),
                ft.Row([
                    small_text(f"{pending_count} 项", color=SUB),
                    ft.IconButton(
                        icon=ft.Icons.EXPAND_LESS if expanded else ft.Icons.EXPAND_MORE,
                        icon_size=17,
                        icon_color=SUB,
                        tooltip="收起" if expanded else "查看全部",
                        width=28,
                        height=28,
                        padding=0,
                        on_click=toggle_advice,
                    ),
                ], spacing=0),
            ]
            action_controls = []
            if expanded and carb_training_note:
                action_controls.append(ft.Row([
                    make_button("按建议调整", on_click=apply_recommended_carb_day, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                    make_button("保持当前", on_click=keep_current_carb_day, bgcolor="#F3F4F6", color=SUB, expand=True),
                ], spacing=6))
            advice_box = ft.Container(
                content=ft.Column([
                    ft.Row(header_controls, alignment="spaceBetween"),
                    ft.Column(advice_parts, spacing=2),
                    *action_controls,
                ], spacing=4),
                bgcolor=SURFACE,
                border=thin_border(),
                border_radius=8,
                padding=8,
            )

        return card(ft.Column([
            ft.Row([section_title("基础信息 / 目标"), make_button("更新", on_click=apply_profile, bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
            ft.Row([weight_field, bodyfat_field], spacing=8, vertical_alignment="start"),
            prev_box,
            ft.Row([day_type_button("高碳日"), day_type_button("中碳日"), day_type_button("低碳日")], spacing=7),
            ft.Row([
                target_box("碳水", compact_range_text(targets["carb_min"], targets["carb_max"])),
                target_box("蛋白", compact_range_text(targets["protein_min"], targets["protein_max"])),
                target_box("脂肪", compact_range_text(targets["fat_min"], targets["fat_max"]))
            ], spacing=7),
            macro_bars,
            advice_box,
        ], spacing=8))

    def render_today_dashboard():
        total = daily_total()
        targets = get_targets()
        eva = evaluate(total)
        active_session_date = find_active_session_date()
        session = session_model()
        training_status = session.status if session else "planned"
        completed = completed_set_count(session) if session else 0
        planned = planned_set_count(session) if session else 0

        macro_card = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([small_text("今日摄入"), ft.Text(f"{total['kcal']:g}", size=40, weight="bold", color=TEXT), small_text(f"目标约 {eva['kcal_target']:g} kcal")], spacing=2),
                    pill(state["day_type"], ORANGE if state["day_type"] == "高碳日" else SKY_BLUE if state["day_type"] == "中碳日" else "#7C5CC4"),
                ], alignment="spaceBetween", vertical_alignment="start"),
                macro_progress_bar("碳水", total["carb"], target_min=targets["carb_min"], target_max=targets["carb_max"], kind="carb", width=responsive_bar_width()),
                macro_progress_bar("蛋白", total["protein"], target_min=targets["protein_min"], target_max=targets["protein_max"], kind="protein", width=responsive_bar_width()),
                macro_progress_bar("脂肪", total["fat"], target_min=targets["fat_min"], target_max=targets["fat_max"], kind="fat", width=responsive_bar_width()),
            ], spacing=8),
            bgcolor="#FFFFFF", border=thin_border(), border_radius=12, padding=18, margin=8,
        )

        if active_session_date and active_session_date != state.get("date"):
            training_title = "继续跨日训练"
            training_subtitle = f"训练开始于 {active_session_date}，点击恢复"
            training_icon = ft.Icons.PLAY_CIRCLE_FILLED
        elif training_status == "active":
            training_title = "继续训练"
            training_subtitle = f"已完成 {completed}/{planned} 组 · {clock_text(elapsed_seconds(session_data()))}"
            training_icon = ft.Icons.PLAY_CIRCLE_FILLED
        elif training_status == "completed":
            training_title = "今日训练已完成"
            training_subtitle = f"{completed} 组 · 容量 {session_volume(session):g} kg"
            training_icon = ft.Icons.EMOJI_EVENTS
        else:
            training_title = "开始今天的训练"
            training_subtitle = "动作、组数和计时都在训练页完成"
            training_icon = ft.Icons.FITNESS_CENTER

        training_card = ft.Container(
            content=ft.Row([
                ft.Container(content=ft.Icon(training_icon, size=32, color="#FFFFFF"), width=56, height=56, bgcolor="#0E604E", border_radius=14, alignment=ft.Alignment.CENTER),
                ft.Column([ft.Text(training_title, size=20, weight="bold", color="#FFFFFF"), ft.Text(training_subtitle, size=14, color="#EAFBF5", weight="bold")], expand=True, spacing=4),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color="#FFFFFF"),
            ], spacing=12, vertical_alignment="center"),
            bgcolor="#116E59", border_radius=12, padding=18, margin=8,
            on_click=lambda e: resume_session_date(active_session_date) if active_session_date and active_session_date != state.get("date") else set_view("training"),
        )

        def meal_tile(meal):
            items = state.get("meals", {}).get(meal, [])
            count = len(items) if isinstance(items, list) else 0
            return ft.Container(
                content=ft.Column([
                    ft.Text(meal, size=13, weight="bold", color=TEXT),
                    ft.Text(f"已记 {count} 项" if count else "未记录 +", size=14, color=PRIMARY if count else SUB, weight="bold", max_lines=1, overflow="ellipsis"),
                ], horizontal_alignment="center", alignment="center", spacing=3),
                height=66, bgcolor="#FFFFFF", border=thin_border(PRIMARY if count else BORDER), border_radius=10, expand=True,
                ink=True,
                on_click=lambda e, m=meal: (state.update({"selected_meal": m}), set_view("diet")),
            )

        meals_card = ft.Container(
            content=ft.Column([
                ft.Row([section_title("六餐记录"), small_text("点击进入对应餐次")], alignment="spaceBetween"),
                ft.Row([meal_tile(m) for m in MEALS[:3]], spacing=8),
                ft.Row([meal_tile(m) for m in MEALS[3:]], spacing=8),
            ], spacing=10), bgcolor="#FFFFFF", border=thin_border(), border_radius=12, padding=16, margin=8,
        )

        water_total = int(sum(state.get("water", [])))
        sleep_text = format_minutes(sleep_total_minutes()) if sleep_total_minutes() else "未记录"
        recovery_card = ft.Container(
            content=ft.Column([
                ft.Row([section_title("身体与恢复"), ft.Icon(ft.Icons.CHEVRON_RIGHT, color=SUB)], alignment="spaceBetween"),
                ft.Row([
                    ft.Column([small_text("饮水"), ft.Text(f"{water_total} ml", size=15, weight="bold", color=TEXT)], expand=True),
                    ft.Column([small_text("补剂"), ft.Text(f"{len(state.get('supplements', []))} 项", size=15, weight="bold", color=TEXT)], expand=True),
                    ft.Column([small_text("睡眠"), ft.Text(sleep_text, size=15, weight="bold", color=TEXT)], expand=True),
                ], spacing=8),
            ], spacing=12), bgcolor="#FFFFFF", border=thin_border(), border_radius=12, padding=16, margin=8,
            on_click=lambda e: set_view("daily_details"),
        )
        return ft.Column([macro_card, training_card, meals_card, recovery_card], spacing=0)

    def render_recovery_page():
        weight = mobile_text_field("体重 kg", state.get("weight", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        bodyfat = mobile_text_field("体脂 %", state.get("bodyfat", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)

        def save_body_metric(metric):
            state["weight"] = str(weight.value or "")
            state["bodyfat"] = str(bodyfat.value or "")
            previous = state.get("measurement", {}) if isinstance(state.get("measurement"), dict) else {}
            measured_weight = state["weight"] if metric == "weight" else previous.get("weight_kg") if previous.get("weight_measured") else None
            measured_bodyfat = state["bodyfat"] if metric == "bodyfat" else previous.get("bodyfat_percent") if previous.get("bodyfat_measured") else None
            state["measurement"] = make_body_measurement(
                weight_kg=measured_weight,
                bodyfat_percent=measured_bodyfat,
                measured_at=iso_now(),
            )
            save_profile_from_state()
            save_current()
            refresh()
            snack("体重已记录" if metric == "weight" else "体脂已记录")

        body_card = card(ft.Column([
            ft.Row([section_title("今日身体"), small_text("可分别标记实测")], alignment="spaceBetween"),
            ft.Row([
                ft.Column([weight, make_button("记录体重", on_click=lambda e: save_body_metric("weight"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True)], spacing=6, expand=True),
                ft.Column([bodyfat, make_button("记录体脂", on_click=lambda e: save_body_metric("bodyfat"), bgcolor="#E8F1F6", color=SKY_BLUE, expand=True)], spacing=6, expand=True),
            ], spacing=8, vertical_alignment="start"),
        ], spacing=10), padding=14)
        return ft.Column([
            ft.Container(content=ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="返回今日", on_click=lambda e: set_view("today")),
                ft.Text("身体与恢复", size=20, weight="bold", color=TEXT),
            ], spacing=4), padding=8),
            body_card,
            render_water(),
            render_supp_today(),
            render_sleep(),
        ], spacing=0)

    def render_diet_page():
        total = daily_total()
        targets = get_targets()

        def set_day(day_name):
            state["day_type"] = day_name
            save_current()
            refresh()

        day_buttons = []
        for day_name in DAY_TYPES:
            selected = state["day_type"] == day_name
            day_buttons.append(make_button(day_name, on_click=lambda e, d=day_name: set_day(d), bgcolor=PRIMARY if selected else PRIMARY_SOFT, color="#FFFFFF" if selected else GREEN, expand=True))
        summary = card(ft.Column([
            ft.Row([section_title("饮食总览"), make_button("食物库", on_click=lambda e: set_view("foods"), icon=ft.Icons.RESTAURANT_MENU, bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
            ft.Row(day_buttons, spacing=7),
            macro_progress_bar("碳水", total["carb"], target_min=targets["carb_min"], target_max=targets["carb_max"], kind="carb", width=responsive_bar_width()),
            macro_progress_bar("蛋白", total["protein"], target_min=targets["protein_min"], target_max=targets["protein_max"], kind="protein", width=responsive_bar_width()),
            macro_progress_bar("脂肪", total["fat"], target_min=targets["fat_min"], target_max=targets["fat_max"], kind="fat", width=responsive_bar_width()),
        ], spacing=8), padding=14)
        active = DietViewState(normalize_diet_view(state.get("current_view")))

        def select_diet_view(view):
            set_view(diet_route_for_view(view))

        shell = build_diet_shell(
            active,
            DietShellRenderers(
                today_diet=lambda: ft.Column([summary, render_diet()], spacing=0),
                food_library=render_food_library,
                supplement_library=render_supp_library,
            ),
            select_diet_view,
        )
        return ft.Container(content=shell, padding=ft.Padding(left=8, top=8, right=8, bottom=0))

    def render_badge_wall():
        results = achievement_view_models(evaluate_achievements(records))
        unlocked_count = sum(1 for item in results if item.get("unlocked"))
        expanded = bool(state.get("achievements_expanded", False))
        ranked = list(results)
        visible = ranked if expanded else ranked[:8]
        tier_colors = {
            "bronze": "#A76D3B",
            "silver": "#73818A",
            "gold": "#B98518",
            "diamond": "#277EA8",
        }

        def toggle_achievements(e=None):
            state["achievements_expanded"] = not expanded
            refresh()

        tiles = []
        for item in visible:
            unlocked = bool(item.get("unlocked"))
            progress = max(0.0, min(1.0, to_float(item.get("progress"))))
            current = to_float(item.get("current"))
            target = to_float(item.get("target"))
            color = tier_colors.get(item.get("tier"), "#7157A8" if item.get("hidden") else GREEN)
            tiles.append(ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.EMOJI_EVENTS if unlocked else ft.Icons.LOCK_OUTLINE, size=20, color=color if unlocked else "#98A3A0"),
                        ft.Text(item.get("title", "成就"), size=12, weight="bold", color=TEXT if unlocked else SUB, expand=True, max_lines=1, overflow="ellipsis"),
                    ], spacing=6),
                    ft.Text(item.get("description", ""), size=12, color=SUB, max_lines=2, overflow="ellipsis"),
                    ft.ProgressBar(value=progress, color=color, bgcolor=BAR_BG, height=5),
                    small_text("已解锁" if unlocked else f"{current:g} / {target:g}"),
                ], spacing=5),
                bgcolor="#F9FBFA" if not unlocked else "#FFF9EB",
                border=thin_border(color if unlocked else BORDER),
                border_radius=8,
                height=116,
                expand=True,
                padding=9,
            ))

        rows = [ft.Row(tiles[index:index + 2], spacing=8) for index in range(0, len(tiles), 2)]
        return card(ft.Column([
            ft.Row([section_title("成就系统"), ft.Text(f"{unlocked_count} / {len(results)}", size=12, weight="bold", color=GREEN)], alignment="spaceBetween"),
            small_text("48 项阶梯成就 · 8 项隐藏成就 · 真实数据计算"),
            *rows,
            make_button("收起" if expanded else "查看全部成就", on_click=toggle_achievements, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
        ], spacing=9), padding=14)

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
            return ft.Container(content=ft.Text(label, size=12, weight="bold", color="#FFFFFF" if selected else GREEN, text_align="center", max_lines=1, overflow="ellipsis"), bgcolor=PRIMARY if selected else PRIMARY_SOFT, border=thin_border(PRIMARY if selected else BORDER), border_radius=8, height=44, alignment=ft.Alignment.CENTER, padding=6, expand=True, on_click=lambda e, m=meal: set_selected_meal(m))

        def meal_totals(meal):
            t = {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}
            items = state.get("meals", {}).get(meal, []) if isinstance(state.get("meals"), dict) else []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                for k in t:
                    t[k] += to_float(item.get(k))
            return {k: round(v, 1) for k, v in t.items()}

        content_rows = []
        if selected_meal == "汇总":
            any_record = False
            for meal in MEALS:
                raw_items = state.get("meals", {}).get(meal, []) if isinstance(state.get("meals"), dict) else []
                items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
                if not items:
                    continue
                any_record = True
                mt = meal_totals(meal)
                names = "、".join([str(x.get("food", "")) for x in items[:3]])
                if len(items) > 3:
                    names += "…"
                content_rows.append(ft.Container(content=ft.Column([
                    ft.Row([ft.Text(meal, size=13, weight="bold", color=TEXT), small_text(f"{mt['kcal']} kcal｜碳{mt['carb']} 蛋{mt['protein']} 脂{mt['fat']}")], alignment="spaceBetween"),
                    ft.Text(names, size=12, color=SUB) if names else ft.Container(),
                ], spacing=2), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))
            if not any_record:
                content_rows.append(ft.Container(content=small_text("暂无饮食记录"), bgcolor="#FAFAFA", border_radius=12, padding=10))
            header_right = f"{total['kcal']} kcal｜碳 {total['carb']}g｜蛋白 {total['protein']}g｜脂肪 {total['fat']}g"
        else:
            raw_meal_items = state.get("meals", {}).get(selected_meal, []) if isinstance(state.get("meals"), dict) else []
            meal_items = [item for item in raw_meal_items if isinstance(item, dict)] if isinstance(raw_meal_items, list) else []
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
            ft.Row([section_title("饮食记录"), make_button("添加", on_click=lambda e, m=(meal_for_current_time() if selected_meal=="汇总" else selected_meal): open_add_food_dialog(m), icon=ft.Icons.ADD, expand=False)], alignment="spaceBetween"),
            ft.Row([meal_button("汇总"), meal_button("早餐"), meal_button("午餐"), meal_button("晚餐")], spacing=5),
            ft.Row([meal_button("练前"), meal_button("练后"), meal_button("偷吃")], spacing=5),
            ft.Container(content=ft.Column([ft.Row([ft.Text(selected_meal, size=13, weight="bold", color=TEXT), small_text(header_right)], alignment="spaceBetween"), ft.Column(content_rows, spacing=1)], spacing=6), bgcolor="#FFFFFF", border_radius=8, padding=8),
        ], spacing=8))

    def render_training():
        tr = state["training"]
        target_controls = []
        for idx, t in enumerate(tr.get("targets", [])):
            intensity_text = t.get("intensity", "中等")
            target_controls.append(ft.Container(content=ft.Row([
                ft.Column([ft.Text(f"{t.get('target','')} · {intensity_text}", size=13, weight="bold", color=TEXT), small_text(f"{t.get('detail','')}" + (f"｜{t.get('note','')}" if t.get("note") else ""))], expand=True, spacing=1),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, icon_size=18, on_click=lambda e, i=idx: delete_training(i)),
            ]), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))
        if not target_controls:
            target_controls.append(ft.Container(content=small_text("暂无训练目标"), bgcolor="#FAFAFA", border_radius=12, padding=10))

        duration_field = mobile_text_field(label="时长 min", value=tr.get("total_duration_min", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True, on_change=lambda e: (tr.update({"total_duration_min": e.control.value}), save_current()))
        calories_field = mobile_text_field(label="消耗 kcal", value=tr.get("total_calories_kcal", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True, on_change=lambda e: (tr.update({"total_calories_kcal": e.control.value}), save_current()))
        def save_training_note(e=None):
            tr["summary_note"] = note_field.value or ""
            save_current()
            refresh()

        note_field = mobile_text_field(label="训练备注", value=tr.get("summary_note", ""), expand=True, on_blur=save_training_note, on_submit=save_training_note)
        fatigue_dd = mobile_dropdown(label="状态", value=tr.get("fatigue_status", "状态一般"), options=[ft.dropdown.Option(x) for x in FATIGUE_OPTIONS], on_change=lambda e: (tr.update({"fatigue_status": e.control.value}), save_current(), refresh()), expand=True)

        return card(ft.Column([
            ft.Row([section_title("训练记录"), make_button("添加", on_click=lambda e: open_training_dialog(), icon=ft.Icons.ADD)], alignment="spaceBetween"),
            ft.Row([duration_field, calories_field], spacing=8, vertical_alignment="start"),
            note_field,
            fatigue_dd,
            ft.Column(target_controls, spacing=2),
        ], spacing=8))

    def render_training_workspace():
        session = session_model()
        raw_session = session_data()
        if not session or not raw_session:
            return ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.FITNESS_CENTER, size=54, color="#FFFFFF"),
                        ft.Text("今天练什么？", size=25, weight="bold", color="#FFFFFF"),
                        ft.Text("从上次训练继续，或创建一场自由训练", size=14, color="#EAFBF5", weight="bold", text_align="center"),
                        ft.Row([
                            make_button("复用历史训练", on_click=reuse_history_session, bgcolor="#FFFFFF", color=GREEN, expand=True),
                            make_button("自由训练", on_click=lambda e: (create_empty_session(), refresh()), bgcolor="#125F4D", color="#FFFFFF", expand=True),
                        ], spacing=8),
                    ], horizontal_alignment="center", spacing=14),
                    bgcolor="#116E59", border_radius=12, padding=24, margin=8,
                ),
                card(ft.Column([
                    section_title("训练准备"),
                    small_text("添加动作后即可开始，重量与次数会完整保存。"),
                    make_button("添加第一个动作", on_click=lambda e: open_add_exercise_dialog(), icon=ft.Icons.ADD, expand=True, height=54),
                ], spacing=10), padding=14),
            ], spacing=0)

        status = session.status
        if status == "completed":
            completed = completed_set_count(session)
            planned = planned_set_count(session)
            volume = session_volume(session)
            duration = session.total_duration_min or round(elapsed_seconds(raw_session) / 60, 1)
            exercise_rows = []
            for exercise in session.exercises:
                done = sum(1 for item in exercise.sets if item.completed)
                exercise_rows.append(ft.Container(
                    content=ft.Row([
                        ft.Column([ft.Text(exercise.name, size=15, weight="bold", color=TEXT), small_text(f"{exercise.body_part} · 已完成 {done}/{len(exercise.sets)} 组")], expand=True, spacing=3),
                        ft.Text(f"{sum((item.weight_kg or 0) * (item.reps or 0) for item in exercise.sets if item.completed):g} kg", size=15, weight="bold", color=PRIMARY),
                    ]), bgcolor="#FFFFFF", border=thin_border(), border_radius=10, padding=12,
                ))
            return ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.EMOJI_EVENTS, size=48, color="#FFD166"),
                        ft.Text(session_summary_title(raw_session), size=28, weight="bold", color="#FFFFFF"),
                        ft.Row([
                            ft.Column([ft.Text(f"{duration:g}", size=26, weight="bold", color="#FFFFFF"), ft.Text("分钟", size=12, color="#EAFBF5", weight="bold")], horizontal_alignment="center", expand=True),
                            ft.Column([ft.Text(f"{completed}/{planned}", size=26, weight="bold", color="#FFFFFF"), ft.Text("完成组", size=12, color="#EAFBF5", weight="bold")], horizontal_alignment="center", expand=True),
                            ft.Column([ft.Text(f"{volume:g}", size=26, weight="bold", color="#FFFFFF"), ft.Text("总容量 kg", size=12, color="#EAFBF5", weight="bold")], horizontal_alignment="center", expand=True),
                        ], spacing=8),
                    ], horizontal_alignment="center", spacing=12),
                    bgcolor="#173E35", border_radius=12, padding=22, margin=8,
                ),
                card(ft.Column([section_title("动作明细"), *exercise_rows], spacing=8), padding=14),
                card(ft.Column([
                    section_title("练后建议"),
                    ft.Text(training_carb_warning() or "训练成绩已计入今天记录，记得补充练后餐和水分。", size=14, color=TEXT),
                    ft.Row([
                        make_button("再练一次", on_click=repeat_session, icon=ft.Icons.REPLAY, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                        make_button("新训练", on_click=lambda e: (create_empty_session(), refresh()), icon=ft.Icons.ADD, expand=True),
                    ], spacing=8),
                ], spacing=10), padding=14),
            ], spacing=0)

        if status == "active":
            session, exercise, training_set = current_training_items()
            model = TrainingSession.from_dict(session)
            completed = completed_set_count(model)
            planned = planned_set_count(model)
            progress = session_progress(model)
            elapsed = ft.Text(clock_text(elapsed_seconds(session)), size=50, weight="bold", color="#FFFFFF", text_align="center")
            training_clock_refs["elapsed"] = elapsed
            rest_cycle = session.get("rest_cycle") if isinstance(session.get("rest_cycle"), dict) else None
            rest_status = rest_cycle.get("status") if rest_cycle else ""
            rest_seconds = rest_remaining_seconds(rest_cycle, datetime.datetime.now()) if rest_cycle else 0
            rest_visible = rest_status in {"running", "paused"}
            rest = ft.Text(f"{rest_seconds}", size=68, weight="bold", color="#FFD166", text_align="center")
            training_clock_refs["rest"] = rest

            set_chips = []
            for index, item in enumerate(exercise.get("sets", []) if exercise else []):
                selected = index == state.get("training_set_index", 0)
                done = bool(item.get("completed"))
                set_chips.append(ft.Container(
                    content=ft.Container(
                        content=ft.Text(str(index + 1), size=12, weight="bold", color="#FFFFFF" if done or selected else "#AAB7B3"),
                        width=36, height=36, border_radius=18, alignment=ft.Alignment.CENTER,
                        bgcolor=PRIMARY if done else "#41514C" if selected else "#27312E",
                    ),
                    width=48, height=48, border_radius=24, alignment=ft.Alignment.CENTER,
                    on_click=lambda e, i=index: (state.update({"training_set_index": i}), refresh()),
                ))

            weight = to_float(training_set.get("weight_kg"), 0) if training_set else 0
            reps = int(to_float(training_set.get("reps"), 0)) if training_set else 0
            set_done = bool(training_set and training_set.get("completed"))
            main_action = make_button("撤销本组" if set_done else "完成本组", on_click=undo_current_set if set_done else complete_current_set, icon=ft.Icons.UNDO if set_done else ft.Icons.CHECK_CIRCLE, bgcolor="#56635F" if set_done else "#21A366", color="#FFFFFF", expand=True, height=64)
            end_training_button = ft.Container(
                content=ft.Text("结束", size=13, weight="bold", color="#F97066", max_lines=1, overflow="ellipsis"),
                width=64,
                height=48,
                bgcolor="#241B1B",
                border=thin_border("#F97066"),
                border_radius=8,
                alignment=ft.Alignment.CENTER,
                on_click=finish_session,
            )
            focus_controls = [
                ft.Row([
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_color="#FFFFFF", tooltip="返回今日", width=48, height=48, on_click=lambda e: set_view("today")),
                    ft.Text(f"完成 {completed}/{planned} 组", color="#EAFBF5", size=14, weight="bold", text_align="center", expand=True),
                    end_training_button,
                ], alignment="spaceBetween", spacing=12),
                ft.Column([small_text("训练时长", color="#B9C8C3"), elapsed], horizontal_alignment="center", spacing=0),
                ft.ProgressBar(value=progress, color="#21A366", bgcolor="#31413C", height=8),
            ]
            if rest_visible:
                focus_controls.extend([
                    ft.Container(content=ft.Column([
                        ft.Text("组间休息" if rest_status != "paused" else "组间休息已暂停", size=16, color="#FFFFFF", weight="bold"),
                        rest,
                        ft.Row([
                            make_button("-10秒", on_click=lambda e: adjust_rest(-10), bgcolor="#4A5652", color="#FFFFFF", expand=True, height=48),
                            make_button("继续" if rest_status == "paused" else "暂停", on_click=toggle_rest_pause, bgcolor="#4A5652", color="#FFFFFF", expand=True, height=48),
                            make_button("+10秒", on_click=lambda e: adjust_rest(10), bgcolor="#4A5652", color="#FFFFFF", expand=True, height=48),
                            make_button("跳过", on_click=skip_rest, bgcolor="#4A5652", color="#FFFFFF", expand=True, height=48),
                        ], spacing=6),
                    ], horizontal_alignment="center", spacing=8), bgcolor="#252F2C", border_radius=16, padding=16),
                ])
            focus_controls.extend([
                ft.Container(content=ft.Column([
                    ft.Row([ft.Text(exercise.get("name", "当前动作"), size=22, weight="bold", color="#FFFFFF"), ft.Text(f"动作 {state.get('training_exercise_index', 0)+1}/{len(session.get('exercises', []))}", size=13, color="#D8E2DF", weight="bold")], alignment="spaceBetween"),
                    ft.Row(set_chips, spacing=8, scroll=getattr(getattr(ft, "ScrollMode", object()), "AUTO", "auto")),
                    ft.Row([
                        ft.IconButton(icon=ft.Icons.REMOVE, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: adjust_current("weight_kg", -2.5)),
                        ft.Column([small_text("重量", color="#AFC0BA"), ft.Text(f"{weight:g} kg", size=28, weight="bold", color="#FFFFFF")], horizontal_alignment="center", expand=True, spacing=0),
                        ft.IconButton(icon=ft.Icons.ADD, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: adjust_current("weight_kg", 2.5)),
                    ]),
                    ft.Row([
                        ft.IconButton(icon=ft.Icons.REMOVE, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: adjust_current("reps", -1)),
                        ft.Column([small_text("次数", color="#AFC0BA"), ft.Text(f"{reps} 次", size=28, weight="bold", color="#FFFFFF")], horizontal_alignment="center", expand=True, spacing=0),
                        ft.IconButton(icon=ft.Icons.ADD, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: adjust_current("reps", 1)),
                    ]),
                    main_action,
                    ft.Row([
                        make_button("上一个", on_click=lambda e: move_training(-1), icon=ft.Icons.CHEVRON_LEFT, bgcolor="#303B37", color="#FFFFFF", expand=True),
                        make_button("下一个", on_click=lambda e: move_training(1), icon=ft.Icons.CHEVRON_RIGHT, bgcolor="#303B37", color="#FFFFFF", expand=True),
                    ], spacing=8),
                ], spacing=12), bgcolor="#1B2320", border_radius=16, padding=16),
            ])
            return ft.Container(content=ft.Column(focus_controls, spacing=12), bgcolor="#101513", padding=12, expand=True)

        exercises = raw_session.get("exercises", [])
        exercise_rows = []
        for index, exercise in enumerate(exercises):
            sets = exercise.get("sets", [])
            first = sets[0] if sets else {}
            exercise_rows.append(ft.Container(
                content=ft.Row([
                    ft.Container(content=ft.Text(str(index + 1), color="#FFFFFF", weight="bold"), width=36, height=36, bgcolor=PRIMARY, border_radius=10, alignment=ft.Alignment.CENTER),
                    ft.Column([ft.Text(exercise.get("name", ""), size=16, weight="bold", color=TEXT), small_text(f"{exercise.get('body_part', '')} · {len(sets)} 组 · {to_float(first.get('weight_kg')):g} kg × {int(to_float(first.get('reps')))}")], expand=True, spacing=3),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, on_click=lambda e, i=index: delete_session_exercise(i)),
                ], spacing=10), bgcolor="#FFFFFF", border=thin_border(), border_radius=10, padding=12,
            ))
        return ft.Column([
            ft.Container(content=ft.Column([
                ft.Row([ft.Column([small_text("训练计划", color="#EAFBF5"), ft.Text("今天的训练", size=25, weight="bold", color="#FFFFFF")], spacing=2), ft.Icon(ft.Icons.FITNESS_CENTER, size=42, color="#FFFFFF")], alignment="spaceBetween"),
                ft.Text(f"{len(exercises)} 个动作 · {sum(len(item.get('sets', [])) for item in exercises)} 组", size=14, color="#EAFBF5", weight="bold"),
                make_button("开始训练", on_click=start_session, icon=ft.Icons.PLAY_ARROW, bgcolor="#FFFFFF", color=GREEN, expand=True, height=58),
            ], spacing=12), bgcolor="#116E59", border_radius=12, padding=20, margin=8),
            card(ft.Column([
                ft.Row([section_title("动作安排"), make_button("添加动作", on_click=lambda e: open_add_exercise_dialog(), icon=ft.Icons.ADD, bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
                *(exercise_rows or [ft.Container(content=small_text("还没有动作，先添加一个动作"), bgcolor=SURFACE, border_radius=12, padding=14)]),
            ], spacing=8), padding=14),
            card(ft.Row([
                make_button("复用历史训练", on_click=reuse_history_session, icon=ft.Icons.HISTORY, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                make_button("清空", on_click=lambda e: (create_empty_session(), refresh()), icon=ft.Icons.DELETE_OUTLINE, bgcolor="#FCECEC", color=RED, expand=True),
            ], spacing=8), padding=12),
        ], spacing=0)

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
                bgcolor=PRIMARY_SOFT if active else "#FFFFFF",
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
        ], width=responsive_width(), height=430, spacing=8)

        dlg = dialog_base(
            title,
            content,
            [ft.Container(content=make_button("确定", on_click=confirm, expand=True), width=responsive_width())],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def render_sleep():
        sl = state.setdefault("sleep", {"bed_time": "", "wake_time": "", "naps": []})

        def save_bed(value):
            sl["bed_time"] = value
            save_current()
            refresh()

        def save_wake(value):
            sl["wake_time"] = value
            save_current()
            refresh()

        def open_add_nap_dialog(e=None):
            selected = {"start": "13:00", "end": "14:00"}
            dlg = None

            def set_start(value):
                selected["start"] = value
                start_button.content.value = value
                page.update()

            def set_end(value):
                selected["end"] = value
                end_button.content.value = value
                page.update()

            start_button = time_display_button(
                selected["start"],
                lambda event: open_time_wheel("选择小睡开始", selected["start"], "13", "00", set_start),
            )
            end_button = time_display_button(
                selected["end"],
                lambda event: open_time_wheel("选择小睡结束", selected["end"], "14", "00", set_end),
            )

            def nap_time_line(label, button):
                return ft.Container(
                    content=ft.Row([
                        ft.Text(label, size=13, color=TEXT, weight="bold"),
                        ft.Container(content=button, expand=True),
                    ], spacing=12, vertical_alignment="center"),
                    bgcolor="#FFFFFF",
                    border_radius=8,
                    padding=6,
                )

            def confirm(e=None):
                if duration_between(selected["start"], selected["end"]) <= 0:
                    snack("请填写正确的小睡时间")
                    return
                sl.setdefault("naps", []).append({"start": selected["start"], "end": selected["end"]})
                save_current()
                close_control(dlg)
                refresh()
                snack("已添加小睡")

            dialog_width = responsive_width()
            content = ft.Column([
                small_text("点击时间进行选择"),
                nap_time_line("开始", start_button),
                nap_time_line("结束", end_button),
            ], width=dialog_width, height=175, spacing=10)
            dlg = dialog_base(
                "添加小睡",
                content,
                [ft.Container(content=make_button("保存小睡", on_click=confirm, expand=True), width=dialog_width)],
                on_close=lambda event: close_control(dlg),
            )
            open_control(dlg)

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
            make_button("添加小睡", on_click=open_add_nap_dialog, icon=ft.Icons.ADD, expand=True),
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
                make_button("+250", on_click=lambda e: add_water(250), bgcolor=PRIMARY_SOFT, color=GREEN),
                make_button("+375", on_click=lambda e: add_water(375), bgcolor=PRIMARY_SOFT, color=GREEN),
                make_button("+500", on_click=lambda e: add_water(500), bgcolor=PRIMARY_SOFT, color=GREEN),
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
            ft.Row([ft.Text(f"补剂记录 {selected_count}", size=15, weight="bold"), make_button("管理", on_click=lambda e: set_view("supplements"), bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
            ft.Column(supp_controls, spacing=2),
        ], spacing=8))

    def render_food_library():
        search = mobile_text_field("搜索食物", value="", expand=True)
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

    def make_full_backup_payload():
        return {
            "format": "carbs_king_backup",
            "backup_version": 1,
            "app_version": APP_VERSION,
            "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "daily_records": load_json(RECORD_FILE, {}),
            "food_library": load_json(FOOD_FILE, DEFAULT_FOODS),
            "supplement_library": load_json(SUPP_FILE, DEFAULT_SUPPLEMENTS),
            "user_profile": load_user_profile(),
        }

    def normalize_import_payload(payload):
        """Accept v43+ exported backups and simple raw JSON library files."""
        normalized = {}
        if isinstance(payload, dict):
            expected_types = {
                "daily_records": dict,
                "food_library": list,
                "supplement_library": list,
                "user_profile": dict,
            }
            for key, expected_type in expected_types.items():
                if key in payload:
                    if not isinstance(payload[key], expected_type):
                        raise ValueError(f"{key} 数据格式不正确")
                    normalized[key] = payload[key]

            # Also support a directly copied internal JSON database.
            if not normalized:
                date_keys = [key for key in payload if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(key))]
                if date_keys and len(date_keys) == len(payload):
                    normalized["daily_records"] = payload
                elif any(key in payload for key in ["profile_inited", "height", "activity_habit", "macro_mode"]):
                    normalized["user_profile"] = payload
        elif isinstance(payload, list):
            if not payload:
                raise ValueError("空列表无法判断是食物库还是补剂库")
            if all(isinstance(item, dict) and "base_qty" in item for item in payload):
                normalized["food_library"] = payload
            elif all(isinstance(item, dict) and "default_amount" in item for item in payload):
                normalized["supplement_library"] = payload

        if not normalized:
            raise ValueError("未识别到可导入的碳水大王备份数据")
        return normalized

    def import_summary(import_data):
        parts = []
        if "daily_records" in import_data:
            parts.append(f"历史记录 {len(import_data['daily_records'])} 天")
        if "food_library" in import_data:
            parts.append(f"食物库 {len(import_data['food_library'])} 项")
        if "supplement_library" in import_data:
            parts.append(f"补剂库 {len(import_data['supplement_library'])} 项")
        if "user_profile" in import_data:
            parts.append("个人资料")
        return "、".join(parts)

    def merge_named_items(current_items, imported_items):
        result = [dict(item) for item in current_items if isinstance(item, dict)]
        positions = {
            str(item.get("name", "")).strip(): index
            for index, item in enumerate(result)
            if str(item.get("name", "")).strip()
        }
        for item in imported_items:
            if not isinstance(item, dict):
                continue
            copied = dict(item)
            name = str(copied.get("name", "")).strip()
            if name and name in positions:
                result[positions[name]] = copied
            else:
                if name:
                    positions[name] = len(result)
                result.append(copied)
        return result

    def save_pre_import_snapshot():
        backup_dir = APP_DIR / "import_safety_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_json(backup_dir / f"before_import_{stamp}.json", make_full_backup_payload())

    def apply_import_data(import_data, mode):
        save_pre_import_snapshot()

        if "daily_records" in import_data:
            incoming = import_data["daily_records"]
            if mode == "merge":
                merged_records = dict(records)
                merged_records.update(incoming)
                records.clear()
                records.update(merged_records)
            else:
                records.clear()
                records.update(incoming)
            save_json(RECORD_FILE, records)

        if "food_library" in import_data:
            incoming = import_data["food_library"]
            restored_foods = merge_named_items(foods, incoming) if mode == "merge" else list(incoming)
            foods.clear()
            foods.extend(restored_foods)
            save_json(FOOD_FILE, foods)

        if "supplement_library" in import_data:
            incoming = import_data["supplement_library"]
            restored_supplements = merge_named_items(supplements, incoming) if mode == "merge" else list(incoming)
            supplements.clear()
            supplements.extend(restored_supplements)
            save_json(SUPP_FILE, supplements)

        if "user_profile" in import_data:
            incoming = dict(import_data["user_profile"])
            if mode == "merge":
                restored_profile = load_user_profile()
                restored_profile.update(incoming)
            else:
                restored_profile = incoming
            save_user_profile(restored_profile)

            current_profile = load_user_profile()
            state["weight"] = str(current_profile.get("weight", state.get("weight", "62.5")))
            state["bodyfat"] = str(current_profile.get("bodyfat", state.get("bodyfat", "13")))
            state["height"] = str(current_profile.get("height", state.get("height", "170")))
            state["age"] = str(current_profile.get("age", state.get("age", "30")))
            state["sex"] = str(current_profile.get("sex", state.get("sex", "男")))
            state["activity_habit"] = str(current_profile.get("activity_habit", state.get("activity_habit", "规律训练")))
            state["waist_cm"] = str(current_profile.get("waist_cm", state.get("waist_cm", "")))
            state["arm_cm"] = str(current_profile.get("arm_cm", state.get("arm_cm", "")))
            state["macro_mode"] = current_profile.get("macro_mode", state.get("macro_mode", "auto"))
            state["macro_multipliers"] = json.loads(json.dumps(current_profile.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS)))
            state["profile_inited"] = bool(current_profile.get("profile_inited", state.get("profile_inited", False)))

        load_record_for_date(state.get("date", date.today().isoformat()), autosave=False, show=False)

    def open_import_confirmation(file_name, import_data):
        dlg = None
        summary = import_summary(import_data)

        def confirm(mode):
            try:
                close_control(dlg)
                apply_import_data(import_data, mode)
                snack(f"已{('合并' if mode == 'merge' else '覆盖')}导入：{summary}")
            except Exception as ex:
                snack(f"导入失败：{str(ex)[:60]}")

        dialog_width = responsive_width()
        content = ft.Column([
            ft.Text(file_name, size=13, weight="bold", color=TEXT),
            small_text(f"识别到：{summary}"),
            ft.Container(
                content=small_text("合并：保留现有数据，同日期或同名称以备份为准。\n覆盖：只替换该文件中包含的数据分类。", color=ORANGE),
                bgcolor="#FFF7ED",
                border_radius=8,
                padding=10,
            ),
            small_text("导入前会自动生成一份本地安全快照。"),
        ], width=dialog_width, height=190, spacing=10)
        action_row = ft.Row([
            make_button("取消", on_click=lambda e: close_control(dlg), bgcolor="#F1F1F1", color=SUB, expand=True),
            make_button("合并导入", on_click=lambda e: confirm("merge"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
            make_button("覆盖导入", on_click=lambda e: confirm("replace"), bgcolor="#FDECEC", color=RED, expand=True),
        ], spacing=6)
        dlg = dialog_base(
            "确认导入备份",
            content,
            [ft.Container(content=action_row, width=dialog_width)],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    async def import_backup_handler(e=None):
        try:
            selected_files = await file_picker.pick_files(
                dialog_title="选择碳水大王备份",
                allow_multiple=False,
                with_data=True,
            )
            if not selected_files:
                return
            selected = selected_files[0]
            raw = getattr(selected, "bytes", None)
            if not raw:
                selected_path = getattr(selected, "path", None)
                if selected_path and "://" not in str(selected_path):
                    raw = Path(str(selected_path)).read_bytes()
            if not raw:
                raise ValueError("无法读取所选文件")
            payload = json.loads(raw.decode("utf-8-sig"))
            import_data = normalize_import_payload(payload)
            open_import_confirmation(getattr(selected, "name", "备份文件"), import_data)
        except json.JSONDecodeError:
            snack("导入失败：所选文件不是有效的 JSON 备份")
        except Exception as ex:
            snack(f"导入失败：{str(ex)[:60]}")

    def export_handler(export_kind):
        async def handler(e=None):
            exported_at = datetime.datetime.now().isoformat(timespec="seconds")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            common = {
                "format": "carbs_king_backup",
                "backup_version": 1,
                "app_version": APP_VERSION,
                "exported_at": exported_at,
            }
            export_map = {
                "all": (
                    "完整备份",
                    "full_backup",
                    make_full_backup_payload(),
                ),
                "records": ("历史记录", "daily_records", {**common, "daily_records": load_json(RECORD_FILE, {})}),
                "foods": ("食物库", "food_library", {**common, "food_library": load_json(FOOD_FILE, DEFAULT_FOODS)}),
                "supplements": ("补剂库", "supplement_library", {**common, "supplement_library": load_json(SUPP_FILE, DEFAULT_SUPPLEMENTS)}),
                "profile": ("个人资料", "user_profile", {**common, "user_profile": load_user_profile()}),
            }
            label, file_part, payload = export_map.get(export_kind, export_map["all"])
            file_name = f"carbs_king_{file_part}_{timestamp}.json"
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8-sig")
            try:
                selected_path = await file_picker.save_file(
                    dialog_title=f"导出{label}",
                    file_name=file_name,
                    src_bytes=raw,
                )
                # Desktop only returns a path, so Python must write the bytes.
                # Android/iOS already saved src_bytes and may return a document
                # URI such as /document/primary:Download/..., which pathlib
                # cannot open as a normal filesystem path.
                if selected_path and not page_is_mobile() and not getattr(page, "web", False):
                    output_path = Path(str(selected_path))
                    if not output_path.exists() or output_path.stat().st_size == 0:
                        output_path.write_bytes(raw)
                if selected_path:
                    snack(f"{label}已导出")
            except Exception as ex:
                snack(f"导出失败：{str(ex)[:60]}")

        return handler

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
            save_profile_from_state()
            save_current()

        def save_profile_fields(e=None):
            circumference = {"measured_at": iso_now()}
            if str(waist_field.value or "").strip():
                circumference["waist_cm"] = to_float(waist_field.value)
            if str(arm_field.value or "").strip():
                circumference["arm_cm"] = to_float(arm_field.value)
            state["circumference"] = circumference if len(circumference) > 1 else None
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
            return make_button(label, on_click=lambda e, v=label: setter(v), bgcolor=PRIMARY if selected else PRIMARY_SOFT, color="#FFFFFF" if selected else GREEN, expand=True)

        def set_macro_mode(mode):
            state["macro_mode"] = mode
            save_profile_from_state()
            save_current()
            refresh()
            snack("已切换为自动计算" if mode == "auto" else "已切换为自定义倍数")

        def open_macro_settings_dialog(e=None):
            dialog_width = responsive_width()
            fields = {}
            rows = []
            multipliers = state.setdefault("macro_multipliers", json.loads(json.dumps(DEFAULT_MACRO_MULTIPLIERS)))

            def macro_multiplier_field(label, value):
                field = plain_number_field(value=value, keyboard_type=_KEYBOARD_NUMBER, expand=True)
                label_text = small_text(label)
                try:
                    label_text.no_wrap = True
                except Exception:
                    pass
                box = ft.Column([
                    ft.Container(content=label_text, height=28),
                    field,
                ], spacing=3)
                box.expand = True
                return box, field

            for day_type in ["高碳日", "中碳日", "低碳日"]:
                current = multipliers.setdefault(day_type, dict(DEFAULT_MACRO_MULTIPLIERS[day_type]))
                carb_box, carb_field = macro_multiplier_field("碳水×体重", f"{to_float(current.get('carb'), DEFAULT_MACRO_MULTIPLIERS[day_type]['carb']):g}")
                protein_box, protein_field = macro_multiplier_field("蛋白×去脂", f"{to_float(current.get('protein'), DEFAULT_MACRO_MULTIPLIERS[day_type]['protein']):g}")
                fat_box, fat_field = macro_multiplier_field("脂肪×体重", f"{to_float(current.get('fat'), DEFAULT_MACRO_MULTIPLIERS[day_type]['fat']):g}")
                fields[day_type] = {"carb": carb_field, "protein": protein_field, "fat": fat_field}
                rows.extend([
                    ft.Text(day_type, size=14, weight="bold", color=PRIMARY),
                    ft.Row([carb_box, protein_box, fat_box], spacing=6),
                ])

            dlg = None

            def confirm(event=None):
                updated = {}
                for day_type, macro_fields in fields.items():
                    values = {macro: to_float(field.value, 0) for macro, field in macro_fields.items()}
                    if any(value <= 0 or value > 10 for value in values.values()):
                        snack("倍数需大于 0 且不超过 10")
                        return
                    updated[day_type] = values
                state["macro_multipliers"] = updated
                state["macro_mode"] = "custom"
                save_profile_from_state()
                save_current()
                close_control(dlg)
                refresh()
                snack("自定义倍数已保存")

            content = ft.Column([
                small_text("自定义值为目标区间中心；碳水、脂肪按体重计算，蛋白质按去脂体重计算。"),
                *rows,
            ], width=dialog_width, height=430, spacing=9, scroll=_SCROLL_AUTO)
            dlg = dialog_base(
                "自定义高中低碳倍数",
                content,
                [ft.Container(content=make_button("保存并启用", on_click=confirm, expand=True), width=dialog_width)],
                on_close=lambda event: close_control(dlg),
            )
            open_control(dlg)

        multiplier_rows = []
        for day_type in ["高碳日", "中碳日", "低碳日"]:
            values = state.get("macro_multipliers", {}).get(day_type, DEFAULT_MACRO_MULTIPLIERS[day_type])
            multiplier_rows.append(ft.Row([
                small_text(day_type),
                ft.Text(
                    f"碳 {to_float(values.get('carb')):g}｜蛋 {to_float(values.get('protein')):g}｜脂 {to_float(values.get('fat')):g}",
                    size=12,
                    weight="bold",
                    color=TEXT,
                ),
            ], alignment="spaceBetween"))

        auto_selected = state.get("macro_mode", "auto") == "auto"
        custom_selected = not auto_selected
        macro_box = ft.Container(
            content=ft.Column([
                ft.Row([section_title("宏量目标计算"), make_button("编辑倍数", on_click=open_macro_settings_dialog, bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
                ft.Row([
                    make_button("自动计算", on_click=lambda e: set_macro_mode("auto"), bgcolor=PRIMARY if auto_selected else PRIMARY_SOFT, color="#FFFFFF" if auto_selected else GREEN, expand=True),
                    make_button("自定义", on_click=lambda e: set_macro_mode("custom"), bgcolor=PRIMARY if custom_selected else PRIMARY_SOFT, color="#FFFFFF" if custom_selected else GREEN, expand=True),
                ], spacing=8),
                *multiplier_rows,
                small_text("自动模式会结合体重、体脂、年龄修正；自定义模式使用上面的个人倍数。"),
            ], spacing=7),
            bgcolor="#F8FAFC",
            border_radius=8,
            padding=12,
        )

        export_box = ft.Container(
            content=ft.Column([
                ft.Row([section_title("备份与导出"), small_text("JSON 格式")], alignment="spaceBetween"),
                make_button("导出完整备份", on_click=export_handler("all"), icon=ft.Icons.DOWNLOAD, expand=True),
                make_button("导入备份", on_click=import_backup_handler, icon=ft.Icons.UPLOAD_FILE, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                ft.Row([
                    make_button("历史记录", on_click=export_handler("records"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                    make_button("个人资料", on_click=export_handler("profile"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                ], spacing=8),
                ft.Row([
                    make_button("食物库", on_click=export_handler("foods"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                    make_button("补剂库", on_click=export_handler("supplements"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                ], spacing=8),
                small_text("可导入完整或分类 JSON；导入前会确认合并或覆盖，并自动保留安全快照。"),
            ], spacing=8),
            bgcolor="#F8FAFC",
            border_radius=8,
            padding=12,
        )

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
            ft.Row([section_title("我"), make_button("保存", on_click=save_profile_fields, bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
            ft.Row([weight_box, bodyfat_box], spacing=8, vertical_alignment="start"),
            ft.Row([height_box, age_box], spacing=8, vertical_alignment="start"),
            ft.Row([waist_box, arm_box], spacing=8, vertical_alignment="start"),
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
            macro_box,
            export_box,
            ft.Container(content=small_text("腰围、臂围只做记录，不参与碳循环公式。今日页仍保留体重、体脂，方便每日更新。"), bgcolor="#FAFAFA", border_radius=8, padding=10),
        ], spacing=10))

    def render_data_page():
        data_state = state.setdefault("data_page", {})

        def update_data_page(**changes):
            data_state.update(changes)
            refresh()

        def open_record_surface(kind):
            if kind in {"weight", "bodyfat", "recovery"}:
                set_view("daily_details")
                return
            if kind == "circumference":
                set_view("me")
                return
            if kind == "diet":
                set_view("diet")
                return
            set_view("training")

        def save_calendar_event(selected_date, event):
            current = records.get(selected_date, {})
            current = dict(current) if isinstance(current, dict) else {}
            if event is None:
                current.pop("calendar_event", None)
                if current:
                    records[selected_date] = current
                else:
                    records.pop(selected_date, None)
            else:
                current["calendar_event"] = event
                records[selected_date] = current
            save_json(RECORD_FILE, records)
            data_state["selected_date"] = selected_date
            refresh()

        def edit_calendar_event(selected_date, action):
            if action == "rest":
                save_calendar_event(selected_date, {"type": "rest", "text": "休息"})
                return
            if action == "clear":
                save_calendar_event(selected_date, None)
                return
            current = records.get(selected_date, {})
            current_event = current.get("calendar_event", {}) if isinstance(current, dict) else {}
            note = mobile_text_field("事项内容", str(current_event.get("text", "")) if isinstance(current_event, dict) else "", width=responsive_width())
            dlg = None

            def confirm_custom(e=None):
                text = str(note.value or "").strip()
                if not text:
                    snack("请输入事项内容")
                    return
                close_control(dlg)
                save_calendar_event(selected_date, {"type": "custom", "text": text})

            dlg = dialog_base(
                "自定义事项",
                ft.Column([small_text(selected_date), note], width=responsive_width(), spacing=8),
                [make_button("保存事项", on_click=confirm_custom, expand=True)],
                on_close=lambda e: close_control(dlg),
            )
            open_control(dlg)

        config = DataPageConfig(
            period_days=int(data_state.get("period_days", 7)),
            active_tab=str(data_state.get("active_tab", "趋势")),
            chart_kind=str(data_state.get("chart_kind", "weight")),
            body_part_filter=str(data_state.get("body_part_filter", "全部")),
            selected_date=data_state.get("selected_date") or state.get("date"),
            action_trend_open=bool(data_state.get("action_trend_open", False)),
            selected_exercise=data_state.get("selected_exercise"),
            raw_expanded=bool(data_state.get("raw_expanded", False)),
        )
        records_local = load_json(RECORD_FILE, {})
        return build_data_page_view(
            records_local if isinstance(records_local, dict) else {},
            end_date=state.get("date", date.today().isoformat()),
            config=config,
            on_period_change=lambda days: update_data_page(period_days=days),
            on_tab_change=lambda tab: update_data_page(active_tab=tab, action_trend_open=False),
            on_chart_change=lambda kind: update_data_page(chart_kind=kind, action_trend_open=False),
            on_add_record=open_record_surface,
            on_action_trend_open=lambda e: update_data_page(action_trend_open=True),
            on_action_trend_close=lambda e: update_data_page(action_trend_open=False),
            on_selected_exercise_change=lambda name: update_data_page(selected_exercise=name),
            on_body_part_filter_change=lambda part: update_data_page(body_part_filter=part),
            on_selected_date_change=lambda selected: update_data_page(selected_date=selected),
            on_calendar_event_change=edit_calendar_event,
            on_toggle_raw=lambda e: update_data_page(raw_expanded=not bool(data_state.get("raw_expanded", False))),
        )

    def render_history():
        records_local = load_json(RECORD_FILE, {})
        records_local = records_local if isinstance(records_local, dict) else {}
        keys = sorted(records_local.keys(), reverse=True)
        controls = []

        today = date.today()
        start_day = today - datetime.timedelta(days=6)
        recent_keys = []
        for key in keys:
            try:
                record_day = date.fromisoformat(key)
            except (TypeError, ValueError):
                continue
            if start_day <= record_day <= today:
                recent_keys.append(key)

        weights = []
        bodyfats = []
        compliance_days = 0
        food_days = 0
        exceeded = Counter()
        daily_summaries = []
        for key in sorted(recent_keys):
            rec = records_local.get(key, {})
            if not isinstance(rec, dict):
                continue
            profile = rec.get("profile", {})
            total = rec.get("daily_total", {})
            if not isinstance(profile, dict):
                profile = {}
            if not isinstance(total, dict):
                total = {}
            targets = profile.get("targets", {})
            if not isinstance(targets, dict):
                targets = {}
            measurement = normalize_body_measurement(rec, key)
            weight = measurement.get("weight_kg") if measurement["is_measured"] else None
            bodyfat = measurement.get("bodyfat_percent") if measurement["is_measured"] else None
            if weight is not None:
                weights.append((key, weight))
            if bodyfat is not None:
                bodyfats.append((key, bodyfat))

            meals = rec.get("meals", {})
            has_food = isinstance(meals, dict) and any(
                isinstance(items, list) and any(isinstance(item, dict) for item in items)
                for items in meals.values()
            )
            required_targets = ["carb_min", "carb_max", "protein_min", "protein_max", "fat_min", "fat_max", "calorie_target"]
            has_complete_targets = all(to_float(targets.get(name), 0) > 0 for name in required_targets)
            evaluable_food_day = has_food and has_complete_targets
            training_summary = summarize_daily_training(rec, key)
            training_label = training_summary["body_part_label"] if training_summary["has_training"] else "休息/未记"
            compliance = profile.get("compliance", {})
            compliance_status = compliance.get("status", "未记录") if isinstance(compliance, dict) and evaluable_food_day else "未评估"
            daily_summaries.append({
                "date": key[5:],
                "day_type": str(profile.get("day_type", "未设置")),
                "training": training_label,
                "status": compliance_status,
            })
            if not evaluable_food_day:
                continue
            food_days += 1
            macro_in_range = (
                to_float(targets.get("carb_min")) <= to_float(total.get("carb")) <= to_float(targets.get("carb_max"))
                and to_float(targets.get("protein_min")) <= to_float(total.get("protein")) <= to_float(targets.get("protein_max"))
                and to_float(targets.get("fat_min")) <= to_float(total.get("fat")) <= to_float(targets.get("fat_max"))
            )
            if macro_in_range:
                compliance_days += 1
            if to_float(total.get("carb")) > to_float(targets.get("carb_max"), float("inf")):
                exceeded["碳水"] += 1
            if to_float(total.get("protein")) > to_float(targets.get("protein_max"), float("inf")):
                exceeded["蛋白"] += 1
            if to_float(total.get("fat")) > to_float(targets.get("fat_max"), float("inf")):
                exceeded["脂肪"] += 1
            kcal_target = to_float(targets.get("calorie_target"), 0)
            if kcal_target and to_float(total.get("kcal")) > kcal_target + 150:
                exceeded["热量"] += 1

        def trend_text(values, suffix):
            if not values:
                return "暂无数据"
            latest = values[-1][1]
            if len(values) < 3:
                return f"最新 {latest:g}{suffix} · 样本不足"
            average = round(sum(value for _, value in values) / len(values), 1)
            return f"均 {average:g}{suffix} · 最新 {latest:g}{suffix}"

        if recent_keys:
            frequent = [
                f"{name} {count}/{food_days}天"
                for name, count in exceeded.most_common(2)
                if count >= 2 and food_days and count / food_days >= 0.4
            ]
            frequent_text = "、".join(frequent) if frequent else "无经常超标项"
            sample_is_small = food_days < 3
            compliance_text = f"{compliance_days} / {food_days} 天" if food_days else "暂无饮食"
            trend_grid = ft.Column([
                ft.Row([
                    ft.Column([small_text("体重"), ft.Text(trend_text(weights, " kg"), size=13, weight="bold", color=TEXT)], spacing=2, expand=True),
                    ft.Column([small_text("体脂"), ft.Text(trend_text(bodyfats, "%"), size=13, weight="bold", color=TEXT)], spacing=2, expand=True),
                ], spacing=8),
                ft.Row([
                    ft.Column([small_text("达标天数"), ft.Text(compliance_text, size=13, weight="bold", color=GREEN if compliance_days else ORANGE)], spacing=2, expand=True),
                    ft.Column([small_text("经常超标"), ft.Text("样本不足" if sample_is_small else frequent_text, size=12, weight="bold", color=SUB if sample_is_small else RED if frequent else GREEN)], spacing=2, expand=True),
                ], spacing=8),
            ], spacing=8)

            expanded = bool(state.get("history_trend_expanded", False))

            def toggle_history_trend(e=None):
                state["history_trend_expanded"] = not bool(state.get("history_trend_expanded", False))
                refresh()

            detail_rows = []
            if expanded:
                detail_rows.append(ft.Row([
                    small_text("日期"), small_text("碳日"), small_text("训练"), small_text("饮食"),
                ], alignment="spaceBetween"))
                for item in reversed(daily_summaries):
                    detail_rows.append(ft.Row([
                        ft.Text(item["date"], size=12, color=SUB, width=42),
                        ft.Text(item["day_type"].replace("日", ""), size=12, color=TEXT, width=34),
                        ft.Text(item["training"], size=12, color=TEXT, expand=True, max_lines=1, overflow="ellipsis"),
                        ft.Text(item["status"], size=12, color=GREEN if item["status"] == "达标" else SUB, width=36, text_align="right"),
                    ], spacing=4))
            summary_content = ft.Column([
                ft.Row([
                    section_title("最近 7 天趋势"),
                    ft.IconButton(icon=ft.Icons.EXPAND_LESS if expanded else ft.Icons.EXPAND_MORE, icon_size=18, icon_color=SUB, tooltip="收起每日明细" if expanded else "展开每日明细", on_click=toggle_history_trend),
                ], alignment="spaceBetween"),
                small_text(f"饮食记录 {food_days} 天｜漏记 {7 - food_days} 天"),
                trend_grid,
                *detail_rows,
            ], spacing=8)
        else:
            summary_content = ft.Column([
                section_title("最近 7 天趋势"),
                small_text("最近 7 天暂无记录，保存今日数据后开始统计"),
            ], spacing=6)

        if not keys:
            controls.append(card(small_text("暂无历史记录")))
        for d in keys:
            rec = records_local[d]
            if not isinstance(rec, dict):
                continue
            p = rec.get("profile", {})
            total = rec.get("daily_total", {})
            if not isinstance(p, dict):
                p = {}
            if not isinstance(total, dict):
                total = {}
            comp = p.get("compliance", {})
            if not isinstance(comp, dict):
                comp = {}
            measurement = normalize_body_measurement(rec, d)
            body_line_parts = []
            if measurement["is_measured"]:
                if measurement.get("weight_kg") is not None:
                    body_line_parts.append(f"体重 {measurement['weight_kg']:g} kg")
                if measurement.get("bodyfat_percent") is not None:
                    body_line_parts.append(f"体脂 {measurement['bodyfat_percent']:g}%")
            body_line = "｜".join(body_line_parts) if body_line_parts else "身体未实测"
            controls.append(card(ft.Row([
                ft.Column([
                    ft.Text(f"{d}｜{p.get('day_type','')}", size=14, weight="bold"),
                    small_text(f"{comp.get('status','')}｜{total.get('kcal',0)} kcal｜碳 {total.get('carb',0)} 蛋白 {total.get('protein',0)} 脂肪 {total.get('fat',0)}"),
                    small_text(body_line)
                ], expand=True, spacing=2),
                ft.Row([
                    ft.IconButton(icon=ft.Icons.DESCRIPTION_OUTLINED, icon_color=PRIMARY, on_click=lambda e, x=d: open_record_detail(x)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, on_click=lambda e, x=d: delete_history_record(x)),
                ], spacing=0),
            ]), padding=10, margin_bottom=6))
        return ft.Column([
            card(ft.Row([section_title("历史记录"), make_button("刷新", on_click=lambda e: refresh(), bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween")),
            card(summary_content),
            ft.Column(controls, spacing=0)
        ])

    def render_nav():
        current_session = session_data()
        if state.get("current_view") == "training" and current_session and current_session.get("status") == "active":
            return ft.Container(height=0)
        items = [
            ("today", "今日", ft.Icons.TODAY),
            ("training", "训练", ft.Icons.FITNESS_CENTER),
            ("diet", "饮食", ft.Icons.RESTAURANT_MENU),
            ("data", "数据", ft.Icons.INSERT_CHART_OUTLINED),
            ("me", "我", ft.Icons.PERSON_OUTLINE),
        ]

        tabs = []
        for key, label, icon in items:
            selected_view = state["current_view"]
            selected = selected_view == key or (key == "today" and selected_view == "daily_details") or (key == "diet" and selected_view in {"foods", "supplements"})
            tabs.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(icon, size=22, color=PRIMARY if selected else SUB),
                        ft.Text(label, size=12, color=PRIMARY if selected else SUB, weight="bold" if selected else "normal"),
                    ], horizontal_alignment="center", spacing=2),
                    on_click=lambda e, k=key: set_view(k),
                    expand=True,
                    padding=6,
                    bgcolor="#F7FFFFFF",
                )
            )

        return ft.Container(
            content=ft.Row(tabs, spacing=0, alignment="spaceAround"),
            padding=6,
            bgcolor="#F7FFFFFF",
            border=ft.Border(top=ft.BorderSide(width=1, color=BORDER)),
        )

    main_column = ft.Column(spacing=0, scroll=_SCROLL_AUTO, expand=True)
    nav_holder = ft.Container(bgcolor="#F7FFFFFF")

    def refresh_soft():
        # Used for text field change where a full rebuild while typing is disruptive.
        save_current()
        targets = get_targets()
        page.update()

    def refresh():
        main_column.controls.clear()
        view = state["current_view"]
        current_session = session_data()
        active_training = bool(
            view == "training"
            and current_session
            and current_session.get("status") == "active"
        )
        shell_bg = "#101513" if active_training else BG
        page.bgcolor = shell_bg
        body_container.bgcolor = shell_bg
        if view == "today":
            main_column.controls.extend([render_today_dashboard(), render_top(), ft.Container(height=8)])
        elif view == "daily_details":
            main_column.controls.extend([render_recovery_page(), ft.Container(height=8)])
        elif view == "training":
            main_column.controls.append(render_training_workspace())
        elif view in {"diet", "foods", "supplements"}:
            main_column.controls.extend([render_diet_page(), ft.Container(height=12)])
        elif view == "data":
            main_column.controls.extend([render_data_page(), ft.Container(height=12)])
        elif view == "me":
            main_column.controls.extend([render_badge_wall(), render_me(), ft.Container(height=12)])
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

    async def training_clock_loop():
        while True:
            await asyncio.sleep(1)
            session = session_data()
            if not session or session.get("status") != "active":
                continue
            elapsed_control = training_clock_refs.get("elapsed")
            if elapsed_control is not None:
                elapsed_control.value = clock_text(elapsed_seconds(session))
                try:
                    elapsed_control.update()
                except Exception:
                    pass
            rest_cycle = session.get("rest_cycle") if isinstance(session.get("rest_cycle"), dict) else None
            rest_seconds = rest_remaining_seconds(rest_cycle, datetime.datetime.now()) if rest_cycle else 0
            rest_control = training_clock_refs.get("rest")
            if rest_control is not None:
                rest_control.value = str(rest_seconds)
                try:
                    rest_control.update()
                except Exception:
                    pass
            if isinstance(rest_cycle, dict) and rest_cycle.get("status") == "running" and rest_seconds <= 0:
                complete_rest_if_elapsed(session)
                try:
                    refresh()
                except Exception:
                    pass

    try:
        page.run_task(training_clock_loop)
    except Exception:
        pass

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

        dialog_width = responsive_width()
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
                return make_button(label, on_click=lambda e, l=label, g=group: choose(g, l), bgcolor=PRIMARY if current else PRIMARY_SOFT, color="#FFFFFF" if current else GREEN, expand=True)

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
            save_profile_from_state()
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

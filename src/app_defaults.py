"""Static application defaults and option catalogs."""

from __future__ import annotations

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

CIRCUMFERENCE_FIELDS = (
    ("chest_cm", "胸围"),
    ("waist_cm", "腰围"),
    ("hip_cm", "臀围"),
    ("arm_cm", "上臂围"),
    ("thigh_cm", "大腿围"),
    ("calf_cm", "小腿围"),
)

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

__all__ = [
    "DAY_TYPES", "DEFAULT_MACRO_MULTIPLIERS", "CIRCUMFERENCE_FIELDS", "TRAINING_TARGETS", "ABS_ACTIONS",
    "FATIGUE_OPTIONS", "INTENSITY_OPTIONS", "DEFAULT_FOODS", "DEFAULT_SUPPLEMENTS",
]

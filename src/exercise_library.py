# -*- coding: utf-8 -*-
"""Built-in exercise catalog and search helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from storage_service import TRAINING_FILE, load_json, save_json


_MOVEMENT_GUIDES = {
    "水平推": {
        "cues": ["肩胛骨后收下沉，躯干保持稳定", "控制下放，前臂接近垂直", "推起时呼气，手肘不要锁死"],
        "mistakes": ["臀部离开支撑面", "手肘过度外展", "下放过快或借力反弹"],
    },
    "夹胸": {
        "cues": ["胸部打开，肩胛保持稳定", "手臂保持轻微弯曲", "向中间夹合并缓慢还原"],
        "mistakes": ["用手臂屈伸代替夹胸", "耸肩", "重量过大导致动作幅度不足"],
    },
    "俯撑": {
        "cues": ["头、躯干和腿保持一线", "核心收紧", "胸部主动靠近支撑面"],
        "mistakes": ["塌腰或撅臀", "手肘完全横向打开", "动作幅度过小"],
    },
    "垂直拉": {
        "cues": ["先下沉肩胛，再用肘向下拉", "胸部自然抬起", "全程控制还原"],
        "mistakes": ["身体大幅后仰", "只用手臂拉", "耸肩或拉至颈后"],
    },
    "划船": {
        "cues": ["保持脊柱中立", "肘部向髋部方向拉", "顶端主动收紧背部"],
        "mistakes": ["躯干过度旋转", "耸肩", "还原过快"],
    },
    "髋铰链": {
        "cues": ["臀部向后移动", "脊柱保持中立", "重量贴近身体移动"],
        "mistakes": ["弓背", "膝盖过度前移", "顶端过度后仰"],
    },
    "肩推": {
        "cues": ["核心和臀部收紧", "前臂保持接近垂直", "重量沿稳定轨迹上推"],
        "mistakes": ["腰部过度反弓", "耸肩", "用腿部弹震借力"],
    },
    "平举": {
        "cues": ["肩胛保持稳定", "手肘轻微弯曲", "控制抬起和下放"],
        "mistakes": ["耸肩", "大幅摆动身体", "抬起过高且失去控制"],
    },
    "深蹲": {
        "cues": ["双脚稳定踩地", "膝盖方向与脚尖一致", "保持躯干稳定并控制下蹲"],
        "mistakes": ["膝盖明显内扣", "脚跟离地", "腰背失去中立"],
    },
    "单腿蹲": {
        "cues": ["前脚全脚掌受力", "骨盆保持稳定", "膝盖沿脚尖方向移动"],
        "mistakes": ["身体左右摇晃", "膝盖内扣", "后腿过度发力"],
    },
    "腿部器械": {
        "cues": ["调整座椅和转轴位置", "全程控制速度", "使用可控动作幅度"],
        "mistakes": ["膝关节猛烈锁死", "重量过大导致幅度不足", "快速弹震借力"],
    },
    "臀推": {
        "cues": ["下巴微收，肋骨保持稳定", "顶端主动收紧臀部", "通过髋部伸展完成动作"],
        "mistakes": ["腰部过度后仰", "脚位过远或过近", "顶端没有控制"],
    },
    "提踵": {
        "cues": ["前脚掌稳定支撑", "脚跟充分下降再抬起", "顶端短暂停顿"],
        "mistakes": ["快速弹震", "脚踝向内或向外翻", "动作幅度不足"],
    },
    "弯举": {
        "cues": ["上臂位置保持稳定", "屈肘抬起并控制下放", "手腕保持自然"],
        "mistakes": ["身体前后摆动", "肘部大幅前移", "手腕过度弯曲"],
    },
    "三头伸展": {
        "cues": ["上臂保持稳定", "通过肘关节完成伸展", "末端主动收紧三头肌"],
        "mistakes": ["肩部和躯干借力", "肘部明显外张", "还原过快"],
    },
    "卷腹": {
        "cues": ["肋骨向骨盆靠近", "腰部保持可控", "呼气时收紧腹部"],
        "mistakes": ["用手拉颈部", "髋屈肌过度代偿", "快速摆动身体"],
    },
    "举腿": {
        "cues": ["先稳定骨盆", "控制腿部抬起", "下放时避免腰部过度拱起"],
        "mistakes": ["依靠摆动", "腰部离地失控", "下放过快"],
    },
    "核心稳定": {
        "cues": ["保持自然呼吸", "收紧核心并稳定骨盆", "只在可控范围内动作"],
        "mistakes": ["憋气", "塌腰", "为延长时间牺牲姿势"],
    },
    "旋转抗旋": {
        "cues": ["骨盆和躯干保持稳定", "动作由躯干控制完成", "左右两侧均衡训练"],
        "mistakes": ["用手臂甩动", "动作速度过快", "腰部过度扭转"],
    },
    "有氧": {
        "cues": ["先用低强度热身", "保持可持续节奏", "结束前逐步降低强度"],
        "mistakes": ["未热身直接冲刺", "姿势失控仍维持速度", "忽视器械安全设置"],
    },
}


# name, equipment, target_muscles, guide, default_weight_kg, default_reps, default_sets
_EXERCISE_SPECS = {
    "胸": [
        ("杠铃卧推", "杠铃", "胸大肌、三角肌前束、肱三头肌", "水平推", 20, 10, 4),
        ("上斜杠铃卧推", "杠铃", "胸大肌锁骨部、三角肌前束、肱三头肌", "水平推", 20, 10, 4),
        ("下斜杠铃卧推", "杠铃", "胸大肌胸肋部、肱三头肌", "水平推", 20, 10, 4),
        ("哑铃卧推", "哑铃", "胸大肌、三角肌前束、肱三头肌", "水平推", 8, 10, 4),
        ("上斜哑铃卧推", "哑铃", "胸大肌锁骨部、三角肌前束", "水平推", 8, 10, 4),
        ("哑铃飞鸟", "哑铃", "胸大肌", "夹胸", 5, 12, 3),
        ("器械推胸", "器械", "胸大肌、肱三头肌", "水平推", 20, 12, 4),
        ("上斜器械推胸", "器械", "胸大肌锁骨部、三角肌前束", "水平推", 20, 12, 4),
        ("史密斯机卧推", "器械", "胸大肌、肱三头肌", "水平推", 20, 10, 4),
        ("蝴蝶机夹胸", "器械", "胸大肌", "夹胸", 15, 15, 4),
        ("绳索夹胸", "绳索", "胸大肌", "夹胸", 5, 15, 4),
        ("俯卧撑", "自重", "胸大肌、肱三头肌、核心", "俯撑", None, 15, 4),
        ("双杠臂屈伸（胸部侧重）", "自重", "胸大肌、肱三头肌", "俯撑", None, 10, 4),
    ],
    "背": [
        ("高位下拉", "器械", "背阔肌、大圆肌、肱二头肌", "垂直拉", 25, 12, 4),
        ("反握高位下拉", "器械", "背阔肌、肱二头肌", "垂直拉", 25, 12, 4),
        ("引体向上", "自重", "背阔肌、肱二头肌", "垂直拉", None, 8, 4),
        ("辅助引体向上", "器械", "背阔肌、肱二头肌", "垂直拉", 25, 10, 4),
        ("杠铃俯身划船", "杠铃", "背阔肌、斜方肌、菱形肌", "划船", 20, 10, 4),
        ("T杠划船", "器械", "背阔肌、斜方肌、菱形肌", "划船", 20, 10, 4),
        ("单臂哑铃划船", "哑铃", "背阔肌、菱形肌", "划船", 10, 12, 4),
        ("胸托哑铃划船", "哑铃", "背阔肌、斜方肌中束", "划船", 8, 12, 4),
        ("坐姿绳索划船", "绳索", "背阔肌、菱形肌、斜方肌", "划船", 20, 12, 4),
        ("器械高位划船", "器械", "背阔肌、大圆肌", "划船", 20, 12, 4),
        ("直臂下压", "绳索", "背阔肌、大圆肌", "垂直拉", 10, 15, 3),
        ("杠铃硬拉", "杠铃", "竖脊肌、臀大肌、腘绳肌", "髋铰链", 30, 6, 3),
        ("哑铃上拉", "哑铃", "背阔肌、胸大肌", "垂直拉", 8, 12, 3),
    ],
    "肩": [
        ("站姿杠铃推举", "杠铃", "三角肌前束、三角肌中束、肱三头肌", "肩推", 15, 8, 4),
        ("坐姿哑铃推举", "哑铃", "三角肌前束、三角肌中束、肱三头肌", "肩推", 6, 10, 4),
        ("阿诺德推举", "哑铃", "三角肌前束、三角肌中束", "肩推", 5, 10, 3),
        ("器械肩推", "器械", "三角肌前束、三角肌中束、肱三头肌", "肩推", 15, 12, 4),
        ("史密斯机肩推", "器械", "三角肌前束、肱三头肌", "肩推", 15, 10, 4),
        ("哑铃侧平举", "哑铃", "三角肌中束", "平举", 4, 15, 4),
        ("单臂绳索侧平举", "绳索", "三角肌中束", "平举", 3, 15, 4),
        ("器械侧平举", "器械", "三角肌中束", "平举", 10, 15, 4),
        ("反向蝴蝶机飞鸟", "器械", "三角肌后束、菱形肌", "平举", 10, 15, 4),
        ("俯身哑铃反向飞鸟", "哑铃", "三角肌后束、斜方肌中束", "平举", 3, 15, 4),
        ("绳索面拉", "绳索", "三角肌后束、肩袖肌群、斜方肌", "划船", 10, 15, 4),
        ("绳索直立划船", "绳索", "三角肌中束、斜方肌", "划船", 10, 12, 3),
        ("哑铃耸肩", "哑铃", "斜方肌上束", "划船", 12, 12, 4),
    ],
    "腿": [
        ("杠铃深蹲", "杠铃", "股四头肌、臀大肌、内收肌", "深蹲", 20, 8, 4),
        ("杠铃前蹲", "杠铃", "股四头肌、臀大肌、核心", "深蹲", 20, 8, 4),
        ("哈克深蹲", "器械", "股四头肌、臀大肌", "深蹲", 20, 10, 4),
        ("腿举", "器械", "股四头肌、臀大肌", "腿部器械", 40, 12, 4),
        ("保加利亚分腿蹲", "哑铃", "股四头肌、臀大肌", "单腿蹲", 5, 10, 4),
        ("哑铃反向箭步蹲", "哑铃", "臀大肌、股四头肌", "单腿蹲", 5, 10, 3),
        ("哑铃登台阶", "哑铃", "臀大肌、股四头肌", "单腿蹲", 5, 10, 3),
        ("罗马尼亚硬拉", "杠铃", "腘绳肌、臀大肌、竖脊肌", "髋铰链", 20, 10, 4),
        ("相扑硬拉", "杠铃", "臀大肌、内收肌、股四头肌", "髋铰链", 30, 6, 3),
        ("杠铃臀推", "杠铃", "臀大肌、腘绳肌", "臀推", 20, 10, 4),
        ("腿屈伸", "器械", "股四头肌", "腿部器械", 15, 15, 4),
        ("坐姿腿弯举", "器械", "腘绳肌", "腿部器械", 15, 12, 4),
        ("俯卧腿弯举", "器械", "腘绳肌", "腿部器械", 15, 12, 4),
        ("站姿提踵", "器械", "腓肠肌、比目鱼肌", "提踵", 20, 15, 4),
        ("坐姿提踵", "器械", "比目鱼肌、腓肠肌", "提踵", 15, 15, 4),
    ],
    "二头": [
        ("杠铃弯举", "杠铃", "肱二头肌、肱肌", "弯举", 10, 10, 4),
        ("EZ杠弯举", "杠铃", "肱二头肌、肱肌", "弯举", 10, 10, 4),
        ("交替哑铃弯举", "哑铃", "肱二头肌", "弯举", 5, 12, 4),
        ("上斜哑铃弯举", "哑铃", "肱二头肌长头", "弯举", 4, 12, 3),
        ("锤式弯举", "哑铃", "肱肌、肱桡肌、肱二头肌", "弯举", 5, 12, 4),
        ("牧师凳弯举", "杠铃", "肱二头肌短头、肱肌", "弯举", 8, 12, 4),
        ("器械牧师凳弯举", "器械", "肱二头肌、肱肌", "弯举", 10, 12, 4),
        ("双臂绳索弯举", "绳索", "肱二头肌", "弯举", 10, 12, 4),
        ("单臂绳索弯举", "绳索", "肱二头肌", "弯举", 5, 12, 3),
        ("集中弯举", "哑铃", "肱二头肌", "弯举", 4, 12, 3),
        ("蜘蛛弯举", "哑铃", "肱二头肌短头", "弯举", 4, 12, 3),
        ("反握杠铃弯举", "杠铃", "肱桡肌、肱肌", "弯举", 8, 12, 3),
        ("佐特曼弯举", "哑铃", "肱二头肌、肱桡肌", "弯举", 4, 10, 3),
    ],
    "三头": [
        ("直杆绳索下压", "绳索", "肱三头肌", "三头伸展", 10, 12, 4),
        ("绳索下压", "绳索", "肱三头肌", "三头伸展", 10, 12, 4),
        ("绳索过顶臂屈伸", "绳索", "肱三头肌长头", "三头伸展", 8, 12, 4),
        ("单臂绳索下压", "绳索", "肱三头肌", "三头伸展", 5, 12, 3),
        ("仰卧杠铃臂屈伸", "杠铃", "肱三头肌长头", "三头伸展", 8, 10, 4),
        ("坐姿哑铃过顶臂屈伸", "哑铃", "肱三头肌长头", "三头伸展", 8, 12, 4),
        ("窄握杠铃卧推", "杠铃", "肱三头肌、胸大肌", "水平推", 20, 8, 4),
        ("双杠臂屈伸（三头侧重）", "自重", "肱三头肌、胸大肌", "俯撑", None, 10, 4),
        ("凳上臂屈伸", "自重", "肱三头肌", "俯撑", None, 12, 3),
        ("器械双杠臂屈伸", "器械", "肱三头肌、胸大肌", "俯撑", 20, 12, 4),
        ("哑铃俯身臂屈伸", "哑铃", "肱三头肌", "三头伸展", 3, 15, 3),
        ("交叉绳索臂屈伸", "绳索", "肱三头肌", "三头伸展", 5, 12, 3),
        ("JM推举", "杠铃", "肱三头肌", "三头伸展", 15, 10, 3),
    ],
    "腹": [
        ("卷腹", "自重", "腹直肌", "卷腹", None, 15, 4),
        ("绳索卷腹", "绳索", "腹直肌", "卷腹", 10, 15, 4),
        ("反向卷腹", "自重", "腹直肌、腹斜肌", "卷腹", None, 15, 4),
        ("悬垂屈膝举腿", "自重", "腹直肌、髋屈肌", "举腿", None, 12, 4),
        ("悬垂直腿举腿", "自重", "腹直肌、髋屈肌", "举腿", None, 10, 4),
        ("仰卧举腿", "自重", "腹直肌、髋屈肌", "举腿", None, 15, 4),
        ("健腹轮", "器械", "腹直肌、腹横肌、背阔肌", "核心稳定", None, 10, 4),
        ("平板支撑", "自重", "腹横肌、腹直肌、臀肌", "核心稳定", None, 45, 3),
        ("侧平板支撑", "自重", "腹斜肌、臀中肌", "核心稳定", None, 30, 3),
        ("死虫式", "自重", "腹横肌、腹直肌", "核心稳定", None, 12, 3),
        ("鸟狗式", "自重", "核心、臀肌、竖脊肌", "核心稳定", None, 12, 3),
        ("帕洛夫抗旋转", "绳索", "腹斜肌、腹横肌", "旋转抗旋", 5, 12, 3),
        ("俄罗斯转体", "自重", "腹斜肌、腹直肌", "旋转抗旋", None, 20, 3),
    ],
    "有氧": [
        ("跑步机快走", "器械", "心肺系统、下肢肌群", "有氧", None, None, 1),
        ("跑步机慢跑", "器械", "心肺系统、下肢肌群", "有氧", None, None, 1),
        ("跑步机爬坡", "器械", "心肺系统、臀肌、小腿", "有氧", None, None, 1),
        ("动感单车", "器械", "心肺系统、股四头肌、臀肌", "有氧", None, None, 1),
        ("椭圆机", "器械", "心肺系统、上下肢肌群", "有氧", None, None, 1),
        ("划船机", "器械", "心肺系统、背部、下肢", "有氧", None, None, 1),
        ("登阶机", "器械", "心肺系统、臀肌、股四头肌", "有氧", None, None, 1),
        ("户外跑步", "自重", "心肺系统、下肢肌群", "有氧", None, None, 1),
        ("户外骑行", "其他", "心肺系统、股四头肌、臀肌", "有氧", None, None, 1),
        ("游泳", "其他", "心肺系统、全身肌群", "有氧", None, None, 1),
        ("跳绳", "其他", "心肺系统、小腿、协调能力", "有氧", None, None, 1),
        ("战绳", "器械", "心肺系统、肩臂、核心", "有氧", None, None, 6),
        ("波比跳", "自重", "心肺系统、全身肌群", "有氧", None, 10, 5),
    ],
}


EXERCISE_CATEGORIES = tuple(_EXERCISE_SPECS)

_TIMED_EXERCISES = {"平板支撑", "侧平板支撑", "战绳"}
_CARDIO_EXERCISES = {
    "跑步机快走", "跑步机慢跑", "跑步机爬坡", "动感单车", "椭圆机", "划船机",
    "登阶机", "户外跑步", "户外骑行", "游泳", "跳绳",
}
_DISTANCE_EXERCISES = {
    "跑步机快走", "跑步机慢跑", "跑步机爬坡", "动感单车", "椭圆机", "划船机",
    "户外跑步", "户外骑行", "游泳",
}

_CARDIO_METRIC_FIELDS = {
    "跑步机快走": ["speed_kph", "incline_percent"],
    "跑步机慢跑": ["speed_kph", "incline_percent"],
    "跑步机爬坡": ["speed_kph", "incline_percent"],
    "动感单车": ["resistance_level", "cadence_rpm"],
    "椭圆机": ["resistance_level", "strides_per_minute"],
    "划船机": ["resistance_level", "stroke_rate_spm"],
    "登阶机": ["resistance_level", "steps_per_minute"],
}

_EXERCISE_ALIASES = {"登阶机": ["爬楼机", "楼梯机"]}
_TIMED_DEFAULT_SECONDS = {"平板支撑": 45, "侧平板支撑": 30, "战绳": 30}


def _recording_mode(name: str) -> str:
    if name in _CARDIO_EXERCISES:
        return "cardio"
    if name in _TIMED_EXERCISES:
        return "timed"
    return "strength"

_LEGACY_EXERCISE_LIBRARY: list[dict[str, Any]] = [
    {
        "name": name,
        "category": category,
        "equipment": equipment,
        "target_muscles": target_muscles.split("、"),
        "cues": list(_MOVEMENT_GUIDES[guide]["cues"]),
        "mistakes": list(_MOVEMENT_GUIDES[guide]["mistakes"]),
        "default_weight_kg": default_weight_kg,
        "default_reps": default_reps,
        "default_sets": default_sets,
        "recording_mode": _recording_mode(name),
        "distance_enabled": name in _DISTANCE_EXERCISES,
        "cardio_metric_fields": list(_CARDIO_METRIC_FIELDS.get(name, [])),
        "aliases": list(_EXERCISE_ALIASES.get(name, [])),
        "default_duration_seconds": _TIMED_DEFAULT_SECONDS.get(name, 1200 if name in _CARDIO_EXERCISES else None),
    }
    for category, specs in _EXERCISE_SPECS.items()
    for name, equipment, target_muscles, guide, default_weight_kg, default_reps, default_sets in specs
]


# The upstream workbook is intentionally precise, but literal translations
# such as “杠杆式”“雪橇机”“托臂弯举” are not how people search in a Chinese
# gym.  Keep these rules beside the loader so every catalog rebuild receives
# the same user-facing terminology without changing stable source/media IDs.
_COMMON_NAME_REPLACEMENTS = (
    ("侧to侧", "左右"),
    ("仰卧仰卧", "仰卧"),
    ("小腿小腿", "小腿"),
    ("托臂弯举", "牧师凳弯举"),
    ("二头肌弯举", "弯举"),
    ("后三角肌", "后束"),
    ("三头肌伸展", "三头伸展"),
    ("小腿推举", "提踵"),
    ("腿部提踵", "提踵"),
    ("侧向下拉", "高位下拉"),
    ("向前举起", "前平举"),
    ("前肩部举起", "前平举"),
    ("后侧平举", "后束飞鸟"),
    ("杠铃高深蹲", "杠铃高杠深蹲"),
    ("杠铃低深蹲", "杠铃低杠深蹲"),
    ("史密斯低深蹲", "史密斯低杠深蹲"),
)

_SLED_DISPLAY_NAMES = {
    "雪橇45度单腿推举": "45度单腿倒蹬",
    "雪橇45度小腿推举": "45度倒蹬机提踵",
    "雪橇45度腿举": "45度倒蹬",
    "雪橇45度宽距腿举": "45度宽距倒蹬",
    "雪橇小腿推举腿举": "倒蹬机提踵",
    "雪橇单腿小腿推举腿举": "倒蹬机单腿提踵",
    "雪橇窄距哈克深蹲": "哈克机窄距深蹲",
    "雪橇哈克深蹲": "哈克机深蹲",
    "雪橇向前角度提踵": "哈克机站姿提踵",
    "雪橇仰卧小腿推举": "仰卧倒蹬机提踵",
    "雪橇仰卧深蹲": "仰卧倒蹬",
}

_COMMON_SEARCH_FAMILIES = (
    (("胸", "三头"), ("卧推", "胸推", "凳推举"), ("卧推", "推胸")),
    (("胸",), ("推举",), ("推胸", "卧推")),
    (("胸",), ("飞鸟", "夹胸", "胸部挤压"), ("飞鸟", "夹胸")),
    (("胸", "三头"), ("俯卧撑",), ("俯卧撑",)),
    (("胸", "三头"), ("臂屈伸",), ("双杠臂屈伸", "双杠撑体")),
    (("背",), ("高位下拉", "侧向下拉", "绳索下拉", "前下拉", "下拉"), ("高位下拉", "拉背")),
    (("背", "二头"), ("引体向上", "引体"), ("引体向上",)),
    (("背",), ("划船",), ("划船", "拉背")),
    (("背",), ("直臂下压", "直臂下拉", "仰卧上拉", "鹦鹉螺"), ("直臂下压", "直臂下拉", "器械上拉")),
    (("背",), ("耸肩",), ("耸肩",)),
    (("背",), ("挺身", "后伸展"), ("山羊挺身", "背伸展")),
    (("腿",), ("深蹲",), ("深蹲",)),
    (("腿", "臀部"), ("硬拉",), ("硬拉",)),
    (("腿",), ("箭步蹲", "分腿深蹲"), ("箭步蹲", "分腿蹲")),
    (("腿",), ("倒蹬", "腿举", "腿推"), ("倒蹬", "腿举", "腿推")),
    (("腿",), ("腿屈伸", "腿伸展"), ("坐姿腿屈伸", "腿屈伸")),
    (("腿",), ("腿弯举", "腿屈曲"), ("腿弯举", "腿屈曲")),
    (("腿",), ("提踵", "小腿推举"), ("提踵", "练小腿")),
    (("腿",), ("髋外展",), ("髋外展", "大腿外展")),
    (("腿",), ("髋内收",), ("髋内收", "大腿内收", "夹腿")),
    (("腿",), ("踏台上步", "踏步"), ("登台阶", "踏台上步")),
    (("臀部",), ("臀桥", "髋部举起"), ("臀桥", "臀推")),
    (("臀部",), ("髋部伸展", "拉穿"), ("髋伸展", "绳索拉穿")),
    (("肩",), ("肩推", "过头推举", "军式推举", "推举"), ("推肩", "肩推", "肩上推举")),
    (("肩",), ("侧平举",), ("侧平举",)),
    (("肩",), ("前平举", "向前举起"), ("前平举",)),
    (("肩",), ("反向飞鸟", "后束飞鸟", "后侧平举"), ("反向飞鸟", "后束飞鸟")),
    (("肩",), ("直立划船",), ("直立划船", "提拉")),
    (("二头",), ("弯举",), ("弯举", "练二头")),
    (("二头",), ("牧师凳",), ("牧师凳弯举", "斜板弯举")),
    (("二头",), ("锤式弯举",), ("锤式弯举", "锤弯举")),
    (("三头",), ("下压",), ("三头下压", "绳索下压")),
    (("三头",), ("三头伸展", "伸展"), ("三头伸展", "臂屈伸")),
    (("三头",), ("过头三头伸展", "过头臂屈伸"), ("过顶臂屈伸", "过头臂屈伸")),
    (("三头",), ("仰卧三头伸展", "碎颅"), ("仰卧臂屈伸", "碎颅式")),
    (("三头",), ("后踢",), ("三头后踢", "哑铃臂屈伸")),
    (("小臂",), ("腕弯举",), ("腕弯举", "练小臂")),
    (("腹部",), ("卷腹",), ("卷腹", "练腹")),
    (("腹部",), ("仰卧起坐",), ("仰卧起坐", "练腹")),
    (("腹部",), ("举腿", "腿部髋部举起", "腿举起", "提膝", "髋部举起"), ("举腿", "下腹训练")),
    (("腹部",), ("俄罗斯转体", "转体"), ("俄罗斯转体", "腹部转体")),
    (("腹部",), ("健腹轮", "前滚"), ("健腹轮", "健腹轮前推")),
    (("腹部", "核心稳定"), ("平板支撑", "平板"), ("平板支撑", "核心训练")),
    (("腹部", "核心稳定"), ("侧臀桥", "侧平板"), ("侧平板支撑", "侧桥")),
    (("有氧",), ("波比跳",), ("波比跳", "全身有氧")),
    (("有氧",), ("登山跑",), ("登山跑", "登山者")),
    (("有氧",), ("动感单车",), ("动感单车", "室内单车")),
    (("有氧",), ("台阶机",), ("台阶机", "登阶机", "爬楼机")),
)

_SEARCH_QUALIFIERS = (
    "上斜", "下斜", "平板", "坐姿", "站姿", "俯卧", "仰卧", "单臂", "单腿",
    "双臂", "双腿", "宽握", "宽距", "窄握", "窄距", "反握", "对握", "交替",
)


def _append_unique(values: list[str], value: Any) -> None:
    text = "".join(str(value or "").split())
    if text and text not in values and not re.search(r"[A-Za-z]{3,}", text):
        values.append(text)


def _apply_common_catalog_terminology(item: dict[str, Any]) -> str:
    """Normalize literal equipment/name translations and return the old title."""
    old_name = str(item.get("name") or "").strip()
    name = old_name
    equipment = str(item.get("equipment") or "其他").strip()

    if equipment == "器械" and name.startswith("杠杆式"):
        equipment = "悍马机"
        name = f"悍马机{name.removeprefix('杠杆式')}"
    elif equipment == "雪橇机":
        equipment = "倒蹬机"
        for source_name, common_name in _SLED_DISPLAY_NAMES.items():
            if name.startswith(source_name):
                name = f"{common_name}{name[len(source_name):]}"
                break
        else:
            name = name.replace("雪橇", "倒蹬机", 1)
    elif equipment == "锤式器械":
        equipment = "大锤"

    for literal, common in _COMMON_NAME_REPLACEMENTS:
        name = name.replace(literal, common)
    name = name.replace("第一式", "（变式一）").replace("第二式", "（变式二）")
    if name.endswith("3"):
        name = f"{name[:-1]}（变式三）"

    item["name"] = name
    item["equipment"] = equipment
    return old_name


def _apply_common_search_aliases(item: dict[str, Any], old_name: str = "") -> None:
    """Associate precise variants with the Chinese terms people actually type."""
    aliases: list[str] = []
    for value in item.get("aliases", []):
        _append_unique(aliases, value)
    if old_name and old_name != item.get("name"):
        _append_unique(aliases, old_name)

    name = str(item.get("name") or "")
    category = str(item.get("category") or "其他")
    equipment = str(item.get("equipment") or "其他")

    # Titles retain a useful posture/view suffix when it distinguishes media,
    # while search also accepts the plain action and equipment-free wording.
    plain_name = re.sub(r"（(男士|女士|男性示范|女性示范|后视角|侧视角|变式[一二三])）", "", name)
    if plain_name != name:
        _append_unique(aliases, plain_name)
    equipment_prefixes = (
        "半圆平衡球", "髋内收外展机", "上肢功率车", "史密斯机", "悍马机",
        "倒蹬机", "鹦鹉螺机", "蝴蝶机", "腿屈伸机", "腿弯举机", "地雷管",
        "弹力带", "杠铃", "哑铃", "绳索", "壶铃", "药球", "健身球",
        "泡沫轴", "曲杆杠铃", "EZ杠铃", "EZ曲杆",
    )
    for prefix in equipment_prefixes:
        if plain_name.startswith(prefix) and len(plain_name) > len(prefix) + 1:
            _append_unique(aliases, plain_name.removeprefix(prefix))
            break

    for categories, triggers, common_terms in _COMMON_SEARCH_FAMILIES:
        matched = [trigger for trigger in triggers if trigger in name]
        if category not in categories or not matched:
            continue
        qualifiers = [value for value in _SEARCH_QUALIFIERS if value in name]
        for common in common_terms:
            _append_unique(aliases, common)
            _append_unique(aliases, f"{equipment}{common}")
            for qualifier in qualifiers:
                _append_unique(aliases, f"{qualifier}{common}")
                _append_unique(aliases, f"{equipment}{qualifier}{common}")
            for trigger in matched:
                _append_unique(aliases, name.replace(trigger, common))

    # Common word-order variants that do not belong to only one body part.
    if "肩推" in name:
        _append_unique(aliases, name.replace("肩推", "推肩"))
        _append_unique(aliases, f"{equipment}推肩")
    if "牧师凳弯举" in name:
        _append_unique(aliases, name.replace("牧师凳弯举", "托臂弯举"))
    if "倒蹬" in name:
        _append_unique(aliases, name.replace("倒蹬", "腿举"))
        _append_unique(aliases, name.replace("倒蹬", "腿推"))

    canonical = "".join(name.split())
    item["aliases"] = [value for value in aliases if value != canonical]


def _load_offline_dataset() -> list[dict[str, Any]]:
    """Load the imported Chinese exercise dataset when it ships with the app."""
    path = Path(__file__).with_name("exercise_catalog_data.json")
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    additions_path = Path(__file__).with_name("exercise_catalog_additions.json")
    try:
        additions = json.loads(additions_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        additions = []
    if isinstance(additions, list):
        values.extend(additions)
    catalog = [item for item in values if isinstance(item, dict) and str(item.get("name") or "").strip()]
    # Keep reviewed naming/classification corrections separate from the large
    # generated data file so a future upstream rebuild cannot silently undo
    # them. IDs and media references remain unchanged.
    override_path = Path(__file__).with_name("exercise_catalog_overrides.json")
    try:
        canonical_overrides = json.loads(override_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        canonical_overrides = {}
    for item in catalog:
        old_name = _apply_common_catalog_terminology(item)
        override = canonical_overrides.get(str(item.get("id") or "").removeprefix("dataset:"))
        if override is not None:
            item.update(override)
        _apply_common_search_aliases(item, old_name)
    return catalog


# The offline dataset replaces the previous small strength library.  Keep the
# legacy definitions only as a safe development fallback when the data file is
# absent; user-created actions continue to be appended separately.
EXERCISE_LIBRARY = _load_offline_dataset() or _LEGACY_EXERCISE_LIBRARY
_CATEGORY_ORDER = (
    "胸", "背", "腿", "肩", "二头", "三头", "小臂", "颈部", "臀部",
    "功能性", "核心稳定", "腹部", "热身动作", "拉伸", "有氧", "全身", "计时动作", "Tabata", "自重", "其他",
)
_AVAILABLE_CATEGORIES = {str(item.get("category") or "其他") for item in EXERCISE_LIBRARY}
EXERCISE_CATEGORIES = tuple(category for category in _CATEGORY_ORDER if category in _AVAILABLE_CATEGORIES)

_EXERCISES_BY_NAME = {exercise["name"].casefold(): exercise for exercise in EXERCISE_LIBRARY}


def _normalized(value: str) -> str:
    return "".join(value.split()).casefold()


def normalize_custom_exercise(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    name = str(value.get("name", "")).strip()
    if not name:
        return None
    mode = str(value.get("recording_mode", "strength"))
    if mode not in {"strength", "timed", "cardio"}:
        mode = "strength"

    def text_list(key: str) -> list[str]:
        raw = value.get(key, [])
        if not isinstance(raw, list):
            return []
        return [str(item).strip() for item in raw if str(item).strip()]

    return {
        "name": name,
        "category": str(value.get("category") or "其他").strip(),
        "equipment": str(value.get("equipment") or "其他").strip(),
        "target_muscles": text_list("target_muscles"),
        "cues": text_list("cues"),
        "mistakes": text_list("mistakes"),
        "default_weight_kg": value.get("default_weight_kg"),
        "default_reps": value.get("default_reps", 10),
        "default_sets": value.get("default_sets", 4),
        "recording_mode": mode,
        "distance_enabled": bool(value.get("distance_enabled", mode == "cardio")),
        "cardio_metric_fields": text_list("cardio_metric_fields"),
        "aliases": text_list("aliases"),
        "default_duration_seconds": value.get("default_duration_seconds"),
    }


def load_custom_exercises(path: Path = TRAINING_FILE) -> list[dict[str, Any]]:
    payload = load_json(path, {})
    values = payload.get("custom_exercises", []) if isinstance(payload, dict) else []
    normalized = [normalize_custom_exercise(item) for item in values] if isinstance(values, list) else []
    return [item for item in normalized if item is not None]


def save_custom_exercise(exercise: dict[str, Any], path: Path = TRAINING_FILE) -> dict[str, Any]:
    normalized = normalize_custom_exercise(exercise)
    if normalized is None:
        raise ValueError("请填写动作名称")
    name_key = normalized["name"].casefold()
    if name_key in _EXERCISES_BY_NAME:
        raise ValueError("动作名称已存在")

    payload = load_json(path, {})
    if not isinstance(payload, dict):
        payload = {}
    existing = load_custom_exercises(path)
    if any(item["name"].casefold() == name_key for item in existing):
        raise ValueError("动作名称已存在")
    payload["custom_exercises"] = [*existing, normalized]
    save_json(path, payload)
    return normalized


def delete_custom_exercise(name: str, path: Path = TRAINING_FILE) -> bool:
    """Remove only a library definition; sessions retain their copied exercise data."""
    name_key = str(name or "").strip().casefold()
    if not name_key or name_key in _EXERCISES_BY_NAME:
        return False
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return False
    existing = load_custom_exercises(path)
    retained = [item for item in existing if item["name"].casefold() != name_key]
    if len(retained) == len(existing):
        return False
    payload["custom_exercises"] = retained
    save_json(path, payload)
    return True


def exercise_catalog(custom_exercises: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    custom = load_custom_exercises() if custom_exercises is None else custom_exercises
    # User entries intentionally come first: a custom variant with the same
    # display name must remain selectable after the much larger offline import.
    return [*custom, *EXERCISE_LIBRARY]


def search_exercises(
    query: str,
    category: str | None = None,
    exercises: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Search names, equipment and target muscles, optionally within one category."""
    needle = _normalized(query or "")
    matches = [
        exercise
        for exercise in (EXERCISE_LIBRARY if exercises is None else exercises)
        if (category is None or exercise["category"] == category)
        and needle in _normalized(" ".join([
            exercise["name"],
            exercise["category"],
            exercise["equipment"],
            *exercise.get("aliases", []),
            *exercise["target_muscles"],
        ]))
    ]
    if not needle:
        return matches

    def relevance(exercise: dict[str, Any]) -> tuple[int, int, int]:
        name = _normalized(str(exercise.get("name") or ""))
        aliases = [_normalized(str(value)) for value in exercise.get("aliases", [])]
        if name == needle:
            match_rank = 0
        elif needle in aliases:
            match_rank = 1
        elif name.startswith(needle):
            match_rank = 2
        elif needle in name:
            match_rank = 3
        else:
            match_rank = 4
        return (match_rank, -int(exercise.get("search_priority") or 0), len(name))

    return sorted(matches, key=relevance)


def search_exercises_with_fallback(
    query: str,
    category: str | None,
    subgroup: str = "全部",
    equipment: str = "全部",
    exercises: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Search strictly first, then relax filters instead of showing a dead end.

    The returned scope is empty for an exact filter match, ``filters`` when
    only subgroup/equipment were relaxed, and ``category`` when the selected
    body part also had to be relaxed.
    """
    pool = EXERCISE_LIBRARY if exercises is None else exercises
    category_matches = search_exercises(query, category, pool)

    def apply_detail_filters(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = values
        if subgroup != "全部":
            result = [item for item in result if str(item.get("subgroup") or "整体") == subgroup]
        if equipment != "全部":
            result = [item for item in result if str(item.get("equipment") or "其他") == equipment]
        return result

    strict = apply_detail_filters(category_matches)
    if strict or not _normalized(query or ""):
        return strict, ""
    if category_matches:
        return category_matches, "filters"
    global_matches = search_exercises(query, None, pool)
    return (global_matches, "category") if global_matches else ([], "")


def get_exercise(name: str) -> dict[str, Any] | None:
    """Return an exercise by exact name, ignoring surrounding whitespace and case."""
    return _EXERCISES_BY_NAME.get((name or "").strip().casefold())

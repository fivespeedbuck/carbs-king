"""Apply a conservative offline terminology pass to Chinese exercise names."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


PHRASES = {
    "dumbbell incline breeding": "哑铃上斜飞鸟",
    "dumbbell lying femoral": "哑铃仰卧腘绳肌训练",
    "dumbbell rear delt row_shoulder": "哑铃后三角肌肩部划船",
    "exercise ball one legged diagonal kick hamstring curl": "健身球单腿对角踢腿腘绳肌弯举",
    "ez bar french press on exercise ball": "健身球上 EZ 曲杆法式推举",
    "ez bar standing french press": "EZ 曲杆站姿法式推举",
    "ez barbell anti gravity press": "EZ 杠铃反重力推举",
    "ez barbell decline close grip face press": "EZ 杠铃下斜窄握面部推举",
    "ez barbell seated curls": "EZ 杠铃坐姿弯举",
    "ez-bar biceps curl (with arm blaster)": "EZ 曲杆二头肌弯举（固臂器）",
    "farmers walk": "农夫行走",
    "frankenstein squat": "弗兰肯斯坦深蹲",
    "front lever reps": "前水平支撑重复动作",
    "full maltese": "全程马耳他挺身",
    "glute-ham raise": "臀腿挺身",
    "groin crunch": "腹股沟卷腹",
    "hands bike": "手摇单车",
    "hug keens to chest": "抱膝贴胸",
    "hyght dumbbell fly": "高位哑铃飞鸟",
    "incline push up depth jump": "上斜俯卧撑深度跳",
    "incline twisting sit-up": "上斜转体仰卧起坐",
    "inverse leg curl (bench support)": "反向腿弯举（卧推凳支撑）",
    "inverse leg curl (on pull-up cable machine)": "引体向上绳索器械反向腿弯举",
    "inverted row bent knees": "屈膝反向划船",
    "inverted row with straps": "悬吊带反向划船",
    "iron cross stretch": "铁十字拉伸",
    "isometric chest squeeze": "等长胸部挤压",
    "isometric wipers": "等长雨刷式",
    "jack burpee": "开合波比跳",
    "jack jump (male)": "开合跳（男士）",
    "jackknife sit-up": "折刀式仰卧起坐",
    "janda sit-up": "珍达式仰卧起坐",
    "jump rope": "跳绳",
    "kettlebell advanced windmill": "壶铃进阶风车",
    "kettlebell alternating hang clean": "壶铃交替悬垂翻举",
    "kettlebell alternating renegade row": "壶铃交替叛徒划船",
    "kettlebell arnold press": "壶铃阿诺德推举",
    "kettlebell bottoms up clean from the hang position": "壶铃悬垂倒置翻举",
    "kettlebell double alternating hang clean": "壶铃双手交替悬垂翻举",
    "kettlebell double jerk": "壶铃双手挺举",
    "kettlebell double push press": "壶铃双手借力推举",
    "kettlebell double snatch": "壶铃双手抓举",
    "kettlebell double windmill": "壶铃双手风车",
    "kettlebell extended range one arm press on floor": "壶铃地面单臂全程推举",
    "kettlebell figure 8": "壶铃 8 字绕铃",
    "kettlebell hang clean": "壶铃悬垂翻举",
    "kettlebell lunge pass through": "壶铃箭步蹲传递",
    "kettlebell one arm push press": "壶铃单臂借力推举",
    "kettlebell plyo push-up": "壶铃增强式俯卧撑",
    "kettlebell seesaw press": "壶铃跷跷板推举",
    "kettlebell sumo high pull": "壶铃相扑式高拉",
    "kettlebell turkish get up (squat style)": "壶铃土耳其起立（深蹲式）",
    "kettlebell windmill": "壶铃风车",
    "kettlebell pirate supper legs": "壶铃海盗式腿部动作",
    "kick out sit": "踢腿坐起",
    "knee touch crunch": "触膝卷腹",
    "l-sit on floor": "地面 L 型支撑",
    "london bridge": "伦敦桥式臀桥",
    "mixed grip chin-up": "混合握引体向上",
    "lever gripper hands": "杠杆式握力器训练",
    "lever horizontal one leg press": "杠杆式水平单腿推举",
    "lever lying two-one leg curl": "杠杆式仰卧双单腿弯举",
    "lever t-bar reverse grip row": "杠杆式 T 杆反握划船",
    "lever unilateral row": "杠杆式单侧划船",
    "medicine ball chest push from 3 point stance": "药球三点支撑胸部推举",
    "medicine ball chest push multiple response": "药球胸部多次反应推举",
    "medicine ball chest push single response": "药球胸部单次反应推举",
    "medicine ball overhead slam": "药球过头砸球",
    "modified hindu push-up (male)": "改良印度俯卧撑（男士）",
    "monster walk": "怪兽行走",
    "negative crunch": "离心卷腹",
    "olympic barbell hammer curl": "奥林匹克杠铃锤式弯举",
    "olympic barbell triceps extension": "奥林匹克杠铃三头肌伸展",
    "one arm towel row": "单臂毛巾划船",
    "one arm slam (with medicine ball)": "单臂药球砸球",
    "one leg donkey calf raise": "单腿驴式提踵",
    "pelvic tilt into bridge": "骨盆倾斜转臀桥",
    "peroneals stretch": "腓骨肌拉伸",
    "pike-to-cobra push-up": "折刀转眼镜蛇俯卧撑",
    "plyo push up": "增强式俯卧撑",
    "potty squat": "如厕深蹲",
    "potty squat with support": "支撑如厕深蹲",
    "power clean": "力量翻举",
    "power point plank": "力量点平板支撑",
    "quick feet v. 2": "快速小碎步第二式",
    "pull-in (on stability ball)": "健身球上收腿",
    "push-up close-grip off dumbbell": "哑铃窄距俯卧撑",
    "push-up plus": "肩胛前伸俯卧撑",
    "quarter sit-up": "四分之一仰卧起坐",
    "reclining big toe pose with rope": "绳索仰卧大脚趾式",
    "resistance band hip thrusts on knees (female)": "弹力带跪姿臀推（女士）",
    "rocking frog stretch": "摇摆青蛙拉伸",
    "rocky pull-up pulldown": "洛基引体向上下拉",
    "rope climb": "绳索攀爬",
    "runners stretch": "跑者拉伸",
    "scapular pull-up": "肩胛引体向上",
    "seated wide angle pose sequence": "坐姿宽角式序列",
    "scissor jumps (male)": "剪刀跳（男士）",
    "semi squat jump (male)": "半蹲跳（男士）",
    "short stride run": "短步幅跑",
    "shoulder tap": "触肩",
    "shoulder tap push-up": "触肩俯卧撑",
    "ski step": "滑雪步",
    "sledge hammer": "大锤挥击",
    "single leg bridge with outstretched leg": "伸腿单腿臀桥",
    "single leg platform slide": "单腿踏台滑动",
    "sled 45 degrees one leg press": "雪橇 45 度单腿推举",
    "sled 45в° leg press (back pov)": "雪橇 45 度腿举（后视角）",
    "sled 45° leg press (side pov)": "雪橇 45 度腿举（侧视角）",
    "sled closer hack squat": "雪橇窄距哈克深蹲",
    "smith behind neck press": "史密斯颈后推举",
    "smith chair squat": "史密斯椅式深蹲",
    "smith decline reverse-grip press": "史密斯下斜反握推举",
    "smith incline reverse-grip press": "史密斯上斜反握推举",
    "smith reverse-grip press": "史密斯反握推举",
    "smith sprint lunge": "史密斯冲刺箭步蹲",
    "snatch pull": "抓举高拉",
    "spider crawl push up": "蜘蛛爬行俯卧撑",
    "spine stretch": "脊柱拉伸",
    "spine twist": "脊柱转体",
    "split squats": "分腿深蹲",
    "stalder press": "斯塔尔德推举",
    "star jump (male)": "星形跳（男士）",
    "stationary bike run v. 3": "动感单车冲刺第三式",
    "stationary bike walk": "动感单车行走",
    "stability ball crunch (full range hands behind head)": "健身球全程颈后卷腹",
    "standing behind neck press": "站姿颈后推举",
    "standing hamstring and calf stretch with strap": "拉带站姿腘绳肌小腿拉伸",
    "straddle maltese": "分腿马耳他挺身",
    "suspended abdominal fallout": "悬吊腹部前伸",
    "suspended push-up": "悬吊俯卧撑",
    "suspended reverse crunch": "悬吊反向卷腹",
    "suspended row": "悬吊划船",
    "suspended split squat": "悬吊分腿深蹲",
    "swimmer kicks v. 2 (male)": "游泳踢腿第二式（男士）",
    "triceps dip (between benches)": "双凳三头肌臂屈伸",
    "twin handle parallel grip lat pulldown": "双把平行握高位下拉",
    "twisted leg raise": "转体举腿",
    "twisted leg raise (female)": "转体举腿（女士）",
    "v-sit on floor": "地面 V 型支撑",
    "vertical leg raise (on parallel bars)": "双杠垂直举腿",
    "walk elliptical cross trainer": "椭圆机行走",
    "walking lunge": "行走箭步蹲",
    "weighted close grip chin-up on dip cage": "双杠架负重窄握引体向上",
    "weighted cossack squats (male)": "负重哥萨克深蹲（男士）",
    "weighted one hand pull up": "负重单手引体向上",
    "weighted donkey calf raise": "负重驴式提踵",
    "weighted drop push up": "负重落差俯卧撑",
}

WORDS = {
    "bends": "弯曲", "bike": "单车", "blaster": "固臂器", "catch": "接球", "clasped": "交握", "crawl": "爬行",
    "crunches": "卷腹", "curls": "弯举", "depth": "深度", "delt": "三角肌", "donkey": "驴式", "equipment": "器械",
    "face": "面部", "femoral": "腘绳肌", "flexion": "屈曲", "grip": "握法", "gripless": "无握把", "ham": "腘绳肌",
    "hands": "手", "high": "高位", "horizontal": "水平", "hyper": "挺身", "incline": "上斜", "inside": "内侧",
    "inverse": "反向", "jack": "开合", "knees": "膝盖", "maltese": "马耳他挺身", "modified": "改良", "multiple": "多次",
    "negative": "离心", "oblique": "腹斜肌", "outside": "外侧", "pad": "垫", "pass": "传递", "plyo": "增强式",
    "point": "点", "pose": "式", "posterior": "后侧", "pull": "拉", "push": "推", "raised": "抬起",
    "raises": "举", "reach": "伸展", "reclining": "仰卧", "release": "释放", "renegade": "叛徒", "reps": "重复",
    "reversed": "反向", "reverse": "反向", "rotary": "旋转", "round": "环绕", "run": "跑步", "scapular": "肩胛",
    "seated": "坐姿", "self": "自我", "shoulder": "肩部", "single": "单", "sit": "坐姿", "squeeze": "挤压",
    "staircase": "楼梯", "stationary": "固定", "style": "式", "support": "支撑", "tap": "触碰", "throw": "投掷",
    "tibialis": "胫骨肌", "toe": "脚趾", "towel": "毛巾", "treadmill": "跑步机", "twisting": "转体", "vertical": "垂直",
    "walking": "行走", "walk": "行走", "wipers": "雨刷式", "windmill": "风车", "with": "配", "without": "无",
}


def localize(source_name: str, current_name: str) -> str:
    exact = PHRASES.get(source_name.casefold())
    if exact:
        return exact
    result = current_name
    for english, chinese in sorted(WORDS.items(), key=lambda item: len(item[0]), reverse=True):
        result = re.sub(rf"(?i)\b{re.escape(english)}\b", chinese, result)
    return re.sub(r"\s+", " ", result).strip()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with (root / "outputs/exercise_name_translation/remaining_english_names.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    overrides = {
        row["id"].replace("dataset:", "").zfill(4): localize(row["source"], row["name"])
        for row in rows
    }
    (root / "outputs/exercise_name_translation/fourth_residual_name_overrides.json").write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()

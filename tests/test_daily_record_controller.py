import ast
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_state import AppState  # noqa: E402
from daily_record_controller import DailyRecordController, DailyRecordDependencies  # noqa: E402
from nutrition_service import create_nutrition_service  # noqa: E402
from repositories import AppRepositories  # noqa: E402


MEALS = ("早餐", "午餐", "晚餐", "练前", "练后", "偷吃")


class MemoryRepository:
    def __init__(self, value):
        self.value = value

    def load(self):
        return self.value

    def save(self, value):
        self.value = value


def build_controller(records=None):
    state = AppState.default(MEALS)
    records = records or {}
    repository = MemoryRepository(records)
    repositories = AppRepositories(repository, MemoryRepository([]), MemoryRepository([]), MemoryRepository({}), MemoryRepository({}))
    events = []
    controller = DailyRecordController(DailyRecordDependencies(
        state=state,
        repositories=repositories,
        records=records,
        nutrition=create_nutrition_service(state),
        meals=MEALS,
        load_profile=lambda: {},
        sleep_total_minutes=lambda: 450,
        format_minutes=lambda value: f"{value // 60}小时{value % 60}分",
        restore_training_cursor=lambda: events.append("cursor"),
        refresh=lambda: events.append("refresh"),
        snack=lambda message: events.append(message),
    ))
    return controller, state, repository, events


class DailyRecordControllerTests(unittest.TestCase):
    def test_save_preserves_daily_record_contract(self):
        controller, state, repository, events = build_controller()
        state["meals"]["早餐"] = [{"name": "燕麦", "kcal": 100, "carb": 20, "protein": 4, "fat": 2}]
        controller.save(show=True)

        saved = repository.value[state["date"]]
        self.assertEqual(saved["meal_totals"]["早餐"]["kcal"], 100)
        self.assertEqual(saved["sleep"]["total_minutes"], 450)
        self.assertIn("session", saved["training"])
        self.assertIn("已保存", events)

    def test_load_normalizes_missing_sections_without_changing_disk_shape(self):
        records = {"2026-07-01": {"profile": {"day_type": "低碳日"}, "training": [], "meals": {"早餐": [{}]}}}
        controller, state, _, events = build_controller(records)
        controller.load("2026-07-01")

        self.assertEqual(state["day_type"], "低碳日")
        self.assertEqual(len(state["meals"]["早餐"]), 1)
        self.assertEqual(state["training"]["sessions"], [])
        self.assertEqual(events[-2:], ["cursor", "refresh"])

    def test_calendar_event_survives_followup_diet_save(self):
        controller, state, repository, _ = build_controller()
        target_date = state["date"]
        event = {"type": "custom", "text": "出差"}

        controller.update_calendar_event(target_date, event)
        state["meals"][MEALS[0]].append({"food": "米饭", "kcal": 116})
        controller.save()

        saved = repository.value[target_date]
        self.assertEqual(saved["calendar_event"], event)
        self.assertEqual(saved["meals"][MEALS[0]][0]["food"], "米饭")

    def test_current_circumference_syncs_state_and_survives_training_save(self):
        controller, state, repository, _ = build_controller()
        target_date = state["date"]

        controller.update_circumference(
            target_date,
            "waist_cm",
            80.5,
            measured_at="2026-07-22T08:00:00",
            note="晨起",
        )
        self.assertEqual(state["circumference"]["waist_cm"], 80.5)
        state["training"]["session"] = {
            "id": "session-current",
            "date": target_date,
            "status": "planned",
        }
        controller.save()

        circumference = repository.value[target_date]["profile"]["circumference"]
        self.assertEqual(circumference["waist_cm"], 80.5)
        self.assertEqual(circumference["notes"]["waist_cm"], "晨起")
        self.assertEqual(repository.value[target_date]["training"]["session"]["id"], "session-current")

    def test_clear_training_removes_all_training_sources_but_preserves_daily_data(self):
        controller, state, repository, events = build_controller()
        target_date = state["date"]
        state["meals"][MEALS[0]] = [{"food": "米饭", "kcal": 116}]
        state["water"] = [300]
        state["supplements"] = [{"name": "肌酸"}]
        controller.update_calendar_event(target_date, {"type": "custom", "text": "出差"})
        controller.update_circumference(target_date, "waist_cm", 80, measured_at="2026-07-22T08:00:00")
        state["training"].update({
            "total_duration_min": "60", "total_calories_kcal": "500",
            "targets": [{"target": "腿"}],
            "session": {"id": "current", "status": "completed", "exercises": [{"name": "深蹲"}]},
            "sessions": [{"id": "morning", "status": "completed"}],
        })
        controller.save()

        controller.clear_training(target_date)

        saved = repository.value[target_date]
        self.assertIsNone(saved["training"]["session"])
        self.assertEqual(saved["training"]["sessions"], [])
        self.assertEqual(saved["training"]["targets"], [])
        self.assertEqual(saved["training"]["total_duration_min"], "")
        self.assertEqual(saved["training"]["total_calories_kcal"], "")
        self.assertEqual(saved["meals"][MEALS[0]][0]["food"], "米饭")
        self.assertEqual(saved["water"]["records_ml"], [300])
        self.assertEqual(saved["supplements"][0]["name"], "肌酸")
        self.assertEqual(saved["calendar_event"]["text"], "出差")
        self.assertEqual(saved["profile"]["circumference"]["waist_cm"], 80)
        self.assertIn("cursor", events)
        self.assertIn("refresh", events)

    def test_clear_historical_training_does_not_replace_other_record_sections(self):
        records = {"2026-07-01": {
            "meals": {"早餐": [{"food": "燕麦"}]},
            "recovery": {"score": 8},
            "calendar_event": {"text": "休假"},
            "training": {"session": {"id": "old"}, "sessions": [{"id": "old"}], "total_duration_min": "40"},
        }}
        controller, _, repository, _ = build_controller(records)

        controller.clear_training("2026-07-01")

        saved = repository.value["2026-07-01"]
        self.assertEqual(saved["meals"]["早餐"][0]["food"], "燕麦")
        self.assertEqual(saved["recovery"]["score"], 8)
        self.assertEqual(saved["calendar_event"]["text"], "休假")
        self.assertIsNone(saved["training"]["session"])
        self.assertEqual(saved["training"]["sessions"], [])

    def test_delete_one_circumference_keeps_other_metrics_and_daily_sections(self):
        records = {"2026-07-22": {
            "meals": {"早餐": [{"food": "燕麦"}]},
            "calendar_event": {"text": "体检"},
            "profile": {"circumference": {
                "measured_at": "2026-07-22T08:00:00",
                "waist_cm": 80,
                "chest_cm": 100,
                "notes": {"waist_cm": "晨起", "chest_cm": "自然呼吸"},
            }},
        }}
        controller, state, repository, _ = build_controller(records)
        state["date"] = "2026-07-22"

        self.assertTrue(controller.delete_circumference("2026-07-22", "waist_cm"))

        saved = repository.value["2026-07-22"]
        circumference = saved["profile"]["circumference"]
        self.assertNotIn("waist_cm", circumference)
        self.assertEqual(circumference["chest_cm"], 100)
        self.assertEqual(circumference["notes"], {"chest_cm": "自然呼吸"})
        self.assertEqual(saved["meals"]["早餐"][0]["food"], "燕麦")
        self.assertEqual(saved["calendar_event"]["text"], "体检")
        self.assertEqual(state["circumference"]["chest_cm"], 100)

    def test_delete_last_circumference_keeps_profile_and_other_daily_data(self):
        records = {"2026-07-22": {
            "meals": {"早餐": [{"food": "燕麦"}]},
            "profile": {
                "day_type": "高碳日",
                "circumference": {"measured_at": "2026-07-22T08:00:00", "calf_cm": 38},
            },
        }}
        controller, _, repository, _ = build_controller(records)

        self.assertTrue(controller.delete_circumference("2026-07-22", "calf_cm"))

        saved = repository.value["2026-07-22"]
        self.assertNotIn("circumference", saved["profile"])
        self.assertEqual(saved["profile"]["day_type"], "高碳日")
        self.assertEqual(saved["meals"]["早餐"][0]["food"], "燕麦")

    def test_daily_record_controller_does_not_import_flet_or_main(self):
        tree = ast.parse((ROOT / "src" / "daily_record_controller.py").read_text(encoding="utf-8"))
        imported = {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported.update(
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertFalse(imported & {"flet", "main"})


if __name__ == "__main__":
    unittest.main()

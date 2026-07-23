import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_state import AppState  # noqa: E402
from backup_service import BackupServiceDependencies, create_backup_service  # noqa: E402
from repositories import AppRepositories  # noqa: E402
from storage_service import load_json, save_json  # noqa: E402


MEALS = ("早餐", "午餐", "晚餐", "练前", "练后", "偷吃")


class MemoryRepository:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.fail_next_save = False

    def load(self):
        return copy.deepcopy(self.value)

    def save(self, value):
        if self.fail_next_save:
            self.fail_next_save = False
            raise OSError("simulated write failure")
        self.value = copy.deepcopy(value)


def build_service(root: Path):
    records = {"2026-07-22": {"calendar_event": {"text": "原事项"}}}
    foods = [{"name": "米饭", "base_qty": 100, "custom": {"keep": True}}]
    supplements = [{"name": "肌酸", "default_amount": 5}]
    profile_store = {"value": {"weight": "80", "profile_inited": True, "unknown": "keep"}}
    achievements = {"first_training": "2026-07-20T08:00:00"}
    repositories = AppRepositories(
        MemoryRepository(records),
        MemoryRepository(foods),
        MemoryRepository(supplements),
        MemoryRepository(profile_store["value"]),
        MemoryRepository(achievements),
    )
    save_json(root / "training_data.json", {
        "custom_exercises": [{"name": "自定义动作"}],
        "active_session": {"name": "应清除的当前训练"},
    })
    state = AppState.default(MEALS)
    state["date"] = "2026-07-22"
    reloads = []

    def load_profile():
        return copy.deepcopy(profile_store["value"])

    def save_profile(value):
        profile_store["value"] = copy.deepcopy(value)

    service = create_backup_service(BackupServiceDependencies(
        state=state,
        repositories=repositories,
        records=records,
        foods=foods,
        supplements=supplements,
        app_dir=root,
        app_version="1.2.1",
        load_profile=load_profile,
        save_profile=save_profile,
        reload_date=lambda *args, **kwargs: reloads.append((args, kwargs)),
    ))
    return service, state, repositories, records, foods, supplements, profile_store, reloads


class BackupServiceTests(unittest.TestCase):
    def test_full_payload_contains_all_persisted_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            service, _, _, _, _, _, _, _ = build_service(Path(temp))
            payload = service.build_payload()

            self.assertEqual(payload["backup_version"], 2)
            self.assertIn("daily_records", payload)
            self.assertIn("food_library", payload)
            self.assertIn("supplement_library", payload)
            self.assertIn("user_profile", payload)
            self.assertIn("achievement_unlocks", payload)
            self.assertEqual(payload["training_data"]["custom_exercises"][0]["name"], "自定义动作")

    def test_legacy_full_backup_is_valid_but_partial_backup_is_not(self):
        with tempfile.TemporaryDirectory() as temp:
            service, _, _, _, _, _, _, _ = build_service(Path(temp))
            legacy = {
                "daily_records": {},
                "food_library": [],
                "supplement_library": [],
                "user_profile": {"weight": "75"},
            }
            normalized = service.normalize_payload(legacy)
            service.validate_full(normalized)

            with self.assertRaisesRegex(ValueError, "完整备份"):
                service.validate_full({"daily_records": {}})

    def test_full_restore_replaces_all_sections_and_keeps_unknown_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service, state, repositories, records, foods, supplements, profile_store, reloads = build_service(root)
            incoming = {
                "daily_records": {"2026-07-21": {"future_section": {"value": 1}}},
                "food_library": [{"name": "燕麦", "base_qty": 50, "future": 2}],
                "supplement_library": [{"name": "鱼油", "default_amount": 2}],
                "user_profile": {"weight": "72", "profile_inited": True, "future_profile": 3},
                "achievement_unlocks": {"streak_7": "done"},
                "training_data": {"custom_exercises": [{"name": "雪橇推"}]},
            }

            service.validate_full(incoming)
            service.apply(incoming, "replace")

            self.assertEqual(records, incoming["daily_records"])
            self.assertEqual(foods, incoming["food_library"])
            self.assertEqual(supplements, incoming["supplement_library"])
            self.assertEqual(profile_store["value"]["future_profile"], 3)
            self.assertEqual(repositories.achievements.value, incoming["achievement_unlocks"])
            self.assertEqual(load_json(root / "training_data.json", {}), incoming["training_data"])
            self.assertEqual(state["weight"], "72")
            self.assertEqual(len(reloads), 1)
            self.assertEqual(len(list((root / "import_safety_backups").glob("before_import_*.json"))), 1)

    def test_old_full_restore_preserves_sections_missing_from_legacy_format(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service, _, repositories, _, _, _, _, _ = build_service(root)
            old_achievements = repositories.achievements.load()
            old_training = load_json(root / "training_data.json", {})
            incoming = {
                "daily_records": {},
                "food_library": [],
                "supplement_library": [],
                "user_profile": {"weight": "70"},
            }

            service.apply(incoming, "replace")

            self.assertEqual(repositories.achievements.value, old_achievements)
            self.assertEqual(load_json(root / "training_data.json", {}), old_training)

    def test_failed_restore_rolls_every_section_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service, state, repositories, records, foods, supplements, profile_store, reloads = build_service(root)
            before = service.build_payload()
            repositories.achievements.fail_next_save = True
            incoming = {
                "daily_records": {},
                "food_library": [{"name": "坏数据", "base_qty": 1}],
                "supplement_library": [],
                "user_profile": {"weight": "1"},
                "achievement_unlocks": {},
                "training_data": {},
            }

            with self.assertRaisesRegex(RuntimeError, "已自动恢复"):
                service.apply(incoming, "replace")

            self.assertEqual(records, before["daily_records"])
            self.assertEqual(foods, before["food_library"])
            self.assertEqual(supplements, before["supplement_library"])
            self.assertEqual(profile_store["value"], before["user_profile"])
            self.assertEqual(repositories.achievements.value, before["achievement_unlocks"])
            self.assertEqual(load_json(root / "training_data.json", {}), before["training_data"])
            self.assertEqual(state["weight"], before["user_profile"]["weight"])
            self.assertEqual(len(reloads), 1)

    def test_clear_personal_data_preserves_libraries_and_custom_exercises(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service, state, repositories, records, foods, supplements, profile_store, reloads = build_service(root)
            original_foods = copy.deepcopy(foods)
            original_supplements = copy.deepcopy(supplements)

            result = service.clear_personal_data()

            self.assertEqual(result["record_days"], 1)
            self.assertEqual(records, {})
            self.assertEqual(repositories.records.load(), {})
            self.assertEqual(repositories.achievements.load(), {})
            self.assertEqual(profile_store["value"], {})
            self.assertFalse(state["profile_inited"])
            self.assertEqual(state["weight"], "62.5")
            self.assertEqual(foods, original_foods)
            self.assertEqual(supplements, original_supplements)
            self.assertEqual(repositories.foods.load(), original_foods)
            self.assertEqual(repositories.supplements.load(), original_supplements)
            self.assertEqual(
                load_json(root / "training_data.json", {}),
                {"custom_exercises": [{"name": "自定义动作"}]},
            )
            self.assertEqual(len(reloads), 1)
            self.assertFalse((root / "import_safety_backups").exists())

    def test_failed_personal_clear_rolls_back_without_touching_libraries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service, _, repositories, records, foods, supplements, profile_store, _ = build_service(root)
            before = service.build_payload()
            repositories.achievements.fail_next_save = True

            with self.assertRaisesRegex(RuntimeError, "已自动恢复"):
                service.clear_personal_data()

            self.assertEqual(records, before["daily_records"])
            self.assertEqual(profile_store["value"], before["user_profile"])
            self.assertEqual(repositories.achievements.load(), before["achievement_unlocks"])
            self.assertEqual(foods, before["food_library"])
            self.assertEqual(supplements, before["supplement_library"])
            self.assertEqual(load_json(root / "training_data.json", {}), before["training_data"])


class BackupUiContractTests(unittest.TestCase):
    def test_profile_backup_panel_exposes_full_backup_and_personal_clear(self):
        source = (ROOT / "src" / "profile_backup_views.py").read_text(encoding="utf-8-sig")
        self.assertIn('"全量导出"', source)
        self.assertIn('"全量导入"', source)
        self.assertIn('"清除个人数据"', source)
        for removed_label in ("历史记录", "个人资料", "食物库", "补剂库", "合并导入", "覆盖导入"):
            self.assertNotIn(f'"{removed_label}"', source)

    def test_import_controller_requires_full_backup_and_one_restore_action(self):
        source = (ROOT / "src" / "backup_controller.py").read_text(encoding="utf-8-sig")
        self.assertIn("service.validate_full(import_data)", source)
        self.assertIn('service.apply(import_data, "replace")', source)
        self.assertNotIn('confirm("merge")', source)
        self.assertNotIn('confirm("replace")', source)

    def test_personal_clear_requires_two_confirmations_and_names_preserved_libraries(self):
        source = (ROOT / "src" / "backup_controller.py").read_text(encoding="utf-8-sig")

        self.assertIn('"清除个人数据"', source)
        self.assertIn('"再次确认清除"', source)
        self.assertIn('"确认清除"', source)
        self.assertIn("service.clear_personal_data()", source)
        self.assertIn("食物库、补剂库和动作库仍会保留", source)


if __name__ == "__main__":
    unittest.main()

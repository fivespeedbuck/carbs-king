import asyncio
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from achievement_service import normalize_achievement_unlock_state  # noqa: E402
from app_state import AppState  # noqa: E402
from controller_runtime import ControllerRuntime  # noqa: E402
from nutrition_service import create_nutrition_service  # noqa: E402
from profile_controller import ProfileControllerDependencies, create_profile_controller  # noqa: E402
from repositories import AppRepositories  # noqa: E402


class MemoryRepository:
    def __init__(self, value):
        self.value = copy.deepcopy(value)

    def load(self):
        return copy.deepcopy(self.value)

    def save(self, value):
        self.value = copy.deepcopy(value)


class ImmediatePage:
    def run_task(self, handler, *args):
        return asyncio.run(handler(*args))


def click_confirmation(dialog):
    def walk(control):
        if control is None:
            return []
        result = [control]
        content = getattr(control, "content", None)
        if content is not None and content is not control:
            result.extend(walk(content))
        for child in getattr(control, "controls", []) or []:
            result.extend(walk(child))
        return result

    button = next(control for control in walk(dialog) if getattr(control, "on_click", None) is not None)
    button.on_click(None)


class ProfileAchievementCelebrationTests(unittest.TestCase):
    def test_profile_queues_confirms_and_never_reopens_acknowledged_achievements(self):
        state = AppState.default(("早餐", "午餐", "晚餐", "练前", "练后", "偷吃"))
        state["current_view"] = "me"
        achievement_repository = MemoryRepository({})
        repositories = AppRepositories(
            MemoryRepository({}),
            MemoryRepository([]),
            MemoryRepository([]),
            MemoryRepository({}),
            achievement_repository,
        )
        opened = []
        closed = []
        runtime = ControllerRuntime(
            page=ImmediatePage(),
            refresh=lambda: None,
            snack=lambda *args: None,
            navigate=lambda target: None,
            open_control=opened.append,
            close_control=closed.append,
            responsive_width=lambda *args: 360,
            responsive_bar_width=lambda: 340,
        )
        backup = SimpleNamespace(
            export_handler=lambda kind: (lambda event=None: None),
            import_backup=lambda event=None: None,
            clear_personal_data=lambda event=None: None,
        )
        results = [
            {"id": "first", "title": "第一枚", "description": "完成第一项。", "unlocked": True},
            {"id": "second", "title": "第二枚", "description": "完成第二项。", "unlocked": True},
        ]
        controller = create_profile_controller(ProfileControllerDependencies(
            state=state,
            repositories=repositories,
            records={},
            runtime=runtime,
            nutrition=create_nutrition_service(state),
            backup=backup,
            persist_daily=lambda *args, **kwargs: None,
            load_profile=lambda: {},
            keyboard_number=None,
            scroll_hidden=None,
        ))

        with patch("profile_controller.evaluate_achievements", return_value=results):
            controller.render_page()
            self.assertEqual(len(opened), 1)

            click_confirmation(opened[-1])
            self.assertEqual(len(opened), 2)
            self.assertEqual(len(closed), 1)

            click_confirmation(opened[-1])
            self.assertEqual(len(opened), 2)
            self.assertEqual(len(closed), 2)

            controller.render_page()
            self.assertEqual(len(opened), 2)

        stored = normalize_achievement_unlock_state(achievement_repository.load())
        self.assertEqual(stored["pending"], [])
        self.assertEqual(stored["celebrated"], ["first", "second"])


if __name__ == "__main__":
    unittest.main()

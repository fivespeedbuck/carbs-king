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
from goal_challenge_service import create_challenge, normalize_challenge_state  # noqa: E402
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
        for child in getattr(control, "actions", []) or []:
            result.extend(walk(child))
        return result

    button = next(control for control in walk(dialog) if getattr(control, "on_click", None) is not None)
    button.on_click(None)


def click_button_with_text(dialog, label):
    def walk(control):
        if control is None:
            return []
        result = [control]
        content = getattr(control, "content", None)
        if content is not None and content is not control:
            result.extend(walk(content))
        for child in getattr(control, "controls", []) or []:
            result.extend(walk(child))
        for child in getattr(control, "actions", []) or []:
            result.extend(walk(child))
        return result

    def text_values(control):
        return {
            str(getattr(item, "value", ""))
            for item in walk(control)
            if getattr(item, "value", None) is not None
        }

    button = next(
        control
        for control in walk(dialog)
        if getattr(control, "on_click", None) is not None and label in text_values(control)
    )
    button.on_click(None)


def click_control_with_text(root, label):
    def walk(control):
        if control is None:
            return []
        result = [control]
        content = getattr(control, "content", None)
        if content is not None and content is not control:
            result.extend(walk(content))
        for child in getattr(control, "controls", []) or []:
            result.extend(walk(child))
        for child in getattr(control, "actions", []) or []:
            result.extend(walk(child))
        return result

    def descendant_text(control):
        return {
            str(getattr(item, "value", ""))
            for item in walk(control)
            if getattr(item, "value", None) is not None
        }

    target = next(
        control
        for control in walk(root)
        if getattr(control, "on_click", None) is not None and label in descendant_text(control)
    )
    target.on_click(None)


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

    def test_challenge_confirmation_closes_once_and_does_not_immediately_reopen(self):
        state = AppState.default(("早餐", "午餐", "晚餐", "练前", "练后", "偷吃"))
        state["current_view"] = "me"
        challenges = []
        for index in range(2):
            item = create_challenge({
                "title": f"挑战 {index + 1}",
                "lane": "training",
                "challenge_type": "training_sessions",
                "target": 1,
                "unit": "次",
                "start_date": "2026-07-28",
                "end_date": "2026-07-28",
            }, now=f"2026-07-28T0{index + 8}:00:00")
            item.update({
                "status": "completed",
                "completed_at": "2026-07-28T10:00:00",
                "completed_value": 1,
                "final_progress": 1,
            })
            challenges.append(item)
        challenge_repository = MemoryRepository({
            "active": [],
            "completed": challenges,
            "pending_celebrations": [item["id"] for item in challenges],
            "celebrated": [],
        })
        repositories = AppRepositories(
            MemoryRepository({}),
            MemoryRepository([]),
            MemoryRepository([]),
            MemoryRepository({}),
            MemoryRepository({}),
            challenge_repository,
        )
        opened = []
        closed = []
        snacks = []
        runtime = ControllerRuntime(
            page=ImmediatePage(),
            refresh=lambda: None,
            snack=snacks.append,
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

        page = controller.render_page()
        self.assertEqual(len(opened), 0)
        click_control_with_text(page, "待确认完成")
        self.assertEqual(len(opened), 1)
        dialog_text = " ".join(
            str(getattr(item, "value", ""))
            for item in self._walk(opened[0])
        )
        self.assertIn("Yeah Buddy! Light Weight Baby!", dialog_text)
        self.assertIn("2 项挑战已完成", dialog_text)
        self.assertIn("完成了：挑战 1", dialog_text)
        self.assertIn("完成了：挑战 2", dialog_text)
        self.assertNotIn("达成条件", dialog_text)

        click_button_with_text(opened[0], "收下挑战成果")

        self.assertEqual(len(closed), 1)
        self.assertEqual(len(opened), 1)
        self.assertEqual(snacks, ["已收下 2 项挑战成果"])
        stored = normalize_challenge_state(challenge_repository.load())
        self.assertEqual(stored["pending_celebrations"], [])
        self.assertEqual(stored["celebrated"], [item["id"] for item in challenges])

        controller.render_page()
        self.assertEqual(len(opened), 1)

    def test_only_elite_challenge_plays_completion_audio_after_manual_open(self):
        class TrackingAudio:
            def __init__(self, *args, **kwargs):
                self.play_count = 0

            async def play(self):
                self.play_count += 1

        class ServicePage(ImmediatePage):
            def __init__(self):
                self.services = []

        def build_controller(level):
            state = AppState.default(("早餐", "午餐", "晚餐", "练前", "练后", "偷吃"))
            state["current_view"] = "me"
            challenge = create_challenge({
                "title": "精锐测试" if level >= 4 else "传说测试" if level == 3 else "普通测试",
                "lane": "training",
                "challenge_type": "training_sessions",
                "target": 1,
                "unit": "次",
                "start_date": "2026-07-28",
                "end_date": "2026-07-28",
                "level": level,
            }, now="2026-07-28T08:00:00")
            challenge.update({
                "status": "completed",
                "completed_at": "2026-07-28T10:00:00",
                "completed_value": 1,
                "final_progress": 1,
            })
            challenge_repository = MemoryRepository({
                "active": [],
                "completed": [challenge],
                "pending_celebrations": [challenge["id"]],
            })
            repositories = AppRepositories(
                MemoryRepository({}), MemoryRepository([]), MemoryRepository([]),
                MemoryRepository({}), MemoryRepository({}), challenge_repository,
            )
            opened = []
            page = ServicePage()
            runtime = ControllerRuntime(
                page=page,
                refresh=lambda: None,
                snack=lambda *args: None,
                navigate=lambda target: None,
                open_control=opened.append,
                close_control=lambda control: None,
                responsive_width=lambda *args: 360,
                responsive_bar_width=lambda: 340,
            )
            backup = SimpleNamespace(
                export_handler=lambda kind: (lambda event=None: None),
                import_backup=lambda event=None: None,
                clear_personal_data=lambda event=None: None,
            )
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
            return controller, page, opened

        created_audio = []
        with patch("profile_controller.fta.Audio", side_effect=lambda *args, **kwargs: created_audio.append(TrackingAudio()) or created_audio[-1]):
            ordinary, ordinary_page, ordinary_opened = build_controller(2)
            ordinary_view = ordinary.render_page()
            self.assertEqual(created_audio[-1].play_count, 0)
            click_control_with_text(ordinary_view, "待确认完成")
            self.assertEqual(len(ordinary_opened), 1)
            self.assertEqual(created_audio[-1].play_count, 0)
            self.assertEqual(len(ordinary_page.services), 1)

            legend, legend_page, legend_opened = build_controller(3)
            legend_view = legend.render_page()
            self.assertEqual(created_audio[-1].play_count, 0)
            click_control_with_text(legend_view, "待确认完成")
            self.assertEqual(len(legend_opened), 1)
            self.assertEqual(created_audio[-1].play_count, 0)
            self.assertEqual(len(legend_page.services), 1)

            elite, elite_page, elite_opened = build_controller(4)
            elite_view = elite.render_page()
            self.assertEqual(created_audio[-1].play_count, 0)
            click_control_with_text(elite_view, "待确认完成")
            self.assertEqual(len(elite_opened), 1)
            self.assertEqual(created_audio[-1].play_count, 1)
            self.assertEqual(len(elite_page.services), 1)
            self.assertIn("#C73B3B", {
                str(getattr(control, "bgcolor", "")) for control in self._walk(elite_opened[-1])
            })

    def test_failed_challenge_is_silent_and_can_be_edited_then_retried(self):
        class TrackingAudio:
            def __init__(self, *args, **kwargs):
                self.play_count = 0

            async def play(self):
                self.play_count += 1

        class ServicePage(ImmediatePage):
            def __init__(self):
                self.services = []

            def update(self):
                return None

        state = AppState.default(("早餐", "午餐", "晚餐", "练前", "练后", "偷吃"))
        state["current_view"] = "me"
        failed = create_challenge({
            "title": "卧推别认怂",
            "lane": "training",
            "challenge_type": "heavy_sets",
            "target": 3,
            "unit": "组",
            "start_date": "2026-07-01",
            "end_date": "2026-07-07",
            "action_id": "bench-press",
            "action_name": "杠铃卧推",
            "min_weight": 80,
            "level": 3,
        }, now="2026-07-01T08:00:00")
        failed.update({
            "status": "failed",
            "failed_at": "2026-07-08T00:00:00",
            "failure_reason": "挑战已超过结束日期，目标仍未完成",
        })
        challenge_repository = MemoryRepository({
            "active": [],
            "completed": [],
            "failed": [failed],
            "pending_failures": [failed["id"]],
        })
        repositories = AppRepositories(
            MemoryRepository({}), MemoryRepository([]), MemoryRepository([]),
            MemoryRepository({}), MemoryRepository({}), challenge_repository,
        )
        opened = []
        closed = []
        snacks = []
        page = ServicePage()
        runtime = ControllerRuntime(
            page=page,
            refresh=lambda: None,
            snack=lambda message, *args: snacks.append(message),
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
        created_audio = []
        with patch("profile_controller.fta.Audio", side_effect=lambda *args, **kwargs: created_audio.append(TrackingAudio()) or created_audio[-1]):
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
            view = controller.render_page()

        self.assertEqual(len(opened), 0)
        click_control_with_text(view, "挑战失败")
        self.assertEqual(len(opened), 1)
        failure_text = " ".join(
            str(getattr(item, "value", "")) for item in self._walk(opened[-1])
        )
        self.assertIn("恭喜，你成功证明了计划不会自己完成。", failure_text)
        self.assertIn("计划写得挺狠，执行得挺软。", failure_text)
        self.assertIn("嘴硬没用，记录不会替你训练。", failure_text)
        self.assertIn("不服，编辑后重来", failure_text)
        self.assertIn("先挂着丢人", failure_text)
        self.assertEqual(created_audio[0].play_count, 0)
        failure_theme_values = {
            str(value)
            for control in self._walk(opened[-1])
            for value in (getattr(control, "color", ""), getattr(control, "bgcolor", ""))
        }
        self.assertIn("#6F7774", failure_theme_values)
        self.assertNotIn("#C73B3B", failure_theme_values)

        opened[-1].title.controls[-1].on_click(None)
        self.assertEqual(len(closed), 1)
        click_control_with_text(view, "挑战失败")
        self.assertEqual(len(opened), 2)

        click_button_with_text(opened[-1], "先挂着丢人")
        stored = normalize_challenge_state(challenge_repository.load())
        self.assertEqual(stored["pending_failures"], [])
        self.assertEqual(len(stored["failed"]), 1)
        self.assertEqual(created_audio[0].play_count, 0)

        click_control_with_text(view, "挑战失败")
        self.assertEqual(len(opened), 3)
        click_button_with_text(opened[-1], "不服，编辑后重来")
        self.assertEqual(len(opened), 4)
        retry_text = " ".join(
            str(getattr(item, "value", "")) for item in self._walk(opened[-1])
        )
        self.assertIn("卧推别认怂", retry_text)
        self.assertIn("杠铃卧推", retry_text)
        self.assertIn("重新挑战", retry_text)
        self.assertEqual(created_audio[0].play_count, 0)

        click_button_with_text(opened[-1], "重新挑战")
        stored = normalize_challenge_state(challenge_repository.load())
        self.assertEqual(len(stored["active"]), 1, {"snacks": snacks, "raw": challenge_repository.load(), "opened": len(opened)})
        self.assertEqual(stored["active"][0]["title"], "卧推别认怂")
        self.assertEqual(stored["active"][0]["action_name"], "杠铃卧推")
        self.assertTrue(stored["failed"][0].get("retried_at"))
        self.assertEqual(created_audio[0].play_count, 0)

    @staticmethod
    def _walk(control):
        if control is None:
            return []
        result = [control]
        content = getattr(control, "content", None)
        if content is not None and content is not control:
            result.extend(ProfileAchievementCelebrationTests._walk(content))
        for child in getattr(control, "controls", []) or []:
            result.extend(ProfileAchievementCelebrationTests._walk(child))
        for child in getattr(control, "actions", []) or []:
            result.extend(ProfileAchievementCelebrationTests._walk(child))
        return result


if __name__ == "__main__":
    unittest.main()

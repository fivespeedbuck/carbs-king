import asyncio
import hashlib
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rest_notification import (  # noqa: E402
    DEFAULT_BELL_ASSET,
    REST_ALARM_ACTION,
    REST_ALARM_RECEIVER_CLASS,
    REST_NOTIFICATION_CAPABILITY,
    RestNotifier,
    _stable_notification_id,
)


class FakePage:
    def __init__(self):
        self.services = []
        self.tasks = []

    def run_task(self, handler, *args):
        task = asyncio.create_task(handler(*args))
        self.tasks.append(task)
        return task


class ThreadSafeFakePage(FakePage):
    def __init__(self, loop):
        super().__init__()
        self.loop = loop

    def run_task(self, handler, *args):
        future = asyncio.run_coroutine_threadsafe(handler(*args), self.loop)
        self.tasks.append(future)
        return future


class FakeAudio:
    def __init__(self, src, volume):
        self.src = src
        self.volume = volume
        self.play_count = 0

    async def play(self):
        self.play_count += 1


class FakeHaptic:
    def __init__(self):
        self.vibrate_count = 0

    async def vibrate(self):
        self.vibrate_count += 1


class FailingAudio(FakeAudio):
    async def play(self):
        self.play_count += 1
        raise RuntimeError("speaker unavailable")


class FakeSystemNotifier:
    def __init__(self):
        self.posts = []

    def post(self, *, notification_id, title, body):
        self.posts.append(
            {"notification_id": notification_id, "title": title, "body": body}
        )


class FailingSystemNotifier:
    def post(self, *, notification_id, title, body):
        raise RuntimeError("permission denied")


class PermissionDeniedSystemNotifier(FailingSystemNotifier):
    def __init__(self):
        self.requests = 0

    def request_post_permission(self):
        self.requests += 1

    def has_post_permission(self):
        return False


class FakeAlarmScheduler:
    def __init__(self, *, exact=True):
        self.exact = exact
        self.schedules = []
        self.cancels = []
        self.delivered = []

    def schedule(self, *, cycle_id, delay_seconds, request_code, title, body):
        self.schedules.append(
            {
                "cycle_id": cycle_id,
                "delay_seconds": delay_seconds,
                "request_code": request_code,
                "title": title,
                "body": body,
            }
        )
        from rest_notification import AndroidAlarmScheduleResult

        return AndroidAlarmScheduleResult(
            scheduled=True,
            exact=self.exact,
            method="setExactAndAllowWhileIdle(getBroadcast)",
            process_death_notification_supported=True,
            reason="native receiver posts after process death",
        )

    def cancel(self, *, cycle_id, request_code):
        self.cancels.append({"cycle_id": cycle_id, "request_code": request_code})
        return True

    def mark_delivered(self, *, cycle_id):
        self.delivered.append(cycle_id)
        return True


class FailingAlarmScheduler:
    def schedule(self, *, cycle_id, delay_seconds, request_code, title, body):
        raise RuntimeError("alarm service unavailable")


class RestNotifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_registers_offline_services_and_notifies_once(self):
        page = FakePage()
        notifier = RestNotifier(page, audio_factory=FakeAudio, haptic_factory=FakeHaptic)

        first = await notifier.notify_once("rest-1")
        duplicate = await notifier.notify_once("rest-1")

        self.assertEqual(notifier.audio.src, DEFAULT_BELL_ASSET)
        self.assertEqual(page.services, [notifier.audio, notifier.haptic])
        self.assertTrue(first.claimed)
        self.assertTrue(first.sound_played)
        self.assertTrue(first.vibration_succeeded)
        self.assertFalse(duplicate.claimed)
        self.assertEqual(notifier.audio.play_count, 1)
        self.assertEqual(notifier.haptic.vibrate_count, 1)

    async def test_concurrent_duplicates_are_claimed_atomically(self):
        notifier = RestNotifier(
            FakePage(), audio_factory=FakeAudio, haptic_factory=FakeHaptic
        )
        results = await asyncio.gather(
            *(notifier.notify_once("rest-concurrent") for _ in range(20))
        )

        self.assertEqual(sum(result.claimed for result in results), 1)
        self.assertEqual(notifier.audio.play_count, 1)
        self.assertEqual(notifier.haptic.vibrate_count, 1)

    async def test_capability_failures_degrade_without_raising(self):
        def unavailable_haptic():
            raise RuntimeError("no vibrator")

        notifier = RestNotifier(
            FakePage(),
            audio_factory=FailingAudio,
            haptic_factory=unavailable_haptic,
            system_factory=None,
        )
        result = await notifier.notify_once("rest-fallback")

        self.assertTrue(result.claimed)
        self.assertFalse(result.sound_played)
        self.assertFalse(result.vibration_attempted)
        self.assertEqual(len(result.errors), 2)

    async def test_android_system_notification_is_preferred_over_audio_fallback(self):
        system = FakeSystemNotifier()
        notifier = RestNotifier(
            FakePage(),
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            system_factory=lambda: system,
            notification_title="Rest done",
            notification_body="Next set",
        )

        result = await notifier.notify_once("rest-native")

        self.assertTrue(result.system_notification_attempted)
        self.assertTrue(result.system_notification_succeeded)
        self.assertTrue(result.sound_played)
        self.assertTrue(result.vibration_succeeded)
        self.assertEqual(notifier.audio.play_count, 0)
        self.assertEqual(notifier.haptic.vibrate_count, 0)
        self.assertEqual(
            system.posts,
            [{
                "notification_id": _stable_notification_id("rest-native"),
                "title": "Rest done",
                "body": "Next set",
            }],
        )

    async def test_foreground_expiry_always_plays_bundled_audio_without_notification(self):
        page = FakePage()
        system = FakeSystemNotifier()
        alarm = FakeAlarmScheduler()
        notifier = RestNotifier(
            page,
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            system_factory=lambda: system,
            alarm_scheduler_factory=lambda: alarm,
        )
        notifier.trigger_after("rest-visible", 90)

        future = notifier.trigger_foreground("rest-visible")
        duplicate = notifier.trigger_foreground("rest-visible")
        result = await future

        self.assertIsNone(duplicate)
        self.assertTrue(result.sound_played)
        self.assertEqual(notifier.audio.play_count, 1)
        self.assertEqual(system.posts, [])
        self.assertEqual(alarm.delivered, ["rest-visible"])
        self.assertEqual(len(alarm.cancels), 1)

    async def test_system_notification_failure_falls_back_to_flet_alerts(self):
        notifier = RestNotifier(
            FakePage(),
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            system_factory=lambda: FailingSystemNotifier(),
        )

        result = await notifier.notify_once("rest-system-fallback")

        self.assertTrue(result.system_notification_attempted)
        self.assertFalse(result.system_notification_succeeded)
        self.assertTrue(result.sound_played)
        self.assertTrue(result.vibration_succeeded)
        self.assertEqual(notifier.audio.play_count, 1)
        self.assertIn("system notification: permission denied", result.errors)

    async def test_trigger_claims_before_scheduling(self):
        page = FakePage()
        notifier = RestNotifier(page, audio_factory=FakeAudio, haptic_factory=FakeHaptic)

        future = notifier.trigger("rest-trigger")
        duplicate = notifier.trigger("rest-trigger")
        result = await future

        self.assertIsNone(duplicate)
        self.assertTrue(result.claimed)
        self.assertEqual(notifier.audio.play_count, 1)

    async def test_empty_id_and_previously_notified_id_are_ignored(self):
        notifier = RestNotifier(
            FakePage(),
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            notified_cycle_ids=["rest-old"],
        )

        empty = await notifier.notify_once(" ")
        old = await notifier.notify_once("rest-old")

        self.assertFalse(empty.claimed)
        self.assertFalse(old.claimed)
        self.assertEqual(notifier.audio.play_count, 0)

    async def test_trigger_after_reports_in_process_boundary_and_delivers_once(self):
        page = ThreadSafeFakePage(asyncio.get_running_loop())
        notifier = RestNotifier(page, audio_factory=FakeAudio, haptic_factory=FakeHaptic)

        scheduled = notifier.trigger_after("rest-delay", 0)
        duplicate = notifier.trigger_after("rest-delay", 0)
        await asyncio.sleep(0.05)
        result = await asyncio.wrap_future(page.tasks[0])

        self.assertTrue(scheduled.claimed)
        self.assertTrue(scheduled.timer_started)
        self.assertFalse(scheduled.exact_after_process_death)
        self.assertIn("app process is alive", scheduled.reason)
        self.assertIn("AlarmManager scheduler unavailable", scheduled.reason)
        self.assertFalse(duplicate.claimed)
        self.assertTrue(result.claimed)
        self.assertEqual(notifier.audio.play_count, 1)

    async def test_trigger_after_schedules_android_alarm_when_available(self):
        page = ThreadSafeFakePage(asyncio.get_running_loop())
        alarm = FakeAlarmScheduler()
        notifier = RestNotifier(
            page,
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            alarm_scheduler_factory=lambda: alarm,
        )

        scheduled = notifier.trigger_after("rest-alarm", 0)
        await asyncio.sleep(0.05)

        self.assertTrue(scheduled.system_alarm_attempted)
        self.assertTrue(scheduled.system_alarm_scheduled)
        self.assertTrue(scheduled.system_alarm_exact)
        self.assertTrue(scheduled.exact_after_process_death)
        self.assertTrue(scheduled.process_death_notification_supported)
        self.assertFalse(scheduled.timer_started)
        self.assertIn("native receiver", scheduled.reason)
        self.assertEqual(page.tasks, [])
        self.assertEqual(
            alarm.schedules,
            [
                {
                    "cycle_id": "rest-alarm",
                    "delay_seconds": 0.0,
                    "request_code": _stable_notification_id("rest-alarm"),
                    "title": "Rest finished",
                    "body": "Start your next set.",
                }
            ],
        )

    async def test_alarm_failure_keeps_in_process_timer(self):
        page = ThreadSafeFakePage(asyncio.get_running_loop())
        notifier = RestNotifier(
            page,
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            alarm_scheduler_factory=lambda: FailingAlarmScheduler(),
        )

        scheduled = notifier.trigger_after("rest-alarm-fallback", 0)
        await asyncio.sleep(0.05)
        result = await asyncio.wrap_future(page.tasks[0])

        self.assertTrue(scheduled.system_alarm_attempted)
        self.assertFalse(scheduled.system_alarm_scheduled)
        self.assertTrue(scheduled.timer_started)
        self.assertIn("system alarm: alarm service unavailable", scheduled.errors)
        self.assertTrue(result.claimed)

    async def test_permission_denial_keeps_foreground_fallback_and_skips_alarm(self):
        page = ThreadSafeFakePage(asyncio.get_running_loop())
        alarm = FakeAlarmScheduler()
        system = PermissionDeniedSystemNotifier()
        notifier = RestNotifier(
            page,
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            system_factory=lambda: system,
            alarm_scheduler_factory=lambda: alarm,
        )

        scheduled = notifier.trigger_after("rest-permission", 0)
        await asyncio.sleep(0.05)
        result = await asyncio.wrap_future(page.tasks[0])

        self.assertEqual(system.requests, 1)
        self.assertEqual(alarm.schedules, [])
        self.assertTrue(scheduled.timer_started)
        self.assertFalse(scheduled.system_alarm_scheduled)
        self.assertIn("permission is not granted", scheduled.errors[0])
        self.assertTrue(result.sound_played)
        self.assertEqual(notifier.audio.play_count, 1)

    async def test_cancel_paused_cycle_stops_timer_and_alarm_and_releases_claim(self):
        page = ThreadSafeFakePage(asyncio.get_running_loop())
        alarm = FakeAlarmScheduler()
        notifier = RestNotifier(
            page,
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            alarm_scheduler_factory=lambda: alarm,
        )

        scheduled = notifier.trigger_after("rest-paused", 0.2)
        canceled = notifier.cancel("rest-paused")
        await asyncio.sleep(0.25)

        self.assertTrue(scheduled.claimed)
        self.assertTrue(canceled.canceled)
        self.assertTrue(canceled.claim_released)
        self.assertFalse(canceled.timer_canceled)
        self.assertTrue(canceled.system_alarm_attempted)
        self.assertTrue(canceled.system_alarm_canceled)
        self.assertFalse(notifier.has_claimed("rest-paused"))
        self.assertEqual(page.tasks, [])
        self.assertEqual(notifier.audio.play_count, 0)
        self.assertEqual(
            alarm.cancels,
            [
                {
                    "cycle_id": "rest-paused",
                    "request_code": _stable_notification_id("rest-paused"),
                }
            ],
        )

    async def test_adjustment_can_cancel_and_reschedule_same_cycle(self):
        page = ThreadSafeFakePage(asyncio.get_running_loop())
        alarm = FakeAlarmScheduler()
        notifier = RestNotifier(
            page,
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            alarm_scheduler_factory=lambda: alarm,
        )

        old_schedule = notifier.trigger_after("rest-adjust", 0.2)
        canceled = notifier.cancel("rest-adjust")
        new_schedule = notifier.trigger_after("rest-adjust", 0)
        await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)

        self.assertTrue(old_schedule.claimed)
        self.assertTrue(canceled.claim_released)
        self.assertTrue(new_schedule.claimed)
        self.assertEqual(notifier.audio.play_count, 0)
        self.assertEqual(page.tasks, [])
        self.assertEqual(
            [schedule["delay_seconds"] for schedule in alarm.schedules],
            [0.2, 0.0],
        )
        self.assertEqual(
            alarm.cancels,
            [
                {
                    "cycle_id": "rest-adjust",
                    "request_code": _stable_notification_id("rest-adjust"),
                }
            ],
        )

    async def test_skip_cancel_keeps_claim_so_cycle_does_not_ring(self):
        page = ThreadSafeFakePage(asyncio.get_running_loop())
        alarm = FakeAlarmScheduler()
        notifier = RestNotifier(
            page,
            audio_factory=FakeAudio,
            haptic_factory=FakeHaptic,
            alarm_scheduler_factory=lambda: alarm,
        )

        notifier.trigger_after("rest-skip", 0.2)
        canceled = notifier.cancel("rest-skip", release_claim=False)
        duplicate = notifier.trigger_after("rest-skip", 0)
        await asyncio.sleep(0.25)

        self.assertTrue(canceled.canceled)
        self.assertFalse(canceled.claim_released)
        self.assertTrue(notifier.has_claimed("rest-skip"))
        self.assertFalse(duplicate.claimed)
        self.assertEqual(page.tasks, [])
        self.assertEqual(notifier.audio.play_count, 0)

    async def test_same_id_can_be_retriggered_after_cancel_releases_claim(self):
        page = ThreadSafeFakePage(asyncio.get_running_loop())
        notifier = RestNotifier(page, audio_factory=FakeAudio, haptic_factory=FakeHaptic)

        notifier.trigger_after("rest-repeat", 0.2)
        canceled = notifier.cancel("rest-repeat", release_claim=True)
        retriggered = notifier.trigger_after("rest-repeat", 0)
        await asyncio.sleep(0.05)
        result = await asyncio.wrap_future(page.tasks[0])

        self.assertTrue(canceled.claim_released)
        self.assertTrue(retriggered.claimed)
        self.assertTrue(result.claimed)
        self.assertEqual(notifier.audio.play_count, 1)

    def test_capability_statement_documents_flet_boundary(self):
        self.assertIn("Pyjnius", REST_NOTIFICATION_CAPABILITY)
        self.assertIn("BroadcastReceiver", REST_NOTIFICATION_CAPABILITY)
        self.assertIn("getBroadcast", REST_NOTIFICATION_CAPABILITY)
        self.assertIn("process", REST_NOTIFICATION_CAPABILITY)

    def test_alarm_action_is_namespaced_for_android_launch_intent(self):
        self.assertEqual(REST_ALARM_ACTION, "com.chenyang.carbs_king.REST_ALARM")
        self.assertEqual(
            REST_ALARM_RECEIVER_CLASS,
            "com.chenyang.carbs_king.restalarm.RestAlarmReceiver",
        )

    def test_native_receiver_is_part_of_repeatable_flet_build(self):
        root = Path(__file__).resolve().parents[1]
        project = (root / "pyproject.toml").read_text(encoding="utf-8")
        manifest = (
            root
            / "android/rest_alarm_plugin/android/src/main/AndroidManifest.xml"
        ).read_text(encoding="utf-8")
        receiver = (
            root
            / "android/rest_alarm_plugin/android/src/main/kotlin/com/chenyang/"
            "carbs_king/restalarm/RestAlarmReceiver.kt"
        ).read_text(encoding="utf-8")

        self.assertIn("carbs_king_rest_alarm", project)
        self.assertIn('path = "../../android/rest_alarm_plugin"', project)
        self.assertIn('"android.permission.POST_NOTIFICATIONS" = true', project)
        self.assertIn('"android.permission.USE_EXACT_ALARM" = true', project)
        self.assertIn('android:exported="false"', manifest)
        self.assertIn(REST_ALARM_ACTION, manifest)
        self.assertIn("class RestAlarmReceiver : BroadcastReceiver()", receiver)
        self.assertIn("setBypassDnd(false)", receiver)
        self.assertIn("setOnlyAlertOnce(true)", receiver)
        self.assertIn("getBoolean(cycleId, false)", receiver)
        self.assertIn('CHANNEL_ID = "rest_cycle_alerts_v2"', receiver)
        self.assertIn('android.resource://${context.packageName}/raw/rest_coin', receiver)
        native_sound = root / "android/rest_alarm_plugin/android/src/main/res/raw/rest_coin.mp3"
        foreground_sound = root / "src/assets/rest_coin.mp3"
        self.assertTrue(native_sound.is_file())
        self.assertTrue(foreground_sound.is_file())
        self.assertEqual(native_sound.read_bytes(), foreground_sound.read_bytes())
        self.assertEqual(len(native_sound.read_bytes()), 81546)
        self.assertEqual(
            hashlib.sha256(native_sound.read_bytes()).hexdigest().upper(),
            "8E943111B1F3AF5AC259EFD3B42148526505365273E97974AAC7A562CE354E5A",
        )


if __name__ == "__main__":
    unittest.main()

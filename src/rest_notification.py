"""Local and Android system-owned alerts for a completed rest cycle.

The rest-cycle service remains responsible for persisting whether a cycle was
notified. This adapter adds an in-process guard so repeated UI callbacks cannot
play the same alert more than once.

The bundled ``carbs_king_rest_alarm`` Flutter plugin contributes a native,
non-exported BroadcastReceiver to the Android manifest. This module therefore:

* posts Android system notifications while the app process is alive;
* schedules an explicit AlarmManager broadcast which remains valid after the
  Python/Flutter process has been reclaimed;
* fall back to Flet audio and haptics when native Android calls are unavailable;
* uses an in-process delayed timer only when native system scheduling fails.
"""

from __future__ import annotations

import inspect
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

import flet as ft
import flet_audio as fta


DEFAULT_BELL_ASSET = "assets/rest_coin.mp3"
DEFAULT_NOTIFICATION_CHANNEL_ID = "rest_cycle_alerts_v2"
DEFAULT_NOTIFICATION_CHANNEL_NAME = "Rest cycle alerts"
REST_ALARM_ACTION = "com.chenyang.carbs_king.REST_ALARM"
REST_ALARM_RECEIVER_CLASS = "com.chenyang.carbs_king.restalarm.RestAlarmReceiver"
REST_NOTIFICATION_CAPABILITY = (
    "Flet 0.85.3 supplies the Python runtime and Pyjnius foreground bridge. "
    "The local carbs_king_rest_alarm Flutter plugin merges a native, explicit "
    "BroadcastReceiver into AndroidManifest.xml. AlarmManager owns a "
    "PendingIntent.getBroadcast() and can invoke that receiver to post the "
    "rest notification while the app is backgrounded, locked, or its process "
    "has been reclaimed. Notification channels remain subject to Android "
    "notification permission, silent mode, channel settings, and Do Not Disturb."
)


@dataclass(frozen=True)
class RestNotificationResult:
    cycle_id: str
    claimed: bool
    system_notification_attempted: bool = False
    system_notification_succeeded: bool = False
    sound_played: bool = False
    vibration_attempted: bool = False
    vibration_succeeded: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScheduledRestNotification:
    cycle_id: str
    claimed: bool
    delay_seconds: float
    exact_after_process_death: bool = False
    system_alarm_attempted: bool = False
    system_alarm_scheduled: bool = False
    system_alarm_exact: bool = False
    process_death_notification_supported: bool = False
    timer_started: bool = False
    reason: str = ""
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanceledRestNotification:
    cycle_id: str
    canceled: bool
    claim_released: bool = False
    timer_canceled: bool = False
    system_alarm_attempted: bool = False
    system_alarm_canceled: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class AndroidAlarmScheduleResult:
    scheduled: bool
    exact: bool
    method: str
    process_death_notification_supported: bool = False
    reason: str = ""


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _is_android_runtime() -> bool:
    return bool(os.getenv("MAIN_ACTIVITY_HOST_CLASS_NAME"))


class AndroidSystemNotifier:
    """Post an Android notification through Pyjnius when running in an APK."""

    def __init__(
        self,
        *,
        channel_id: str = DEFAULT_NOTIFICATION_CHANNEL_ID,
        channel_name: str = DEFAULT_NOTIFICATION_CHANNEL_NAME,
    ) -> None:
        from jnius import autoclass  # type: ignore

        activity_host_class = os.getenv("MAIN_ACTIVITY_HOST_CLASS_NAME")
        if not activity_host_class:
            raise RuntimeError("MAIN_ACTIVITY_HOST_CLASS_NAME is unavailable")

        activity_host = autoclass(activity_host_class)
        self.activity = activity_host.mActivity
        if self.activity is None:
            raise RuntimeError("Android activity is unavailable")

        self.BuildVersion = autoclass("android.os.Build$VERSION")
        self.Context = autoclass("android.content.Context")
        self.PackageManager = autoclass("android.content.pm.PackageManager")
        self.NotificationManager = autoclass("android.app.NotificationManager")
        self.NotificationBuilder = autoclass("android.app.Notification$Builder")
        self.PendingIntent = autoclass("android.app.PendingIntent")
        self.Intent = autoclass("android.content.Intent")
        self.RingtoneManager = autoclass("android.media.RingtoneManager")
        self.AudioAttributes = autoclass("android.media.AudioAttributes$Builder")
        self.Uri = autoclass("android.net.Uri")
        self.channel_id = channel_id
        self.channel_name = channel_name
        self._ensure_channel()

    def _notification_service(self) -> Any:
        return self.activity.getSystemService(self.Context.NOTIFICATION_SERVICE)

    def _ensure_channel(self) -> None:
        if int(self.BuildVersion.SDK_INT) < 26:
            return
        NotificationChannel = __import__("jnius").autoclass(
            "android.app.NotificationChannel"
        )
        channel = NotificationChannel(
            self.channel_id,
            self.channel_name,
            self.NotificationManager.IMPORTANCE_DEFAULT,
        )
        sound_uri = self.Uri.parse(
            f"android.resource://{self.activity.getPackageName()}/raw/rest_coin"
        )
        audio_attributes = (
            self.AudioAttributes()
            .setUsage(5)  # AudioAttributes.USAGE_NOTIFICATION
            .setContentType(4)  # AudioAttributes.CONTENT_TYPE_SONIFICATION
            .build()
        )
        channel.enableVibration(True)
        channel.setSound(sound_uri, audio_attributes)
        channel.setBypassDnd(False)
        self._notification_service().createNotificationChannel(channel)

    def _has_post_permission(self) -> bool:
        if int(self.BuildVersion.SDK_INT) < 33:
            return True
        permission = "android.permission.POST_NOTIFICATIONS"
        return (
            self.activity.checkSelfPermission(permission)
            == self.PackageManager.PERMISSION_GRANTED
        )

    def has_post_permission(self) -> bool:
        return self._has_post_permission()

    def request_post_permission(self) -> None:
        if int(self.BuildVersion.SDK_INT) < 33 or self._has_post_permission():
            return
        from jnius import autoclass  # type: ignore

        String = autoclass("java.lang.String")
        permissions = [String("android.permission.POST_NOTIFICATIONS")]
        self.activity.requestPermissions(permissions, 21031)

    def post(self, *, notification_id: int, title: str, body: str) -> None:
        self.request_post_permission()
        if not self._has_post_permission():
            raise RuntimeError("android notification permission is not granted")

        launch_intent = self.activity.getPackageManager().getLaunchIntentForPackage(
            self.activity.getPackageName()
        )
        flags = self.PendingIntent.FLAG_UPDATE_CURRENT
        if int(self.BuildVersion.SDK_INT) >= 23:
            flags |= self.PendingIntent.FLAG_IMMUTABLE
        pending_intent = self.PendingIntent.getActivity(
            self.activity, notification_id, launch_intent, flags
        )

        if int(self.BuildVersion.SDK_INT) >= 26:
            builder = self.NotificationBuilder(self.activity, self.channel_id)
        else:
            builder = self.NotificationBuilder(self.activity)
            default_sound = self.RingtoneManager.getDefaultUri(
                self.RingtoneManager.TYPE_NOTIFICATION
            )
            builder.setSound(default_sound)

        icon_id = int(self.activity.getApplicationInfo().icon)
        builder.setSmallIcon(icon_id)
        builder.setContentTitle(title)
        builder.setContentText(body)
        builder.setContentIntent(pending_intent)
        builder.setAutoCancel(True)
        builder.setDefaults(3)  # DEFAULT_SOUND | DEFAULT_VIBRATE
        self._notification_service().notify(notification_id, builder.build())


class AndroidAlarmScheduler:
    """Schedule a system-owned alarm targeting the packaged native receiver."""

    def __init__(self) -> None:
        from jnius import autoclass  # type: ignore

        activity_host_class = os.getenv("MAIN_ACTIVITY_HOST_CLASS_NAME")
        if not activity_host_class:
            raise RuntimeError("MAIN_ACTIVITY_HOST_CLASS_NAME is unavailable")

        activity_host = autoclass(activity_host_class)
        self.activity = activity_host.mActivity
        if self.activity is None:
            raise RuntimeError("Android activity is unavailable")

        self.BuildVersion = autoclass("android.os.Build$VERSION")
        self.Context = autoclass("android.content.Context")
        self.AlarmManager = autoclass("android.app.AlarmManager")
        self.PendingIntent = autoclass("android.app.PendingIntent")
        self.Intent = autoclass("android.content.Intent")

    def _alarm_service(self) -> Any:
        return self.activity.getSystemService(self.Context.ALARM_SERVICE)

    def _intent(
        self,
        cycle_id: str,
        request_code: int,
        *,
        title: str = "",
        body: str = "",
    ) -> Any:
        intent = self.Intent(REST_ALARM_ACTION)
        intent.setClassName(self.activity.getPackageName(), REST_ALARM_RECEIVER_CLASS)
        intent.setPackage(self.activity.getPackageName())
        intent.putExtra("rest_cycle_id", cycle_id)
        intent.putExtra("rest_notification_id", int(request_code))
        intent.putExtra("rest_notification_title", title)
        intent.putExtra("rest_notification_body", body)
        return intent

    def _pending_intent(
        self,
        cycle_id: str,
        request_code: int,
        *,
        title: str,
        body: str,
    ) -> Any:
        intent = self._intent(cycle_id, request_code, title=title, body=body)
        flags = self.PendingIntent.FLAG_UPDATE_CURRENT
        if int(self.BuildVersion.SDK_INT) >= 23:
            flags |= self.PendingIntent.FLAG_IMMUTABLE
        return self.PendingIntent.getBroadcast(
            self.activity, request_code, intent, flags
        )

    def _pending_intent_for_cancel(self, cycle_id: str, request_code: int) -> Any | None:
        intent = self._intent(cycle_id, request_code)
        flags = self.PendingIntent.FLAG_NO_CREATE
        if int(self.BuildVersion.SDK_INT) >= 23:
            flags |= self.PendingIntent.FLAG_IMMUTABLE
        return self.PendingIntent.getBroadcast(
            self.activity, request_code, intent, flags
        )

    def _can_schedule_exact_alarm(self, alarm_manager: Any) -> bool:
        if int(self.BuildVersion.SDK_INT) < 31:
            return True
        return bool(alarm_manager.canScheduleExactAlarms())

    def schedule(
        self,
        *,
        cycle_id: str,
        delay_seconds: float,
        request_code: int,
        title: str,
        body: str,
    ) -> AndroidAlarmScheduleResult:
        alarm_manager = self._alarm_service()
        due_epoch_ms = int(time.time() * 1000) + int(max(0.0, delay_seconds) * 1000)
        pending_intent = self._pending_intent(
            cycle_id, request_code, title=title, body=body
        )
        sdk_int = int(self.BuildVersion.SDK_INT)
        alarm_type = self.AlarmManager.RTC_WAKEUP

        if self._can_schedule_exact_alarm(alarm_manager):
            if sdk_int >= 23:
                alarm_manager.setExactAndAllowWhileIdle(
                    alarm_type, due_epoch_ms, pending_intent
                )
                method = "setExactAndAllowWhileIdle(getBroadcast)"
            elif sdk_int >= 19:
                alarm_manager.setExact(alarm_type, due_epoch_ms, pending_intent)
                method = "setExact(getBroadcast)"
            else:
                alarm_manager.set(alarm_type, due_epoch_ms, pending_intent)
                method = "set(getBroadcast)"
            return AndroidAlarmScheduleResult(
                scheduled=True,
                exact=sdk_int >= 19,
                method=method,
                process_death_notification_supported=True,
                reason=(
                    "system alarm invokes the native notification receiver, "
                    "including after app process death"
                ),
            )

        if sdk_int >= 23:
            alarm_manager.setAndAllowWhileIdle(alarm_type, due_epoch_ms, pending_intent)
            return AndroidAlarmScheduleResult(
                scheduled=True,
                exact=False,
                method="setAndAllowWhileIdle(getBroadcast)",
                process_death_notification_supported=True,
                reason=(
                    "exact alarm access unavailable; native receiver notification "
                    "is scheduled but Android may defer delivery"
                ),
            )

        alarm_manager.set(alarm_type, due_epoch_ms, pending_intent)
        return AndroidAlarmScheduleResult(
            scheduled=True,
            exact=False,
            method="set(getBroadcast)",
            process_death_notification_supported=True,
            reason="legacy native receiver notification schedule",
        )

    def cancel(self, *, cycle_id: str, request_code: int) -> bool:
        pending_intent = self._pending_intent_for_cancel(cycle_id, request_code)
        if pending_intent is None:
            return False
        self._alarm_service().cancel(pending_intent)
        pending_intent.cancel()
        return True

    def mark_delivered(self, *, cycle_id: str) -> bool:
        preferences = self.activity.getSharedPreferences(
            "carbs_king_rest_alarm_deliveries", self.Context.MODE_PRIVATE
        )
        return bool(preferences.edit().putBoolean(str(cycle_id), True).commit())


def _default_system_notifier() -> Any | None:
    if not _is_android_runtime():
        return None
    return AndroidSystemNotifier()


def _default_alarm_scheduler() -> Any | None:
    if not _is_android_runtime():
        return None
    return AndroidAlarmScheduler()


def _stable_notification_id(cycle_id: str) -> int:
    value = 2166136261
    for char in cycle_id:
        value ^= ord(char)
        value = (value * 16777619) & 0x7FFFFFFF
    return value or 1


class RestNotifier:
    """Own Flet alert services and deliver each rest-cycle alert once."""

    def __init__(
        self,
        page: Any,
        *,
        bell_asset: str = DEFAULT_BELL_ASSET,
        audio_factory: Callable[..., Any] | None = fta.Audio,
        haptic_factory: Callable[..., Any] | None = ft.HapticFeedback,
        system_factory: Callable[[], Any | None] | None = _default_system_notifier,
        alarm_scheduler_factory: Callable[[], Any | None] | None = _default_alarm_scheduler,
        notification_title: str = "Rest finished",
        notification_body: str = "Start your next set.",
        notified_cycle_ids: Iterable[str] = (),
    ) -> None:
        self.page = page
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}
        self._schedule_tokens: dict[str, object] = {}
        self._foreground_delivered_ids: set[str] = set()
        self._notified_cycle_ids = {
            str(cycle_id).strip() for cycle_id in notified_cycle_ids if str(cycle_id).strip()
        }
        self._setup_errors: list[str] = []
        self.notification_title = notification_title
        self.notification_body = notification_body
        self.system_notifier = self._create_system_notifier(system_factory)
        self.alarm_scheduler = self._create_alarm_scheduler(alarm_scheduler_factory)
        self.audio = self._create_service(
            "audio", audio_factory, src=bell_asset, volume=1.0
        )
        self.haptic = self._create_service("haptic", haptic_factory)

    def _create_system_notifier(self, factory: Callable[[], Any | None] | None) -> Any | None:
        if factory is None:
            return None
        try:
            return factory()
        except Exception as exc:
            self._setup_errors.append(f"system notification setup: {exc}")
            return None

    def _create_alarm_scheduler(
        self, factory: Callable[[], Any | None] | None
    ) -> Any | None:
        if factory is None:
            return None
        try:
            return factory()
        except Exception as exc:
            self._setup_errors.append(f"system alarm setup: {exc}")
            return None

    def _create_service(
        self, name: str, factory: Callable[..., Any] | None, **kwargs: Any
    ) -> Any | None:
        if factory is None:
            return None
        try:
            service = factory(**kwargs)
            services = getattr(self.page, "services", None)
            if services is None:
                raise RuntimeError("page.services is unavailable")
            services.append(service)
            return service
        except Exception as exc:
            self._setup_errors.append(f"{name} setup: {exc}")
            return None

    def _claim(self, cycle_id: str) -> tuple[str, bool]:
        normalized = str(cycle_id or "").strip()
        if not normalized:
            return "", False
        with self._lock:
            if normalized in self._notified_cycle_ids:
                return normalized, False
            self._notified_cycle_ids.add(normalized)
            return normalized, True

    async def _deliver(self, cycle_id: str) -> RestNotificationResult:
        errors = list(self._setup_errors)
        system_notification_attempted = self.system_notifier is not None
        system_notification_succeeded = False
        sound_played = False
        vibration_attempted = self.system_notifier is not None or self.haptic is not None
        vibration_succeeded = False

        if self.system_notifier is not None:
            try:
                notification_id = _stable_notification_id(cycle_id)
                self.system_notifier.post(
                    notification_id=notification_id,
                    title=self.notification_title,
                    body=self.notification_body,
                )
                system_notification_succeeded = True
                sound_played = True
                vibration_succeeded = True
            except Exception as exc:
                errors.append(f"system notification: {exc}")

        if not system_notification_succeeded and self.audio is not None:
            try:
                await _await_if_needed(self.audio.play())
                sound_played = True
            except Exception as exc:
                errors.append(f"audio play: {exc}")

        if not system_notification_succeeded and self.haptic is not None:
            try:
                await _await_if_needed(self.haptic.vibrate())
                vibration_succeeded = True
            except Exception as exc:
                errors.append(f"haptic vibrate: {exc}")

        return RestNotificationResult(
            cycle_id=cycle_id,
            claimed=True,
            system_notification_attempted=system_notification_attempted,
            system_notification_succeeded=system_notification_succeeded,
            sound_played=sound_played,
            vibration_attempted=vibration_attempted,
            vibration_succeeded=vibration_succeeded,
            errors=tuple(errors),
        )

    async def _deliver_foreground(self, cycle_id: str) -> RestNotificationResult:
        """Play the bundled cue in the foreground without posting a notification."""
        errors = list(self._setup_errors)
        sound_played = False
        vibration_attempted = self.haptic is not None
        vibration_succeeded = False
        if self.audio is not None:
            try:
                await _await_if_needed(self.audio.play())
                sound_played = True
            except Exception as exc:
                errors.append(f"audio play: {exc}")
        if self.haptic is not None:
            try:
                await _await_if_needed(self.haptic.vibrate())
                vibration_succeeded = True
            except Exception as exc:
                errors.append(f"haptic vibrate: {exc}")
        return RestNotificationResult(
            cycle_id=cycle_id,
            claimed=True,
            sound_played=sound_played,
            vibration_attempted=vibration_attempted,
            vibration_succeeded=vibration_succeeded,
            errors=tuple(errors),
        )

    def trigger_foreground(self, cycle_id: str) -> Any | None:
        """Cancel the native alarm and play the local cue exactly once in-app."""
        normalized = str(cycle_id or "").strip()
        if not normalized:
            return None
        with self._lock:
            if normalized in self._foreground_delivered_ids:
                return None
            self._foreground_delivered_ids.add(normalized)
        marker = getattr(self.alarm_scheduler, "mark_delivered", None)
        if callable(marker):
            try:
                marker(cycle_id=normalized)
            except Exception:
                pass
        self.cancel(normalized, release_claim=False)
        try:
            return self.page.run_task(self._deliver_foreground, normalized)
        except Exception:
            with self._lock:
                self._foreground_delivered_ids.discard(normalized)
            return None

    async def notify_once(self, cycle_id: str) -> RestNotificationResult:
        normalized, claimed = self._claim(cycle_id)
        if not claimed:
            return RestNotificationResult(cycle_id=normalized, claimed=False)
        return await self._deliver(normalized)

    def trigger(self, cycle_id: str) -> Any | None:
        """Schedule an alert with ``Page.run_task`` and return its Future."""
        normalized, claimed = self._claim(cycle_id)
        if not claimed:
            return None
        try:
            return self.page.run_task(self._deliver, normalized)
        except Exception:
            # Scheduling failed before any alert was delivered, so a later UI
            # callback may retry the same cycle.
            with self._lock:
                self._notified_cycle_ids.discard(normalized)
            return None

    def trigger_after(self, cycle_id: str, delay_seconds: float) -> ScheduledRestNotification:
        """Schedule a rest alert.

        Android builds hand delivery to an AlarmManager broadcast received by
        native code. The Python timer remains the non-Android/failure fallback.
        """
        normalized, claimed = self._claim(cycle_id)
        delay = max(0.0, float(delay_seconds or 0.0))
        if not claimed:
            return ScheduledRestNotification(
                cycle_id=normalized,
                claimed=False,
                delay_seconds=delay,
                reason="cycle already claimed or empty",
            )

        errors: list[str] = []
        alarm_result: AndroidAlarmScheduleResult | None = None
        system_alarm_attempted = self.alarm_scheduler is not None
        notification_permission_ready = True
        request_permission = getattr(
            self.system_notifier, "request_post_permission", None
        )
        if callable(request_permission):
            try:
                request_permission()
            except Exception as exc:
                errors.append(f"notification permission request: {exc}")
        check_permission = getattr(self.system_notifier, "has_post_permission", None)
        if callable(check_permission):
            try:
                notification_permission_ready = bool(check_permission())
            except Exception as exc:
                notification_permission_ready = False
                errors.append(f"notification permission check: {exc}")
        if not notification_permission_ready:
            errors.append(
                "notification permission is not granted; using in-process fallback"
            )
        if self.alarm_scheduler is not None and notification_permission_ready:
            try:
                alarm_result = self.alarm_scheduler.schedule(
                    cycle_id=normalized,
                    delay_seconds=delay,
                    request_code=_stable_notification_id(normalized),
                    title=self.notification_title,
                    body=self.notification_body,
                )
            except Exception as exc:
                errors.append(f"system alarm: {exc}")

        native_owns_delivery = bool(
            alarm_result
            and alarm_result.scheduled
            and alarm_result.process_death_notification_supported
        )
        timer_started = False
        if not native_owns_delivery:
            token = object()

            def run() -> None:
                with self._lock:
                    if self._schedule_tokens.get(normalized) is not token:
                        return
                try:
                    self.page.run_task(self._deliver, normalized)
                finally:
                    with self._lock:
                        if self._schedule_tokens.get(normalized) is token:
                            self._timers.pop(normalized, None)
                            self._schedule_tokens.pop(normalized, None)

            timer = threading.Timer(delay, run)
            timer.daemon = True
            with self._lock:
                self._timers[normalized] = timer
                self._schedule_tokens[normalized] = token
            timer.start()
            timer_started = True
        return ScheduledRestNotification(
            cycle_id=normalized,
            claimed=True,
            delay_seconds=delay,
            exact_after_process_death=bool(alarm_result and alarm_result.exact),
            system_alarm_attempted=system_alarm_attempted,
            system_alarm_scheduled=bool(alarm_result and alarm_result.scheduled),
            system_alarm_exact=bool(alarm_result and alarm_result.exact),
            process_death_notification_supported=bool(
                alarm_result and alarm_result.process_death_notification_supported
            ),
            timer_started=timer_started,
            reason=self._scheduled_reason(alarm_result, errors),
            errors=tuple(errors),
        )

    def trigger_at(self, cycle_id: str, due_monotonic_seconds: float) -> ScheduledRestNotification:
        return self.trigger_after(cycle_id, due_monotonic_seconds - time.monotonic())

    def cancel(
        self, cycle_id: str, *, release_claim: bool = True
    ) -> CanceledRestNotification:
        normalized = str(cycle_id or "").strip()
        if not normalized:
            return CanceledRestNotification(cycle_id="", canceled=False)

        with self._lock:
            timer = self._timers.pop(normalized, None)
            self._schedule_tokens.pop(normalized, None)
            had_claim = normalized in self._notified_cycle_ids
            if release_claim:
                self._notified_cycle_ids.discard(normalized)

        timer_canceled = False
        if timer is not None:
            timer.cancel()
            timer_canceled = True

        errors: list[str] = []
        system_alarm_attempted = self.alarm_scheduler is not None
        system_alarm_canceled = False
        if self.alarm_scheduler is not None:
            try:
                system_alarm_canceled = bool(
                    self.alarm_scheduler.cancel(
                        cycle_id=normalized,
                        request_code=_stable_notification_id(normalized),
                    )
                )
            except Exception as exc:
                errors.append(f"system alarm cancel: {exc}")

        return CanceledRestNotification(
            cycle_id=normalized,
            canceled=timer_canceled or system_alarm_canceled or had_claim,
            claim_released=release_claim and had_claim,
            timer_canceled=timer_canceled,
            system_alarm_attempted=system_alarm_attempted,
            system_alarm_canceled=system_alarm_canceled,
            errors=tuple(errors),
        )

    def _scheduled_reason(
        self, alarm_result: AndroidAlarmScheduleResult | None, errors: list[str]
    ) -> str:
        parts: list[str] = []
        if alarm_result is not None and alarm_result.scheduled:
            parts.append(alarm_result.reason or alarm_result.method)
        elif self.alarm_scheduler is None:
            parts.append("system AlarmManager scheduler unavailable outside Android APK")
        if not (
            alarm_result
            and alarm_result.scheduled
            and alarm_result.process_death_notification_supported
        ):
            parts.append(
                "in-process timer posts the notification while the app process is alive"
            )
        if errors:
            parts.extend(errors)
        return "; ".join(parts)

    def has_claimed(self, cycle_id: str) -> bool:
        normalized = str(cycle_id or "").strip()
        with self._lock:
            return bool(normalized) and normalized in self._notified_cycle_ids

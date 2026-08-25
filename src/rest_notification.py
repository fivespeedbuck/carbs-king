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
DEFAULT_NOTIFICATION_CHANNEL_ID = "rest_cycle_alerts_v3"
DEFAULT_NOTIFICATION_CHANNEL_NAME = "组间休息提醒（高优先级）"
REST_ALARM_ACTION = "com.chenyang.carbs_king.REST_ALARM"
REST_ALARM_RECEIVER_CLASS = "com.chenyang.carbs_king.restalarm.RestAlarmReceiver"
REST_OVERLAY_SERVICE_CLASS = "com.chenyang.carbs_king.restalarm.RestOverlayService"
REST_OVERLAY_UPDATE_ACTION = "com.chenyang.carbs_king.REST_OVERLAY_UPDATE"
REST_OVERLAY_VISIBILITY_ACTION = "com.chenyang.carbs_king.REST_OVERLAY_VISIBILITY"
REST_OVERLAY_STOP_ACTION = "com.chenyang.carbs_king.REST_OVERLAY_STOP"
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
    overlay_service_started: bool = False
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
    overlay_service_stopped: bool = False
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
        self.JavaString = autoclass("java.lang.String")
        self.Settings = autoclass("android.provider.Settings")
        self.Uri = autoclass("android.net.Uri")
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
        manager = self._notification_service()
        channel = NotificationChannel(
            self.channel_id,
            self.channel_name,
            self.NotificationManager.IMPORTANCE_HIGH,
        )
        resource_id = int(
            self.activity.getResources().getIdentifier(
                "rest_coin", "raw", self.activity.getPackageName()
            )
        )
        if resource_id <= 0:
            raise RuntimeError("native rest_coin sound resource is unavailable")
        sound_uri = self.Uri.parse(
            f"android.resource://{self.activity.getPackageName()}/{resource_id}"
        )
        audio_attributes = (
            self.AudioAttributes()
            .setUsage(4)  # AudioAttributes.USAGE_ALARM
            .setContentType(4)  # AudioAttributes.CONTENT_TYPE_SONIFICATION
            .build()
        )
        channel.enableVibration(True)
        channel.setSound(sound_uri, audio_attributes)
        channel.setBypassDnd(False)
        manager.createNotificationChannel(channel)

    def _has_post_permission(self) -> bool:
        sdk_int = int(self.BuildVersion.SDK_INT)
        if sdk_int >= 33:
            permission = "android.permission.POST_NOTIFICATIONS"
            if (
                self.activity.checkSelfPermission(permission)
                != self.PackageManager.PERMISSION_GRANTED
            ):
                return False
        manager = self._notification_service()
        if sdk_int >= 24 and not bool(manager.areNotificationsEnabled()):
            return False
        if sdk_int >= 26:
            channel = manager.getNotificationChannel(self.channel_id)
            if channel is None:
                return False
            if int(channel.getImportance()) == int(self.NotificationManager.IMPORTANCE_NONE):
                return False
            if channel.getSound() is None:
                return False
        return True

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
        self.JavaString = autoclass("java.lang.String")
        self.Settings = autoclass("android.provider.Settings")
        self.Uri = autoclass("android.net.Uri")

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
        intent.putExtra("rest_cycle_id", self.JavaString(str(cycle_id)))
        intent.putExtra("rest_notification_id", int(request_code))
        intent.putExtra("rest_notification_title", self.JavaString(str(title)))
        intent.putExtra("rest_notification_body", self.JavaString(str(body)))
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

    def has_exact_alarm_access(self) -> bool:
        return self._can_schedule_exact_alarm(self._alarm_service())

    def request_exact_alarm_access(self) -> bool:
        if self.has_exact_alarm_access() or int(self.BuildVersion.SDK_INT) < 31:
            return True
        intent = self.Intent(
            self.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
            self.Uri.parse(f"package:{self.activity.getPackageName()}"),
        )
        self.activity.startActivity(intent)
        return False

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

    def has_delivered(self, *, cycle_id: str) -> bool:
        preferences = self.activity.getSharedPreferences(
            "carbs_king_rest_alarm_deliveries", self.Context.MODE_PRIVATE
        )
        return bool(preferences.getBoolean(str(cycle_id), False))


class AndroidRestOverlayController:
    """Drive the native foreground countdown and optional overlay."""

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
        self.Intent = autoclass("android.content.Intent")
        self.Settings = autoclass("android.provider.Settings")
        self.Uri = autoclass("android.net.Uri")
        self.JavaString = autoclass("java.lang.String")
        self._active_cycle_id = ""
        self._app_visible = True
        self._permission_requested = False

    def has_permission(self) -> bool:
        return int(self.BuildVersion.SDK_INT) < 23 or bool(
            self.Settings.canDrawOverlays(self.activity)
        )

    def request_permission(self) -> bool:
        if self.has_permission() or self._permission_requested:
            return self.has_permission()
        self._permission_requested = True
        intent = self.Intent(
            self.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            self.Uri.parse(f"package:{self.activity.getPackageName()}"),
        )
        self.activity.startActivity(intent)
        return False

    def _service_intent(self, action: str) -> Any:
        intent = self.Intent(action)
        intent.setClassName(self.activity.getPackageName(), REST_OVERLAY_SERVICE_CLASS)
        intent.setPackage(self.activity.getPackageName())
        return intent

    def _start(self, intent: Any) -> None:
        if int(self.BuildVersion.SDK_INT) >= 26:
            self.activity.startForegroundService(intent)
        else:
            self.activity.startService(intent)

    def start(
        self,
        *,
        cycle_id: str,
        delay_seconds: float,
        next_action: str = "",
        theme_color: str = "",
    ) -> bool:
        normalized = str(cycle_id or "").strip()
        if not normalized:
            return False
        self._active_cycle_id = normalized
        intent = self._service_intent(REST_OVERLAY_UPDATE_ACTION)
        intent.putExtra("rest_cycle_id", self.JavaString(normalized))
        intent.putExtra(
            "rest_ends_at_epoch_ms",
            int(time.time() * 1000) + int(max(0.0, delay_seconds) * 1000),
        )
        intent.putExtra("rest_next_action", self.JavaString(str(next_action or "")))
        intent.putExtra("rest_theme_color", self.JavaString(str(theme_color or "")))
        intent.putExtra("rest_app_visible", bool(self._app_visible))
        self._start(intent)
        return True

    def set_app_visible(self, visible: bool) -> None:
        self._app_visible = bool(visible)
        if not self._active_cycle_id:
            return
        intent = self._service_intent(REST_OVERLAY_VISIBILITY_ACTION)
        intent.putExtra("rest_app_visible", self._app_visible)
        # Visibility only updates an already-running foreground service.
        self.activity.startService(intent)

    def stop(self, *, cycle_id: str = "") -> bool:
        normalized = str(cycle_id or "").strip()
        if normalized and normalized != self._active_cycle_id:
            return False
        if not self._active_cycle_id:
            return False
        intent = self._service_intent(REST_OVERLAY_STOP_ACTION)
        self.activity.startService(intent)
        self._active_cycle_id = ""
        return True


def _default_system_notifier() -> Any | None:
    if not _is_android_runtime():
        return None
    return AndroidSystemNotifier()


def _default_alarm_scheduler() -> Any | None:
    if not _is_android_runtime():
        return None
    return AndroidAlarmScheduler()


def _default_overlay_controller() -> Any | None:
    if not _is_android_runtime():
        return None
    return AndroidRestOverlayController()


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
        overlay_controller_factory: Callable[[], Any | None] | None = _default_overlay_controller,
        notification_title: str = "Rest finished",
        notification_body: str = "Start your next set.",
        notified_cycle_ids: Iterable[str] = (),
    ) -> None:
        self.page = page
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}
        self._schedule_tokens: dict[str, object] = {}
        self._native_owned_cycle_ids: set[str] = set()
        self._foreground_delivered_ids: set[str] = set()
        # The native alarm remains the fallback for background and lock-screen
        # delivery.  When Flet is visibly in front, however, the bundled
        # player is the reliable, immediately testable path and must not be
        # suppressed merely because an AlarmManager request was accepted.
        self._app_is_foreground = True
        self._notified_cycle_ids = {
            str(cycle_id).strip() for cycle_id in notified_cycle_ids if str(cycle_id).strip()
        }
        self._setup_errors: list[str] = []
        self.notification_title = notification_title
        self.notification_body = notification_body
        self.system_notifier = self._create_system_notifier(system_factory)
        self.alarm_scheduler = self._create_alarm_scheduler(alarm_scheduler_factory)
        self.overlay_controller = self._create_overlay_controller(overlay_controller_factory)
        self._request_notification_permission_early()
        self.audio = self._create_service(
            "audio", audio_factory, src=bell_asset, volume=1.0
        )
        self.haptic = self._create_service("haptic", haptic_factory)
        self._observe_lifecycle()

    def _observe_lifecycle(self) -> None:
        """Keep foreground delivery scoped to a visible, interactive app."""
        try:
            previous_handler = getattr(self.page, "on_app_lifecycle_state_change", None)

            def on_lifecycle(event: Any) -> None:
                raw_state = getattr(event, "state", "")
                # Flet supplies an AppLifecycleState enum on Android. ``str``
                # of that enum is ``AppLifecycleState.RESTART`` rather than
                # ``restart``; use its transport value so returning from the
                # background re-enables later foreground rest sounds.
                state = str(getattr(raw_state, "value", raw_state)).casefold()
                with self._lock:
                    self._app_is_foreground = state in {"show", "resume", "restart"}
                    is_foreground = self._app_is_foreground
                set_visible = getattr(self.overlay_controller, "set_app_visible", None)
                if callable(set_visible):
                    try:
                        set_visible(is_foreground)
                    except Exception as exc:
                        self._setup_errors.append(f"overlay lifecycle: {exc}")
                if callable(previous_handler):
                    previous_handler(event)

            self.page.on_app_lifecycle_state_change = on_lifecycle
        except Exception as exc:
            self._setup_errors.append(f"app lifecycle setup: {exc}")

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

    def _create_overlay_controller(
        self, factory: Callable[[], Any | None] | None
    ) -> Any | None:
        if factory is None:
            return None
        try:
            return factory()
        except Exception as exc:
            self._setup_errors.append(f"overlay service setup: {exc}")
            return None

    def _request_notification_permission_early(self) -> None:
        request_permission = getattr(
            self.system_notifier, "request_post_permission", None
        )
        if not callable(request_permission):
            return
        try:
            request_permission()
        except Exception as exc:
            self._setup_errors.append(f"notification permission request: {exc}")

    def background_permission_status(self) -> dict[str, bool]:
        def checked(target: Any, method_name: str, default: bool = False) -> bool:
            method = getattr(target, method_name, None)
            if not callable(method):
                return default
            try:
                return bool(method())
            except Exception:
                return False

        android = _is_android_runtime()
        return {
            "android": android,
            "notification": checked(
                self.system_notifier, "has_post_permission", default=not android
            ),
            "exact_alarm": checked(
                self.alarm_scheduler, "has_exact_alarm_access", default=not android
            ),
            "overlay": checked(
                self.overlay_controller, "has_permission", default=not android
            ),
        }

    def request_notification_permission(self) -> bool:
        request = getattr(self.system_notifier, "request_post_permission", None)
        if not callable(request):
            return not _is_android_runtime()
        request()
        return self.background_permission_status()["notification"]

    def request_exact_alarm_permission(self) -> bool:
        request = getattr(self.alarm_scheduler, "request_exact_alarm_access", None)
        if not callable(request):
            return not _is_android_runtime()
        return bool(request())

    def request_overlay_permission(self) -> bool:
        request = getattr(self.overlay_controller, "request_permission", None)
        if not callable(request):
            return not _is_android_runtime()
        return bool(request())

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
        """Play the foreground cue, falling back to a system notification."""
        errors = list(self._setup_errors)
        sound_played = False
        system_notification_attempted = False
        system_notification_succeeded = False
        vibration_attempted = self.haptic is not None
        vibration_succeeded = False

        # AlarmManager and the visible Flet callback can become due on the
        # same frame. Share the native delivery marker before starting the
        # foreground player so the native receiver drops its pending copy.
        # If the native receiver won the race, treat that delivery as already
        # satisfied and do not play the cue a second time.
        native_owned = False
        with self._lock:
            native_owned = cycle_id in self._native_owned_cycle_ids
        if native_owned and self.alarm_scheduler is not None:
            has_delivered = getattr(self.alarm_scheduler, "has_delivered", None)
            mark_delivered = getattr(self.alarm_scheduler, "mark_delivered", None)
            try:
                if callable(has_delivered) and bool(has_delivered(cycle_id=cycle_id)):
                    return RestNotificationResult(
                        cycle_id=cycle_id,
                        claimed=True,
                        sound_played=True,
                        vibration_attempted=False,
                        vibration_succeeded=False,
                        errors=tuple(errors),
                    )
                if callable(mark_delivered) and not bool(mark_delivered(cycle_id=cycle_id)):
                    errors.append("native delivery marker could not be committed")
            except Exception as exc:
                # Foreground playback remains the safe fallback if the marker
                # bridge is unavailable on a particular Android runtime.
                errors.append(f"native delivery marker: {exc}")

        if self.audio is not None:
            try:
                try:
                    await _await_if_needed(self.audio.play(0))
                except TypeError:
                    await _await_if_needed(self.audio.play())
                sound_played = True
            except Exception as exc:
                errors.append(f"audio play: {exc}")
        if not sound_played and self.system_notifier is not None:
            system_notification_attempted = True
            try:
                self.system_notifier.post(
                    notification_id=_stable_notification_id(cycle_id),
                    title=self.notification_title,
                    body=self.notification_body,
                )
                system_notification_succeeded = True
                sound_played = True
            except Exception as exc:
                errors.append(f"foreground system notification: {exc}")
        if self.haptic is not None:
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

    async def _deliver_foreground_and_finalize(self, cycle_id: str) -> RestNotificationResult:
        """Deliver the visible-app cue once, then remove a duplicate alarm."""
        result = await self._deliver_foreground(cycle_id)
        if result.sound_played or result.system_notification_succeeded:
            self.cancel(cycle_id, release_claim=False)
        else:
            with self._lock:
                self._foreground_delivered_ids.discard(cycle_id)
        return result

    def trigger_foreground(self, cycle_id: str) -> Any | None:
        """Play the in-app cue when the app is currently visible.

        This intentionally runs even after a native alarm was scheduled.  A
        scheduled alarm only proves Android accepted a PendingIntent; it does
        not prove a foreground user heard it.  Once the local player starts,
        canceling the still-pending alarm prevents a second cue.
        """
        normalized = str(cycle_id or "").strip()
        if not normalized:
            return None
        with self._lock:
            if not self._app_is_foreground:
                return None
            if normalized in self._foreground_delivered_ids:
                return None
            self._foreground_delivered_ids.add(normalized)
        try:
            return self.page.run_task(self._deliver_foreground_and_finalize, normalized)
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

    def trigger_after(
        self,
        cycle_id: str,
        delay_seconds: float,
        *,
        next_action: str = "",
        theme_color: str = "",
    ) -> ScheduledRestNotification:
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
        notification_permission_ready = not (
            _is_android_runtime() and self.system_notifier is None
        )
        if not notification_permission_ready:
            errors.append(
                "Android notification channel is unavailable; native alarm audio remains scheduled"
            )
        check_permission = getattr(self.system_notifier, "has_post_permission", None)
        if callable(check_permission):
            try:
                notification_permission_ready = bool(check_permission())
            except Exception as exc:
                notification_permission_ready = False
                errors.append(f"notification permission check: {exc}")
        if not notification_permission_ready:
            errors.append(
                "notification permission is not granted; native alarm audio remains scheduled"
            )
        # Native alarm audio does not require notification permission. Always
        # hand the due time to AlarmManager when its receiver is available.
        if self.alarm_scheduler is not None:
            try:
                alarm_result = self.alarm_scheduler.schedule(
                    cycle_id=normalized,
                    delay_seconds=delay,
                    request_code=_stable_notification_id(normalized),
                    title=self.notification_title,
                    body=str(next_action or self.notification_body),
                )
            except Exception as exc:
                errors.append(f"system alarm: {exc}")

        native_owns_delivery = bool(
            alarm_result
            and alarm_result.scheduled
            and alarm_result.process_death_notification_supported
        )
        with self._lock:
            if native_owns_delivery:
                self._native_owned_cycle_ids.add(normalized)
            else:
                self._native_owned_cycle_ids.discard(normalized)
        overlay_service_started = False
        if self.overlay_controller is not None:
            try:
                overlay_service_started = bool(
                    self.overlay_controller.start(
                        cycle_id=normalized,
                        delay_seconds=delay,
                        next_action=str(next_action or ""),
                        theme_color=str(theme_color or ""),
                    )
                )
            except Exception as exc:
                errors.append(f"overlay service: {exc}")
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
            overlay_service_started=overlay_service_started,
            reason=self._scheduled_reason(alarm_result, errors),
            errors=tuple(errors),
        )

    def trigger_at(self, cycle_id: str, due_monotonic_seconds: float) -> ScheduledRestNotification:
        return self.trigger_after(cycle_id, due_monotonic_seconds - time.monotonic())

    def cancel(
        self,
        cycle_id: str,
        *,
        release_claim: bool = True,
        stop_overlay: bool = True,
    ) -> CanceledRestNotification:
        normalized = str(cycle_id or "").strip()
        if not normalized:
            return CanceledRestNotification(cycle_id="", canceled=False)

        with self._lock:
            timer = self._timers.pop(normalized, None)
            self._schedule_tokens.pop(normalized, None)
            self._native_owned_cycle_ids.discard(normalized)
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
        overlay_service_stopped = False
        if stop_overlay and self.overlay_controller is not None:
            try:
                overlay_service_stopped = bool(
                    self.overlay_controller.stop(cycle_id=normalized)
                )
            except Exception as exc:
                errors.append(f"overlay service stop: {exc}")

        return CanceledRestNotification(
            cycle_id=normalized,
            canceled=(
                timer_canceled
                or system_alarm_canceled
                or overlay_service_stopped
                or had_claim
            ),
            claim_released=release_claim and had_claim,
            timer_canceled=timer_canceled,
            system_alarm_attempted=system_alarm_attempted,
            system_alarm_canceled=system_alarm_canceled,
            overlay_service_stopped=overlay_service_stopped,
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

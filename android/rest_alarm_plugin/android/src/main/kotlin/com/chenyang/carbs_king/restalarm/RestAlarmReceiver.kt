package com.chenyang.carbs_king.restalarm

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Build
import android.os.PowerManager

class RestAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_REST_ALARM) return

        val cycleId = intent.textExtra(EXTRA_CYCLE_ID).trim()
        if (cycleId.isEmpty()) return

        synchronized(deliveryLock) {
            val deliveries = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            if (deliveries.getBoolean(cycleId, false)) return

            // The app process might be paused or reclaimed, so playback must
            // happen in the native receiver rather than depend on Flet's
            // background lifecycle. USAGE_ALARM follows the alarm stream.
            context.stopService(Intent(context, RestOverlayService::class.java))
            val pendingResult = goAsync()
            val audioStarted = playBundledAlarm(context) { pendingResult.finish() }
            var notificationPosted = false
            // Direct native playback owns the sound. The notification channel
            // is deliberately silent so lock-screen visibility and vibration
            // do not create a second ringtone.
            if (canPostNotifications(context)) {
                val notificationId = intent.getIntExtra(EXTRA_NOTIFICATION_ID, 1).coerceAtLeast(1)
                val title = intent.textExtra(EXTRA_TITLE).ifBlank { DEFAULT_TITLE }
                val body = intent.textExtra(EXTRA_BODY).ifBlank { DEFAULT_BODY }
                val manager = context.getSystemService(NotificationManager::class.java)
                ensureChannel(context, manager)

                val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)
                val contentIntent = launchIntent?.let {
                    PendingIntent.getActivity(
                        context,
                        notificationId,
                        it,
                        PendingIntent.FLAG_UPDATE_CURRENT or immutableFlag(),
                    )
                }

                val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    Notification.Builder(context, CHANNEL_ID)
                } else {
                    @Suppress("DEPRECATION")
                    Notification.Builder(context)
                }

                builder
                    .setSmallIcon(context.applicationInfo.icon)
                    .setContentTitle(title)
                    .setContentText(body)
                    .setCategory(Notification.CATEGORY_ALARM)
                    .setVisibility(Notification.VISIBILITY_PUBLIC)
                    .setAutoCancel(true)
                    .setOnlyAlertOnce(true)
                    .setTimeoutAfter(60_000)
                contentIntent?.let(builder::setContentIntent)

                manager.notify(notificationId, builder.build())
                notificationPosted = true
            }
            // Only suppress redelivery after at least one native delivery path
            // has been started; notification permission is not a prerequisite
            // for the bundled alarm audio.
            if (audioStarted || notificationPosted) {
                deliveries.edit().putBoolean(cycleId, true).commit()
            }
            if (!audioStarted) pendingResult.finish()
        }
    }

    private fun playBundledAlarm(context: Context, onFinished: () -> Unit): Boolean {
        val player = MediaPlayer()
        val powerManager = context.getSystemService(PowerManager::class.java)
        val wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "${context.packageName}:rest-alarm",
        )
        try {
            wakeLock.acquire(15_000)
            player.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            )
            val source = context.resources.openRawResourceFd(R.raw.rest_coin) ?: run {
                player.release()
                return false
            }
            source.use {
                player.setDataSource(it.fileDescriptor, it.startOffset, it.length)
            }
            player.setOnCompletionListener { completed ->
                releasePlayer(completed, wakeLock)
                onFinished()
            }
            player.setOnErrorListener { failed, _, _ ->
                releasePlayer(failed, wakeLock)
                onFinished()
                true
            }
            synchronized(deliveryLock) { activePlayers.add(player) }
            player.prepare()
            player.start()
            return true
        } catch (_: Exception) {
            synchronized(deliveryLock) { activePlayers.remove(player) }
            player.release()
            if (wakeLock.isHeld) wakeLock.release()
            return false
        }
    }

    private fun releasePlayer(player: MediaPlayer, wakeLock: PowerManager.WakeLock) {
        synchronized(deliveryLock) { activePlayers.remove(player) }
        player.release()
        if (wakeLock.isHeld) wakeLock.release()
    }

    private fun canPostNotifications(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun Intent.textExtra(key: String): String =
        when (val value = extras?.get(key)) {
            is String -> value
            is CharArray -> String(value)
            else -> value?.toString().orEmpty()
        }

    private fun ensureChannel(context: Context, manager: NotificationManager) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            CHANNEL_NAME,
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "组间休息结束提醒"
            enableVibration(true)
            setSound(null, null)
            setBypassDnd(false)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        manager.createNotificationChannel(channel)
    }

    private fun immutableFlag(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0

    companion object {
        private const val ACTION_REST_ALARM = "com.chenyang.carbs_king.REST_ALARM"
        private const val EXTRA_CYCLE_ID = "rest_cycle_id"
        private const val EXTRA_NOTIFICATION_ID = "rest_notification_id"
        private const val EXTRA_TITLE = "rest_notification_title"
        private const val EXTRA_BODY = "rest_notification_body"
        private const val PREFS_NAME = "carbs_king_rest_alarm_deliveries"
        // This native-only channel stays silent because the receiver owns playback.
        private const val CHANNEL_ID = "rest_cycle_native_alerts_v1"
        private const val CHANNEL_NAME = "组间休息提醒（高优先级）"
        private const val DEFAULT_TITLE = "组间休息结束"
        private const val DEFAULT_BODY = "下一组可以开始了"
        private val deliveryLock = Any()
        private val activePlayers = mutableSetOf<MediaPlayer>()
    }
}

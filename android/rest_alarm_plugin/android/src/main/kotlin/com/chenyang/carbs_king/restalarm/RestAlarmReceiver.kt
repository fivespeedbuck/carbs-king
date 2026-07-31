package com.chenyang.carbs_king.restalarm

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.ContentResolver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.net.Uri
import android.os.Build

class RestAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_REST_ALARM) return

        val cycleId = intent.getStringExtra(EXTRA_CYCLE_ID)?.trim().orEmpty()
        if (cycleId.isEmpty()) return

        synchronized(deliveryLock) {
            val deliveries = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            if (deliveries.getBoolean(cycleId, false)) return

            // The app process might be paused or reclaimed, so playback must
            // happen in the native receiver rather than depend on Flet's
            // background lifecycle. USAGE_ALARM follows the alarm stream.
            val audioStarted = playBundledAlarm(context)
            var notificationPosted = false
            // A v3 channel may already own a sound selected by Android. Do not
            // post through it after native playback starts, otherwise one rest
            // can ring twice. The channel remains the audible fallback only
            // when direct bundled playback could not start.
            if (!audioStarted && canPostNotifications(context)) {
                val notificationId = intent.getIntExtra(EXTRA_NOTIFICATION_ID, 1).coerceAtLeast(1)
                val title = intent.getStringExtra(EXTRA_TITLE).orEmpty().ifBlank { DEFAULT_TITLE }
                val body = intent.getStringExtra(EXTRA_BODY).orEmpty().ifBlank { DEFAULT_BODY }
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
        }
    }

    private fun playBundledAlarm(context: Context): Boolean {
        val player = MediaPlayer()
        try {
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
            player.setOnCompletionListener(::releasePlayer)
            player.setOnErrorListener { failed, _, _ ->
                releasePlayer(failed)
                true
            }
            synchronized(deliveryLock) { activePlayers.add(player) }
            player.prepare()
            player.start()
            return true
        } catch (_: Exception) {
            synchronized(deliveryLock) { activePlayers.remove(player) }
            player.release()
            return false
        }
    }

    private fun releasePlayer(player: MediaPlayer) {
        synchronized(deliveryLock) { activePlayers.remove(player) }
        player.release()
    }

    private fun canPostNotifications(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun ensureChannel(context: Context, manager: NotificationManager) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val sound = Uri.Builder()
            .scheme(ContentResolver.SCHEME_ANDROID_RESOURCE)
            .authority(context.packageName)
            .appendPath(R.raw.rest_coin.toString())
            .build()
        val audioAttributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ALARM)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()
        val channel = NotificationChannel(
            CHANNEL_ID,
            CHANNEL_NAME,
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "组间休息结束提醒"
            enableVibration(true)
            setSound(sound, audioAttributes)
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
        // Android 8+ channel sound is immutable after creation; Build 78 uses a new ID.
        private const val CHANNEL_ID = "rest_cycle_alerts_v3"
        private const val CHANNEL_NAME = "组间休息提醒（高优先级）"
        private const val DEFAULT_TITLE = "组间休息结束"
        private const val DEFAULT_BODY = "下一组可以开始了"
        private val deliveryLock = Any()
        private val activePlayers = mutableSetOf<MediaPlayer>()
    }
}

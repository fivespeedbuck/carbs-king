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
import android.media.RingtoneManager
import android.os.Build

class RestAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_REST_ALARM) return

        val cycleId = intent.getStringExtra(EXTRA_CYCLE_ID)?.trim().orEmpty()
        if (cycleId.isEmpty() || !canPostNotifications(context)) return

        synchronized(deliveryLock) {
            val deliveries = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            if (deliveries.getBoolean(cycleId, false)) return

            val notificationId = intent.getIntExtra(EXTRA_NOTIFICATION_ID, 1).coerceAtLeast(1)
            val title = intent.getStringExtra(EXTRA_TITLE).orEmpty().ifBlank { DEFAULT_TITLE }
            val body = intent.getStringExtra(EXTRA_BODY).orEmpty().ifBlank { DEFAULT_BODY }
            val manager = context.getSystemService(NotificationManager::class.java)
            ensureChannel(manager)

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
                    .setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION))
                    .setDefaults(Notification.DEFAULT_SOUND or Notification.DEFAULT_VIBRATE)
            }

            builder
                .setSmallIcon(context.applicationInfo.icon)
                .setContentTitle(title)
                .setContentText(body)
                .setCategory(Notification.CATEGORY_REMINDER)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setAutoCancel(true)
                .setOnlyAlertOnce(true)
            contentIntent?.let(builder::setContentIntent)

            // Commit before notify so redelivery of the same broadcast cannot ring twice.
            if (!deliveries.edit().putBoolean(cycleId, true).commit()) return
            manager.notify(notificationId, builder.build())
        }
    }

    private fun canPostNotifications(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun ensureChannel(manager: NotificationManager) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        val audioAttributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()
        val channel = NotificationChannel(
            CHANNEL_ID,
            CHANNEL_NAME,
            NotificationManager.IMPORTANCE_DEFAULT,
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
        private const val CHANNEL_ID = "rest_cycle_alerts"
        private const val CHANNEL_NAME = "Rest cycle alerts"
        private const val DEFAULT_TITLE = "组间休息结束"
        private const val DEFAULT_BODY = "下一组可以开始了"
        private val deliveryLock = Any()
    }
}

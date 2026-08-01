package com.chenyang.carbs_king.restalarm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.text.TextUtils
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.abs
import kotlin.math.max

class RestOverlayService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private var endsAtEpochMs = 0L
    private var appVisible = true
    private var cycleId = ""
    private var nextAction = ""
    private var themeColor = DEFAULT_THEME_COLOR
    private var overlay: View? = null
    private var countdown: TextView? = null
    private var detail: TextView? = null
    private var layoutParams: WindowManager.LayoutParams? = null
    private var lastNotificationSeconds = -1

    private val tick = object : Runnable {
        override fun run() {
            val remaining = remainingSeconds()
            if (remaining <= 0) {
                stopSelf()
                return
            }
            countdown?.text = formatRemaining(remaining)
            if (lastNotificationSeconds < 0 || abs(lastNotificationSeconds - remaining) >= 5) {
                refreshNotification(remaining)
                lastNotificationSeconds = remaining
            }
            syncOverlay()
            handler.postDelayed(this, 1_000)
        }
    }

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_VISIBILITY -> {
                appVisible = intent.getBooleanExtra(EXTRA_APP_VISIBLE, true)
                if (cycleId.isEmpty() || remainingSeconds() <= 0) {
                    stopSelf()
                    return START_NOT_STICKY
                }
                syncOverlay()
                return START_NOT_STICKY
            }
            ACTION_UPDATE -> {
                cycleId = intent.textExtra(EXTRA_CYCLE_ID).trim()
                endsAtEpochMs = intent.getLongExtra(EXTRA_ENDS_AT_EPOCH_MS, 0L)
                appVisible = intent.getBooleanExtra(EXTRA_APP_VISIBLE, true)
                nextAction = intent.textExtra(EXTRA_NEXT_ACTION).trim()
                themeColor = intent.textExtra(EXTRA_THEME_COLOR).trim().ifEmpty {
                    DEFAULT_THEME_COLOR
                }
                overlay?.setBackgroundColor(parseThemeColor(themeColor))
                detail?.text = nextAction.ifEmpty { "下一个：准备下一组" }
            }
        }
        if (cycleId.isEmpty() || remainingSeconds() <= 0) {
            stopSelf()
            return START_NOT_STICKY
        }
        val remaining = remainingSeconds()
        startForeground(NOTIFICATION_ID, buildNotification(remaining))
        lastNotificationSeconds = remaining
        handler.removeCallbacks(tick)
        handler.post(tick)
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        handler.removeCallbacks(tick)
        removeOverlay()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun Intent.textExtra(key: String): String =
        when (val value = extras?.get(key)) {
            is String -> value
            is CharArray -> String(value)
            else -> value?.toString().orEmpty()
        }

    private fun remainingSeconds(): Int =
        max(0, ((endsAtEpochMs - System.currentTimeMillis() + 999) / 1_000).toInt())

    private fun formatRemaining(seconds: Int): String =
        "休息 %02d:%02d".format(seconds / 60, seconds % 60)

    private fun syncOverlay() {
        val allowed = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this)
        if (appVisible || !allowed || remainingSeconds() <= 0) {
            removeOverlay()
        } else if (overlay == null) {
            addOverlay()
        }
    }

    private fun addOverlay() {
        val windowManager = getSystemService(WindowManager::class.java)
        val text = TextView(this).apply {
            setTextColor(Color.WHITE)
            textSize = 18f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            text = formatRemaining(remainingSeconds())
        }
        val detailText = TextView(this).apply {
            setTextColor(Color.argb(225, 255, 255, 255))
            textSize = 13f
            gravity = Gravity.CENTER
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
            this.text = nextAction.ifEmpty { "下一个：准备下一组" }
        }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(30, 16, 30, 16)
            setBackgroundColor(parseThemeColor(themeColor))
            elevation = 10f
            addView(text)
            addView(detailText)
            text.minimumWidth = (resources.displayMetrics.widthPixels * 0.62f).toInt()
            setOnClickListener {
                packageManager.getLaunchIntentForPackage(packageName)?.let { launch ->
                    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    startActivity(launch)
                }
            }
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            },
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            x = 24
            y = 180
        }
        var startX = 0
        var startY = 0
        var touchX = 0f
        var touchY = 0f
        var moved = false
        var pendingX = params.x
        var pendingY = params.y
        var framePosted = false
        panel.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = params.x
                    startY = params.y
                    touchX = event.rawX
                    touchY = event.rawY
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val deltaX = event.rawX - touchX
                    val deltaY = event.rawY - touchY
                    moved = moved || abs(deltaX) + abs(deltaY) > 12f
                    pendingX = startX - deltaX.toInt()
                    pendingY = startY + deltaY.toInt()
                    if (!framePosted) {
                        framePosted = true
                        panel.postOnAnimation {
                            framePosted = false
                            params.x = pendingX
                            params.y = pendingY
                            try {
                                windowManager.updateViewLayout(panel, params)
                            } catch (_: Exception) {
                                // The service may have removed the overlay meanwhile.
                            }
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) panel.performClick()
                    true
                }
                MotionEvent.ACTION_CANCEL -> true
                else -> false
            }
        }
        try {
            windowManager.addView(panel, params)
            overlay = panel
            countdown = text
            detail = detailText
            layoutParams = params
        } catch (_: Exception) {
            overlay = null
            countdown = null
            detail = null
            layoutParams = null
        }
    }

    private fun removeOverlay() {
        val view = overlay ?: return
        try {
            getSystemService(WindowManager::class.java).removeView(view)
        } catch (_: Exception) {
            // Already detached by the system.
        }
        overlay = null
        countdown = null
        detail = null
        layoutParams = null
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "休息倒计时运行状态",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "切换应用或锁屏时保持组间休息倒计时"
            setSound(null, null)
            enableVibration(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(seconds: Int): Notification {
        val launch = packageManager.getLaunchIntentForPackage(packageName)
        val contentIntent = launch?.let {
            PendingIntent.getActivity(
                this,
                NOTIFICATION_ID,
                it,
                PendingIntent.FLAG_UPDATE_CURRENT or immutableFlag(),
            )
        }
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        builder
            .setSmallIcon(applicationInfo.icon)
            .setContentTitle(formatRemaining(seconds))
            .setContentText(nextAction.ifEmpty { "下一组准备中" })
            .setCategory(Notification.CATEGORY_SERVICE)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
        contentIntent?.let(builder::setContentIntent)
        return builder.build()
    }

    private fun refreshNotification(seconds: Int) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildNotification(seconds))
    }

    private fun parseThemeColor(value: String): Int =
        try {
            Color.parseColor(value)
        } catch (_: IllegalArgumentException) {
            Color.parseColor(DEFAULT_THEME_COLOR)
        }

    private fun immutableFlag(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0

    companion object {
        const val ACTION_UPDATE = "com.chenyang.carbs_king.REST_OVERLAY_UPDATE"
        const val ACTION_VISIBILITY = "com.chenyang.carbs_king.REST_OVERLAY_VISIBILITY"
        const val ACTION_STOP = "com.chenyang.carbs_king.REST_OVERLAY_STOP"
        const val EXTRA_CYCLE_ID = "rest_cycle_id"
        const val EXTRA_ENDS_AT_EPOCH_MS = "rest_ends_at_epoch_ms"
        const val EXTRA_APP_VISIBLE = "rest_app_visible"
        const val EXTRA_NEXT_ACTION = "rest_next_action"
        const val EXTRA_THEME_COLOR = "rest_theme_color"
        private const val DEFAULT_THEME_COLOR = "#2A806B"
        private const val CHANNEL_ID = "rest_overlay_service_v1"
        private const val NOTIFICATION_ID = 81390
    }
}

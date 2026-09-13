package com.example.acnotification.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import androidx.car.app.model.CarColor
import androidx.car.app.notification.CarAppExtender
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.example.acnotification.R

object NotificationHelper {

    const val CHANNEL_ID = "ac_proximity_v8"
    const val NOTIFICATION_ID = 1001
    const val NOTIFICATION_ID_COOL = 1002
    const val ACTION_AC_YES = "com.example.acnotification.ACTION_AC_YES"
    const val ACTION_AC_DISMISS = "com.example.acnotification.ACTION_AC_DISMISS"

    fun createNotificationChannel(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)

        // Delete channels from earlier versions so Android OS refreshes channel settings
        try {
            listOf(
                "ac_proximity_channel_v1", "ac_proximity_channel_v2", "ac_proximity_channel_v3",
                "ac_proximity_v4", "ac_proximity_v5", "ac_proximity_v6", "ac_proximity_v7"
            ).forEach { manager.deleteNotificationChannel(it) }
        } catch (_: Exception) {}

        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        val audioAttributes = AudioAttributes.Builder()
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .setUsage(AudioAttributes.USAGE_NOTIFICATION)
            .build()

        val channel = NotificationChannel(
            CHANNEL_ID,
            "AC Proximity Alerts",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Notifications triggered when you arrive near home"
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 250, 250, 250)
            enableLights(true)
            setSound(soundUri, audioAttributes)
            setShowBadge(true)
            lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
        }
        manager.createNotificationChannel(channel)
    }

    /**
     * Shown when AC is OFF — prompts user to turn it on.
     *
     * Phone: BigTextStyle (unchanged visual appearance).
     * Car:   CarAppExtender (androidx.car.app.notification) overrides the in-car
     *        representation so Android Auto shows a proper HUD heads-up with actions.
     */
    fun showACNotification(context: Context) = showACNotification(context, serverReachable = true)

    fun showACNotification(context: Context, serverReachable: Boolean) {
        createNotificationChannel(context)

        val yesIntent = Intent(context, ACActionReceiver::class.java).apply {
            action = ACTION_AC_YES
        }
        val yesPendingIntent = PendingIntent.getBroadcast(
            context,
            0,
            yesIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val dismissIntent = Intent(context, ACActionReceiver::class.java).apply {
            action = ACTION_AC_DISMISS
        }
        val dismissPendingIntent = PendingIntent.getBroadcast(
            context,
            1,
            dismissIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)

        val expandedBody = if (serverReachable) {
            "Turn on the AC before you arrive home?"
        } else {
            "Turn on the AC before you arrive home?\nAC state could not be verified - no server connection."
        }

        // ── Phone notification: BigTextStyle (no emojis, no extra icon) ──────────
        val bigTextStyle = NotificationCompat.BigTextStyle()
            .setBigContentTitle("You're almost home!")
            .bigText(expandedBody)

        val turnOnAction = NotificationCompat.Action.Builder(
            R.drawable.ic_notification,
            "Turn on AC",
            yesPendingIntent
        ).build()

        val dismissAction = NotificationCompat.Action.Builder(
            R.drawable.ic_notification,
            "Dismiss",
            dismissPendingIntent
        ).build()

        // ── Car notification: CarAppExtender from androidx.car.app ───────────────
        // Configures the in-car appearance independently from the phone notification.
        val prefs = context.getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
        val savedHex = prefs.getString("theme_primary", null)
        val dynamicColor = if (!savedHex.isNullOrBlank()) {
            try { android.graphics.Color.parseColor(savedHex) } catch (_: Exception) { 0xFF0284C7.toInt() }
        } else {
            ContextCompat.getColor(context, R.color.primary_dark)
        }
        val carColor = CarColor.createCustom(dynamicColor, dynamicColor)

        val carExtender = CarAppExtender.Builder()
            .setContentTitle("You're almost home!")
            .setContentText(expandedBody)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(carColor)
            .setImportance(NotificationManager.IMPORTANCE_HIGH)
            .setContentIntent(yesPendingIntent)
            .setDeleteIntent(dismissPendingIntent)
            .addAction(R.drawable.ic_notification, "Turn on AC", yesPendingIntent)
            .addAction(R.drawable.ic_notification, "Dismiss", dismissPendingIntent)
            .build()

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(dynamicColor)
            .setContentTitle("You're almost home!")
            .setContentText("Turn on the AC before you arrive home?")
            .setStyle(bigTextStyle)
            .setContentIntent(yesPendingIntent)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setSound(soundUri)
            .setVibrate(longArrayOf(0, 250, 250, 250))
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .addAction(turnOnAction)
            .addAction(dismissAction)
            .extend(carExtender)
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification)
    }

    /** Shown when AC is already ON — informational only. */
    fun showAlreadyCoolNotification(context: Context) {
        createNotificationChannel(context)

        val prefs = context.getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
        val savedHex = prefs.getString("theme_primary", null)
        val dynamicColor = if (!savedHex.isNullOrBlank()) {
            try { android.graphics.Color.parseColor(savedHex) } catch (_: Exception) { 0xFF0284C7.toInt() }
        } else {
            ContextCompat.getColor(context, R.color.primary_dark)
        }

        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)

        val bigTextStyle = NotificationCompat.BigTextStyle()
            .setBigContentTitle("Welcome home!")
            .bigText("Your AC is already on - enjoy the cool air.")

        val carColor = CarColor.createCustom(dynamicColor, dynamicColor)

        val carExtender = CarAppExtender.Builder()
            .setContentTitle("Welcome home!")
            .setContentText("Your AC is already on - enjoy the cool air.")
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(carColor)
            .setImportance(NotificationManager.IMPORTANCE_HIGH)
            .build()

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(dynamicColor)
            .setContentTitle("Welcome home!")
            .setContentText("Your AC is already on - enjoy the cool air.")
            .setStyle(bigTextStyle)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setSound(soundUri)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .extend(carExtender)
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID_COOL, notification)
    }
}

package com.example.acnotification.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.media.AudioAttributes
import android.media.RingtoneManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.example.acnotification.R

object NotificationHelper {

    const val CHANNEL_ID = "ac_proximity_v6"
    const val NOTIFICATION_ID = 1001
    const val NOTIFICATION_ID_COOL = 1002
    const val ACTION_AC_YES = "com.example.acnotification.ACTION_AC_YES"
    const val ACTION_AC_DISMISS = "com.example.acnotification.ACTION_AC_DISMISS"

    fun createNotificationChannel(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)

        // Delete old cached channels so Android OS refreshes channel settings (importance, sound, etc.)
        try {
            manager.deleteNotificationChannel("ac_proximity_channel_v1")
            manager.deleteNotificationChannel("ac_proximity_channel_v2")
            manager.deleteNotificationChannel("ac_proximity_channel_v3")
            manager.deleteNotificationChannel("ac_proximity_v4")
            manager.deleteNotificationChannel("ac_proximity_v5")
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
     * Uses BigTextStyle + PRIORITY_MAX + CarExtender so Android Auto and phone OS
     * display the actionable buttons directly on the vehicle screen.
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
        val appAvatar = BitmapFactory.decodeResource(context.resources, R.mipmap.ic_launcher)

        val expandedBody = if (serverReachable) {
            "Turn on the AC before you arrive home?"
        } else {
            "Turn on the AC before you arrive home?\n⚠️ AC state couldn't be verified — no server connection."
        }

        val bigTextStyle = NotificationCompat.BigTextStyle()
            .setBigContentTitle("You're almost home! 🏠")
            .bigText(expandedBody)

        val turnOnAction = NotificationCompat.Action.Builder(
            R.drawable.ic_notification,
            "✅ Turn on AC",
            yesPendingIntent
        ).build()

        val dismissAction = NotificationCompat.Action.Builder(
            R.drawable.ic_notification,
            "Dismiss",
            dismissPendingIntent
        ).build()

        // Android Auto CarExtender configuration with dynamic phone theme color
        val prefs = context.getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
        val savedHex = prefs.getString("theme_primary", null)
        val dynamicColor = if (!savedHex.isNullOrBlank()) {
            try { android.graphics.Color.parseColor(savedHex) } catch (_: Exception) { 0xFF0284C7.toInt() }
        } else {
            ContextCompat.getColor(context, R.color.primary_dark)
        }

        val carExtender = NotificationCompat.CarExtender()
            .setLargeIcon(appAvatar)
            .setColor(dynamicColor)

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setLargeIcon(appAvatar)
            .setColor(dynamicColor)
            .setContentTitle("You're almost home! 🏠")
            .setContentText("Turn on the AC before you arrive?")
            .setStyle(bigTextStyle)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
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

    /** Shown when AC is already ON — informational only, surfaces in car via CarExtender. */
    fun showAlreadyCoolNotification(context: Context) {
        createNotificationChannel(context)

        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        val appAvatar = BitmapFactory.decodeResource(context.resources, R.mipmap.ic_launcher)

        val carExtender = NotificationCompat.CarExtender()
            .setLargeIcon(appAvatar)

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setLargeIcon(appAvatar)
            .setContentTitle("Welcome home! ❄️")
            .setContentText("Your AC is already on — enjoy the cool air.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
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

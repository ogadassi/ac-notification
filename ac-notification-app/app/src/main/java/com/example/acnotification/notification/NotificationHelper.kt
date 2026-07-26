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
import com.example.acnotification.R

object NotificationHelper {

    const val CHANNEL_ID = "ac_proximity_v6"
    const val NOTIFICATION_ID = 1001
    const val NOTIFICATION_ID_COOL = 1002
    private const val ACTION_AC_YES = "com.example.acnotification.ACTION_AC_YES"

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
     * Uses BigTextStyle + PRIORITY_MAX so Android OS automatically expands the notification card
     * on arrival, revealing the "✅ Turn on AC" action button immediately without requiring a click.
     */
    fun showACNotification(context: Context) {
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

        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        val appAvatar = BitmapFactory.decodeResource(context.resources, R.mipmap.ic_launcher)

        val bigTextStyle = NotificationCompat.BigTextStyle()
            .setBigContentTitle("You're almost home! 🏠")
            .bigText("Turn on the AC before you arrive?")

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification) // Pure monochromatic white app vector for status bar
            .setLargeIcon(appAvatar)                  // Full-color app icon avatar for the notification bubble
            .setContentTitle("You're almost home! 🏠")
            .setContentText("Turn on the AC before you arrive?")
            .setStyle(bigTextStyle)
            .setPriority(NotificationCompat.PRIORITY_MAX)   // PRIORITY_MAX forces top position & immediate auto-expansion
            .setCategory(NotificationCompat.CATEGORY_MESSAGE) // Lets Android Auto & OS surface action buttons
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setSound(soundUri)
            .setVibrate(longArrayOf(0, 250, 250, 250))
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            // Action button — displayed IMMEDIATELY on the auto-expanded notification card
            .addAction(
                NotificationCompat.Action.Builder(
                    R.drawable.ic_notification,
                    "✅ Turn on AC",
                    yesPendingIntent
                ).build()
            )
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification)
    }

    /** Shown when AC is already ON — informational only, no action button needed. */
    fun showAlreadyCoolNotification(context: Context) {
        createNotificationChannel(context)

        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        val appAvatar = BitmapFactory.decodeResource(context.resources, R.mipmap.ic_launcher)

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setLargeIcon(appAvatar)
            .setContentTitle("Welcome home! ❄️")
            .setContentText("Your AC is already on — enjoy the cool air.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setSound(soundUri)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID_COOL, notification)
    }
}

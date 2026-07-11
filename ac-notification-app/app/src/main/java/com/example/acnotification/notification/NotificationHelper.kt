package com.example.acnotification.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat

object NotificationHelper {

    const val CHANNEL_ID = "ac_proximity_channel"
    const val NOTIFICATION_ID = 1001
    private const val ACTION_AC_YES = "com.example.acnotification.ACTION_AC_YES"

    fun createNotificationChannel(context: Context) {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "AC Proximity Alerts",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Notifications triggered when you arrive near home"
            enableVibration(true)
            setShowBadge(true)
        }
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }

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

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Returning Home?")
            .setContentText("Want to turn the AC on?")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .addAction(
                android.R.drawable.ic_media_play,
                "Yes",
                yesPendingIntent
            )
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification)
    }
}

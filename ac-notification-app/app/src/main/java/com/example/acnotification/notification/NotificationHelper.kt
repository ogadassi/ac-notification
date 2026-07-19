package com.example.acnotification.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat
import com.example.acnotification.R

object NotificationHelper {

    const val CHANNEL_ID = "ac_proximity_channel"
    const val NOTIFICATION_ID = 1001
    const val NOTIFICATION_ID_COOL = 1002
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

    /** Shown when AC is OFF — prompts user to turn it on. Button visible on collapsed notification. */
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

        // Custom collapsed RemoteViews layout containing the action button
        val collapsedView = RemoteViews(context.packageName, R.layout.notification_collapsed).apply {
            setOnClickPendingIntent(R.id.btn_turn_on_ac, yesPendingIntent)
        }

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setCustomContentView(collapsedView)
            .setCustomBigContentView(collapsedView)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification)
    }

    /** Shown when AC is already ON — informational only, no action button needed. */
    fun showAlreadyCoolNotification(context: Context) {
        createNotificationChannel(context)

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Welcome home! ❄️")
            .setContentText("Your AC is already on — enjoy the cool air.")
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID_COOL, notification)
    }
}

package com.example.acnotification.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import androidx.core.app.NotificationCompat
import androidx.core.app.Person
import androidx.core.app.RemoteInput
import androidx.core.content.ContextCompat
import androidx.core.graphics.drawable.IconCompat
import com.example.acnotification.R

object NotificationHelper {

    const val CHANNEL_ID = "ac_proximity_v8"
    const val NOTIFICATION_ID = 1001
    const val ACTION_AC_YES = "com.example.acnotification.ACTION_AC_YES"
    const val ACTION_AC_DISMISS = "com.example.acnotification.ACTION_AC_DISMISS"
    const val ACTION_AC_REPLY = "com.example.acnotification.ACTION_AC_REPLY"
    const val ACTION_AC_MARK_READ = "com.example.acnotification.ACTION_AC_MARK_READ"
    const val KEY_VOICE_REPLY = "ac_voice_reply"
    const val EXTRA_PROMPT = "ac_prompt"

    /** One message in the AC conversation: from the app, or the user's own reply. */
    data class Line(val fromUser: Boolean, val text: String)

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
     * Shown when AC is OFF — asks whether to turn it on.
     *
     * Posted as a MessagingStyle conversation with reply and mark-as-read actions: the only notification
     * shape Android Auto shows for sideloaded apps (with its "Unknown sources" developer setting on).
     * In the car the driver taps Reply and says "turn on"; ACActionReceiver acts on the transcribed reply.
     */
    fun showACNotification(context: Context) = showACNotification(context, serverReachable = true)

    fun showACNotification(context: Context, serverReachable: Boolean) {
        val prompt = if (serverReachable) {
            "You're almost home! Turn on the AC before you arrive?"
        } else {
            "You're almost home! Turn on the AC before you arrive? (AC state could not be verified - no server connection.)"
        }
        showConversation(context, prompt, listOf(Line(fromUser = false, text = prompt)), withPhoneButtons = true)
    }

    /** Shown when AC is already ON — informational, but a reply such as "turn off" still works. */
    fun showAlreadyCoolNotification(context: Context) {
        val prompt = "Welcome home! Your AC is already on - enjoy the cool air."
        showConversation(context, prompt, listOf(Line(fromUser = false, text = prompt)))
    }

    /**
     * Posts or updates the AC conversation. [prompt] is the app's opening message, carried on the reply
     * action so later replies can rebuild the conversation. [alert] = false updates it silently.
     */
    fun showConversation(
        context: Context,
        prompt: String,
        lines: List<Line>,
        withPhoneButtons: Boolean = false,
        alert: Boolean = true,
        timeoutMs: Long? = null
    ) {
        createNotificationChannel(context)

        val app = Person.Builder()
            .setName("AC Notification")
            .setKey("ac_notification")
            .setBot(true)
            .setIcon(IconCompat.createWithResource(context, R.drawable.ic_launcher_custom))
            .build()
        val user = Person.Builder().setName("You").setKey("ac_notification_user").build()

        val style = NotificationCompat.MessagingStyle(user)
        val firstTimestamp = System.currentTimeMillis() - lines.size
        lines.forEachIndexed { i, line ->
            style.addMessage(line.text, firstTimestamp + i, if (line.fromUser) user else app)
        }

        val replyIntent = Intent(context, ACActionReceiver::class.java).apply {
            action = ACTION_AC_REPLY
            putExtra(EXTRA_PROMPT, prompt)
        }
        // Mutable so the system can attach the reply text
        val replyPendingIntent = PendingIntent.getBroadcast(
            context, 2, replyIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        )
        val remoteInput = RemoteInput.Builder(KEY_VOICE_REPLY)
            .setLabel("Say \"turn on\" or \"no\"")
            .setChoices(arrayOf("Turn on AC", "Not now"))
            .build()
        val replyAction = NotificationCompat.Action.Builder(R.drawable.ic_notification, "Reply", replyPendingIntent)
            .addRemoteInput(remoteInput)
            .setSemanticAction(NotificationCompat.Action.SEMANTIC_ACTION_REPLY)
            .setShowsUserInterface(false)
            .setAllowGeneratedReplies(false)
            .build()

        // Android Auto fires mark-as-read on its own after reading the message aloud, so it never acts on the AC
        val markReadAction = NotificationCompat.Action.Builder(
            R.drawable.ic_notification, "Mark as read", broadcast(context, ACTION_AC_MARK_READ, 3)
        )
            .setSemanticAction(NotificationCompat.Action.SEMANTIC_ACTION_MARK_AS_READ)
            .setShowsUserInterface(false)
            .build()

        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(themeColor(context))
            .setStyle(style)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setOnlyAlertOnce(!alert)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)

        if (withPhoneButtons) {
            builder.addAction(R.drawable.ic_notification, "Turn on AC", broadcast(context, ACTION_AC_YES, 0))
        }
        builder.addAction(replyAction)
        if (withPhoneButtons) {
            builder.addAction(R.drawable.ic_notification, "Dismiss", broadcast(context, ACTION_AC_DISMISS, 1))
        }
        builder.addInvisibleAction(markReadAction)
        timeoutMs?.let { builder.setTimeoutAfter(it) }

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, builder.build())
    }

    private fun broadcast(context: Context, action: String, requestCode: Int): PendingIntent =
        PendingIntent.getBroadcast(
            context,
            requestCode,
            Intent(context, ACActionReceiver::class.java).setAction(action),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

    private fun themeColor(context: Context): Int {
        val prefs = context.getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
        val savedHex = prefs.getString("theme_primary", null)
        return if (!savedHex.isNullOrBlank()) {
            try { android.graphics.Color.parseColor(savedHex) } catch (_: Exception) { 0xFF0284C7.toInt() }
        } else {
            ContextCompat.getColor(context, R.color.primary_dark)
        }
    }
}

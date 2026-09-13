package com.example.acnotification.notification

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.RemoteInput
import com.example.acnotification.R
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

class ACActionReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "ACActionReceiver"
        private const val PREFS_NAME = "ac_notification_prefs"
        private const val KEY_WEBHOOK_URL = "webhook_url"
        private const val KEY_API_KEY = "api_key"
        // Separate from NotificationHelper.NOTIFICATION_ID so button feedback never replaces the conversation
        private const val CONFIRMATION_NOTIFICATION_ID = 1003
    }

    private sealed interface CommandResult {
        data object Success : CommandResult
        data object NotConfigured : CommandResult
        data class ServerError(val code: Int) : CommandResult
        data object Unreachable : CommandResult
    }

    override fun onReceive(context: Context, intent: Intent) {
        Log.i(TAG, "Action received: ${intent.action}")

        when (intent.action) {
            NotificationHelper.ACTION_AC_REPLY -> handleReply(context, intent)
            // Android Auto calls this after reading the message aloud; keep the conversation so the driver can still reply
            NotificationHelper.ACTION_AC_MARK_READ -> Log.i(TAG, "Conversation marked as read")
            NotificationHelper.ACTION_AC_DISMISS -> {
                context.getSystemService(NotificationManager::class.java).cancel(NotificationHelper.NOTIFICATION_ID)
                Log.i(TAG, "Notification dismissed by user")
            }
            NotificationHelper.ACTION_AC_YES -> handleTurnOnButton(context)
        }
    }

    private fun handleTurnOnButton(context: Context) {
        context.getSystemService(NotificationManager::class.java).cancel(NotificationHelper.NOTIFICATION_ID)
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        if (prefs.getString(KEY_WEBHOOK_URL, "").isNullOrBlank()) {
            Log.w(TAG, "No webhook URL configured")
            showConfirmation(context, "No webhook URL configured")
            return
        }

        showConfirmation(context, "Turning on AC...")
        runAsync {
            val targetTemp = prefs.getInt("target_temp", 22)
            when (val result = sendAcCommand(prefs, powerOn = true)) {
                CommandResult.Success -> showConfirmation(context, "AC is turning on! Cooling to ${targetTemp}°C")
                CommandResult.NotConfigured -> showConfirmation(context, "No webhook URL configured")
                is CommandResult.ServerError -> showConfirmation(context, "Webhook returned ${result.code}")
                CommandResult.Unreachable -> showRetryNotification(context)
            }
        }
    }

    /** Acts on a typed or spoken reply to the conversation notification and answers in the same conversation. */
    private fun handleReply(context: Context, intent: Intent) {
        val reply = RemoteInput.getResultsFromIntent(intent)
            ?.getCharSequence(NotificationHelper.KEY_VOICE_REPLY)?.toString().orEmpty()
        val prompt = intent.getStringExtra(NotificationHelper.EXTRA_PROMPT) ?: "Turn on the AC?"
        val command = ReplyCommand.parse(reply)
        Log.i(TAG, "Reply \"$reply\" -> $command")

        val history = listOf(
            NotificationHelper.Line(fromUser = false, text = prompt),
            NotificationHelper.Line(fromUser = true, text = reply.ifBlank { "(empty reply)" })
        )
        fun respond(text: String, alert: Boolean = true, timeoutMs: Long? = null) =
            NotificationHelper.showConversation(
                context, prompt, history + NotificationHelper.Line(fromUser = false, text = text),
                alert = alert, timeoutMs = timeoutMs
            )

        when (command) {
            ReplyCommand.DECLINE -> respond("OK, leaving the AC as it is.", alert = false, timeoutMs = 15_000)
            ReplyCommand.UNKNOWN -> respond("Sorry, I didn't catch that. Reply \"turn on\" or \"no\".")
            ReplyCommand.TURN_ON, ReplyCommand.TURN_OFF -> {
                val powerOn = command == ReplyCommand.TURN_ON
                // Answering right away also clears the reply spinner on the phone
                respond(if (powerOn) "Turning on the AC..." else "Turning off the AC...", alert = false)
                val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                runAsync {
                    val retryHint = "Reply \"${if (powerOn) "turn on" else "turn off"}\" to try again."
                    when (val result = sendAcCommand(prefs, powerOn)) {
                        CommandResult.Success -> respond(
                            if (powerOn) "Done - the AC is on, cooling to ${prefs.getInt("target_temp", 22)}°C."
                            else "Done - the AC is off.",
                            timeoutMs = 60_000
                        )
                        CommandResult.NotConfigured -> respond("No AC server is set up in the app yet.")
                        is CommandResult.ServerError -> respond("The AC server returned an error (${result.code}). $retryHint")
                        CommandResult.Unreachable -> respond("Couldn't reach the AC server. $retryHint")
                    }
                }
            }
        }
    }

    // goAsync keeps the broadcast alive while the network call runs on a worker thread
    private fun runAsync(block: () -> Unit) {
        val pendingResult = goAsync()
        Thread {
            try {
                block()
            } finally {
                pendingResult.finish()
            }
        }.start()
    }

    private fun sendAcCommand(prefs: SharedPreferences, powerOn: Boolean): CommandResult {
        val url = prefs.getString(KEY_WEBHOOK_URL, "") ?: ""
        if (url.isBlank()) return CommandResult.NotConfigured
        val apiKey = prefs.getString(KEY_API_KEY, "") ?: ""
        val userName = prefs.getString("user_name", "") ?: ""

        val payload = org.json.JSONObject().apply {
            put("action", if (powerOn) "ac_on" else "ac_off")
            if (powerOn) {
                put("target_temp", prefs.getInt("target_temp", 22))
                if (userName.isNotBlank()) put("user", userName)
            }
            put("timestamp", System.currentTimeMillis())
        }.toString()

        return try {
            val request = Request.Builder()
                .url(url)
                .addHeader("X-API-Key", apiKey)
                .addHeader("ngrok-skip-browser-warning", "true")
                .post(payload.toRequestBody("application/json".toMediaType()))
                .build()
            OkHttpClient().newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Log.i(TAG, "Webhook success: ${response.code}")
                    val editor = prefs.edit().putString("real_ac_state", if (powerOn) "ON" else "OFF")
                    // The arrival cooldown only starts when the AC was turned on
                    if (powerOn) editor.putLong("last_action_time", System.currentTimeMillis())
                    editor.apply()
                    CommandResult.Success
                } else {
                    Log.e(TAG, "Webhook error: ${response.code}")
                    CommandResult.ServerError(response.code)
                }
            }
        } catch (e: IOException) {
            Log.e(TAG, "Webhook request failed — no internet", e)
            CommandResult.Unreachable
        } catch (e: IllegalArgumentException) {
            Log.e(TAG, "Invalid webhook URL", e)
            CommandResult.NotConfigured
        }
    }

    private fun showConfirmation(context: Context, message: String) {
        NotificationHelper.createNotificationChannel(context)

        val notification = NotificationCompat.Builder(context, NotificationHelper.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("AC Control")
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setAutoCancel(true)
            .setTimeoutAfter(10_000) // Auto-dismiss after 10 seconds
            .setOnlyAlertOnce(true)
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(CONFIRMATION_NOTIFICATION_ID, notification)
    }

    /**
     * Shown when the webhook POST fails due to no internet (IOException).
     * Offers a Retry button that re-fires the ACTION_AC_YES broadcast so the user
     * can retry when connectivity is restored, without reopening the app.
     */
    private fun showRetryNotification(context: Context) {
        NotificationHelper.createNotificationChannel(context)

        val retryIntent = Intent(context, ACActionReceiver::class.java).apply {
            action = NotificationHelper.ACTION_AC_YES
        }
        val retryPendingIntent = PendingIntent.getBroadcast(
            context,
            10, // distinct request code from the original YES intent
            retryIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val retryAction = NotificationCompat.Action.Builder(
            R.drawable.ic_notification,
            "Retry",
            retryPendingIntent
        )
        .setShowsUserInterface(false)
        .build()

        val notification = NotificationCompat.Builder(context, NotificationHelper.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("AC Control - No Internet")
            .setContentText("Could not reach the AC server. Tap Retry when you are back online.")
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText("Could not reach the AC server.\nTap Retry when you have internet access to turn on the AC.")
            )
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setAutoCancel(true)
            .setTimeoutAfter(60_000) // Auto-dismiss after 60 s
            .addAction(retryAction)
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(CONFIRMATION_NOTIFICATION_ID, notification)
    }
}

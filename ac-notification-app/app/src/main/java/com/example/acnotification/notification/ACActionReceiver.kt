package com.example.acnotification.notification

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.app.NotificationCompat
import com.example.acnotification.R
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException

class ACActionReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "ACActionReceiver"
        private const val PREFS_NAME = "ac_notification_prefs"
        private const val KEY_WEBHOOK_URL = "webhook_url"
        private const val KEY_API_KEY = "api_key"
        private const val CONFIRMATION_NOTIFICATION_ID = 1002
    }

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        Log.i(TAG, "Action received: $action")

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.cancel(NotificationHelper.NOTIFICATION_ID)

        if (action == NotificationHelper.ACTION_AC_DISMISS) {
            Log.i(TAG, "Notification dismissed by user")
            return
        }

        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val webhookUrl = prefs.getString(KEY_WEBHOOK_URL, "") ?: ""
        val apiKey = prefs.getString(KEY_API_KEY, "") ?: ""

        if (webhookUrl.isBlank()) {
            Log.w(TAG, "No webhook URL configured")
            showConfirmation(context, "\u26A0\uFE0F No webhook URL configured")
            return
        }

        showConfirmation(context, "Turning on AC... \u2744\uFE0F")
        
        // Use goAsync to keep broadcast alive during async network call
        val pendingResult = goAsync()
        Thread {
            try {
                fireWebhook(context, webhookUrl, apiKey, prefs)
            } finally {
                pendingResult.finish()
            }
        }.start()
    }

    private fun fireWebhook(context: Context, url: String, apiKey: String, prefs: android.content.SharedPreferences) {
        val client = OkHttpClient()
        val targetTemp = prefs.getInt("target_temp", 22)
        val userName = prefs.getString("user_name", "") ?: ""

        val jsonPayload = org.json.JSONObject().apply {
            put("action", "ac_on")
            put("target_temp", targetTemp)
            if (userName.isNotBlank()) put("user", userName)
            put("timestamp", System.currentTimeMillis())
        }.toString()
        val body = jsonPayload.toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url(url)
            .addHeader("X-API-Key", apiKey)
            .addHeader("ngrok-skip-browser-warning", "true")
            .post(body)
            .build()

        try {
            val response = client.newCall(request).execute()
            response.use {
                if (it.isSuccessful) {
                    Log.i(TAG, "Webhook success: ${it.code}")
                    // Cooldown and state updated on success
                    prefs.edit()
                        .putLong("last_action_time", System.currentTimeMillis())
                        .putString("real_ac_state", "ON")
                        .apply()
                    showConfirmation(context, "AC is turning on! Cooling to ${targetTemp}°C \u2744\uFE0F")
                } else {
                    Log.e(TAG, "Webhook error: ${it.code}")
                    showConfirmation(context, "\u274C Webhook returned ${it.code}")
                }
            }
        } catch (e: IOException) {
            Log.e(TAG, "Webhook request failed — no internet", e)
            showRetryNotification(context)
        }
    }

    private fun showConfirmation(context: Context, message: String) {
        NotificationHelper.createNotificationChannel(context)
        val carExtender = NotificationCompat.CarExtender()

        val notification = NotificationCompat.Builder(context, NotificationHelper.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("AC Control")
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setAutoCancel(true)
            .setTimeoutAfter(10_000) // Auto-dismiss after 10 seconds
            .extend(carExtender)
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
            action = "com.example.acnotification.ACTION_AC_YES"
        }
        val retryPendingIntent = PendingIntent.getBroadcast(
            context,
            10, // distinct request code from the original YES intent
            retryIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val retryAction = NotificationCompat.Action.Builder(
            R.drawable.ic_notification,
            "🔄 Retry",
            retryPendingIntent
        ).build()

        val carExtender = NotificationCompat.CarExtender()

        val notification = NotificationCompat.Builder(context, NotificationHelper.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("AC Control — No Internet")
            .setContentText("❌ Couldn't reach the AC server. Tap Retry when you're back online.")
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText("❌ Couldn't reach the AC server.\nTap Retry when you have internet access to turn on the AC.")
            )
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setAutoCancel(true)
            .setTimeoutAfter(60_000) // Auto-dismiss after 60 s
            .addAction(retryAction)
            .extend(carExtender)
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(CONFIRMATION_NOTIFICATION_ID, notification)
    }
}

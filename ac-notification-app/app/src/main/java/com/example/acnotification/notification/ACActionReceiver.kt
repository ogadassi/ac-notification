package com.example.acnotification.notification

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.app.NotificationCompat
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
        Log.i(TAG, "YES action received — triggering AC")

        // Dismiss the original notification
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.cancel(NotificationHelper.NOTIFICATION_ID)

        // Fire the webhook
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val webhookUrl = prefs.getString(KEY_WEBHOOK_URL, "") ?: ""
        val apiKey = prefs.getString(KEY_API_KEY, "") ?: ""

        if (webhookUrl.isBlank()) {
            Log.w(TAG, "No webhook URL configured")
            showConfirmation(context, "\u26A0\uFE0F No webhook URL configured")
            return
        }

        showConfirmation(context, "Turning on AC... \u2744\uFE0F")
        fireWebhook(context, webhookUrl, apiKey)
    }

    private fun fireWebhook(context: Context, url: String, apiKey: String) {
        val client = OkHttpClient()
        val json = "{\"action\": \"ac_on\", \"timestamp\": ${System.currentTimeMillis()}}"
        val body = json.toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url(url)
            .addHeader("X-API-Key", apiKey)
            .addHeader("ngrok-skip-browser-warning", "true")
            .post(body)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e(TAG, "Webhook request failed", e)
                showConfirmation(context, "\u274C Failed to reach AC webhook")
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    if (it.isSuccessful) {
                        Log.i(TAG, "Webhook success: ${it.code}")
                        showConfirmation(context, "AC is turning on! \u2744\uFE0F")
                    } else {
                        Log.e(TAG, "Webhook error: ${it.code}")
                        showConfirmation(context, "\u274C Webhook returned ${it.code}")
                    }
                }
            }
        })
    }

    private fun showConfirmation(context: Context, message: String) {
        NotificationHelper.createNotificationChannel(context)
        val notification = NotificationCompat.Builder(context, NotificationHelper.CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("AC Control")
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setTimeoutAfter(10_000) // Auto-dismiss after 10 seconds
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(CONFIRMATION_NOTIFICATION_ID, notification)
    }
}

package com.example.acnotification.geofence

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.example.acnotification.notification.NotificationHelper
import com.example.acnotification.util.AppLogger
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofenceStatusCodes
import com.google.android.gms.location.GeofencingEvent
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

class GeofenceBroadcastReceiver : BroadcastReceiver() {

    companion object {
        const val TAG = "GeofenceReceiver"
        const val ACTION_SIMULATE_ENTRY = "com.example.acnotification.ACTION_SIMULATE_GEOFENCE_ENTRY"
        private const val PREFS_NAME = "ac_notification_prefs"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val ts = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault()).format(Date())
        AppLogger.d(TAG, "[$ts] onReceive — action: ${intent.action}")

        // Simulated entry bypasses dwell — fires immediately for testing
        if (intent.action == ACTION_SIMULATE_ENTRY) {
            AppLogger.w(TAG, "[$ts] 🧪 SIMULATED entry — firing immediately (bypasses 60s dwell)")
            val pending = goAsync()
            Thread {
                try { checkAcStateAndNotify(context, ts) }
                finally { pending.finish() }
            }.start()
            return
        }

        val geofencingEvent = GeofencingEvent.fromIntent(intent) ?: run {
            AppLogger.e(TAG, "[$ts] ❌ NULL geofencing event")
            return
        }

        if (geofencingEvent.hasError()) {
            val errorCode = geofencingEvent.errorCode
            val errorMsg = GeofenceStatusCodes.getStatusCodeString(errorCode)
            AppLogger.e(TAG, "[$ts] ❌ Geofencing ERROR code=$errorCode → $errorMsg")
            when (errorCode) {
                GeofenceStatusCodes.GEOFENCE_NOT_AVAILABLE ->
                    AppLogger.e(TAG, "[$ts] CAUSE: GPS/Location OFF or Play Services not initialised")
                GeofenceStatusCodes.GEOFENCE_TOO_MANY_GEOFENCES ->
                    AppLogger.e(TAG, "[$ts] CAUSE: System limit (>100 geofences) exceeded")
                GeofenceStatusCodes.GEOFENCE_TOO_MANY_PENDING_INTENTS ->
                    AppLogger.e(TAG, "[$ts] CAUSE: Too many PendingIntents (>5)")
            }
            return
        }

        val transitionType = geofencingEvent.geofenceTransition
        val transitionName = when (transitionType) {
            Geofence.GEOFENCE_TRANSITION_ENTER -> "ENTER"
            Geofence.GEOFENCE_TRANSITION_EXIT  -> "EXIT"
            Geofence.GEOFENCE_TRANSITION_DWELL -> "DWELL"
            else -> "UNKNOWN($transitionType)"
        }
        val loc = geofencingEvent.triggeringLocation
        AppLogger.i(TAG, "[$ts] 📍 $transitionName | lat=${loc?.latitude}, lng=${loc?.longitude}, acc=${loc?.accuracy}m")

        when (transitionType) {
            Geofence.GEOFENCE_TRANSITION_ENTER -> {
                // Check action cooldown
                val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                val lastActionTime = prefs.getLong("last_action_time", 0L)
                val cooldownMillis = 30 * 60 * 1000L // 30 minutes
                val elapsed = System.currentTimeMillis() - lastActionTime
                
                if (elapsed < cooldownMillis) {
                    val minutesLeft = ((cooldownMillis - elapsed) / 60_000).toInt()
                    AppLogger.i(TAG, "[$ts] ⏱ COOLDOWN active — user clicked Turn on AC ${30 - minutesLeft}m ago. ${minutesLeft}m remaining. Skipping notification.")
                    return
                }

                // Normal execution
                AppLogger.i(TAG, "[$ts] ✅ ENTER detected — starting AC status check...")
                val pending = goAsync()
                Thread {
                    try { checkAcStateAndNotify(context, ts) }
                    finally { pending.finish() }
                }.start()
            }
            Geofence.GEOFENCE_TRANSITION_EXIT -> {
                AppLogger.i(TAG, "[$ts] 🚪 EXIT detected")
            }
            else -> AppLogger.d(TAG, "[$ts] Ignoring transition: $transitionName")
        }
    }

    /**
     * Calls /api/v1/ac/status on the home server.
     * If AC is on  → shows "welcome home, already cool" notification.
     * If AC is off → shows "turn on AC?" notification with action button.
     * If unreachable → falls back to normal notification.
     */
    private fun checkAcStateAndNotify(context: Context, ts: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val webhookUrl = prefs.getString("webhook_url", null)
        val apiKey = prefs.getString("api_key", null)

        if (webhookUrl.isNullOrBlank()) {
            AppLogger.w(TAG, "[$ts] No webhook URL — showing notification directly")
            NotificationHelper.showACNotification(context)
            return
        }

        // Derive base URL: strip trailing /api/v1/ac/trigger if present
        val baseUrl = webhookUrl.substringBefore("/api/v1/")
        val statusUrl = "$baseUrl/api/v1/ac/status"
        AppLogger.i(TAG, "[$ts] 🔍 Checking AC state: GET $statusUrl")

        try {
            val client = OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                .readTimeout(8, TimeUnit.SECONDS)
                .build()

            val request = Request.Builder()
                .url(statusUrl)
                .get()
                .apply { 
                    if (!apiKey.isNullOrBlank()) addHeader("X-API-Key", apiKey)
                    addHeader("ngrok-skip-browser-warning", "true")
                }
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string()

            if (response.isSuccessful && body != null) {
                val json = JSONObject(body)
                val success = json.optBoolean("success", false)
                val acOn = json.optBoolean("ac_on", false)
                val source = json.optString("source", "unknown")
                AppLogger.i(TAG, "[$ts] AC status response: success=$success, ac_on=$acOn, source=$source")

                if (success && acOn) {
                    AppLogger.i(TAG, "[$ts] ❄️ AC already ON → showing 'house is cool' notification")
                    NotificationHelper.showAlreadyCoolNotification(context)
                } else {
                    AppLogger.i(TAG, "[$ts] 🔴 AC is OFF → showing 'turn on AC' notification")
                    NotificationHelper.showACNotification(context)
                }
            } else {
                AppLogger.w(TAG, "[$ts] Status check HTTP ${response.code} — falling back to normal notification")
                NotificationHelper.showACNotification(context)
            }
        } catch (e: Exception) {
            AppLogger.e(TAG, "[$ts] Status check failed: ${e.message} — falling back to normal notification")
            NotificationHelper.showACNotification(context)
        }
    }
}


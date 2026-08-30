package com.example.acnotification.api

import android.content.Context
import com.example.acnotification.util.AppLogger
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class AcApiClient(private val context: Context) {

    companion object {
        private const val TAG = "AcApiClient"
        private const val PREFS_NAME = "ac_notification_prefs"
        private const val KEY_WEBHOOK_URL = "webhook_url"
        private const val KEY_API_KEY = "api_key"
        private const val KEY_REAL_AC_STATE = "real_ac_state"
        private const val KEY_LAST_ACTION_TIME = "last_action_time"
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .build()

    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    data class StatusResult(
        val isAcOn: Boolean,
        val source: String,
        val targetTemp: Double = 22.0
    )

    fun fetchStatus(callback: (Result<StatusResult>) -> Unit) {
        val webhookUrl = prefs.getString(KEY_WEBHOOK_URL, null)
        val apiKey = prefs.getString(KEY_API_KEY, null)

        if (webhookUrl.isNullOrBlank()) {
            AppLogger.w(TAG, "No webhook URL configured for status query")
            callback(Result.failure(IllegalStateException("Webhook URL not configured")))
            return
        }

        val baseUrl = webhookUrl.substringBefore("/api/v1/")
        val statusUrl = "$baseUrl/api/v1/ac/status"
        AppLogger.i(TAG, "Fetching AC status: GET $statusUrl")

        val request = Request.Builder()
            .url(statusUrl)
            .get()
            .apply {
                if (!apiKey.isNullOrBlank()) addHeader("X-API-Key", apiKey)
                addHeader("ngrok-skip-browser-warning", "true")
            }
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                AppLogger.e(TAG, "Status check network failure: ${e.message}")
                callback(Result.failure(e))
            }

            override fun onResponse(call: Call, response: Response) {
                response.use { resp ->
                    if (!resp.isSuccessful) {
                        AppLogger.w(TAG, "Status check returned HTTP ${resp.code}")
                        callback(Result.failure(IOException("Server error HTTP ${resp.code}")))
                        return
                    }
                    val body = resp.body?.string() ?: ""
                    try {
                        val json = JSONObject(body)
                        val isAcOn = json.optBoolean("ac_on", false)
                        val source = json.optString("source", "unknown")
                        prefs.edit().putString(KEY_REAL_AC_STATE, if (isAcOn) "ON" else "OFF").apply()
                        AppLogger.i(TAG, "Status check success: isAcOn=$isAcOn, source=$source")
                        callback(Result.success(StatusResult(isAcOn, source)))
                    } catch (e: Exception) {
                        AppLogger.e(TAG, "Failed to parse status response: ${e.message}")
                        callback(Result.failure(e))
                    }
                }
            }
        })
    }

    fun triggerAc(powerOn: Boolean, callback: (Result<String>) -> Unit) {
        val webhookUrl = prefs.getString(KEY_WEBHOOK_URL, null)
        val apiKey = prefs.getString(KEY_API_KEY, null)

        if (webhookUrl.isNullOrBlank()) {
            AppLogger.w(TAG, "No webhook URL configured for trigger")
            callback(Result.failure(IllegalStateException("Webhook URL not configured")))
            return
        }

        val actionName = if (powerOn) "ac_on" else "ac_off"
        val targetTemp = prefs.getInt("target_temp", 22)
        val userName = prefs.getString("user_name", "") ?: ""

        val jsonObj = JSONObject().apply {
            put("action", actionName)
            if (powerOn) {
                put("target_temp", targetTemp)
                if (userName.isNotBlank()) put("user", userName)
            }
            put("timestamp", System.currentTimeMillis())
        }
        val body = jsonObj.toString().toRequestBody("application/json".toMediaType())

        AppLogger.i(TAG, "Triggering AC: POST $webhookUrl (action=$actionName, temp=$targetTemp, user=$userName)")

        val request = Request.Builder()
            .url(webhookUrl)
            .post(body)
            .apply {
                if (!apiKey.isNullOrBlank()) addHeader("X-API-Key", apiKey)
                addHeader("ngrok-skip-browser-warning", "true")
            }
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                AppLogger.e(TAG, "Trigger network failure: ${e.message}")
                callback(Result.failure(e))
            }

            override fun onResponse(call: Call, response: Response) {
                response.use { resp ->
                    if (resp.isSuccessful) {
                        prefs.edit()
                            .putLong(KEY_LAST_ACTION_TIME, System.currentTimeMillis())
                            .putString(KEY_REAL_AC_STATE, if (powerOn) "ON" else "OFF")
                            .apply()
                        val msg = if (powerOn) "AC is turning on! Cooling to ${targetTemp}°C ❄️" else "AC turned off"
                        AppLogger.i(TAG, "Trigger success: $msg")
                        callback(Result.success(msg))
                    } else {
                        AppLogger.e(TAG, "Trigger failed: HTTP ${resp.code}")
                        callback(Result.failure(IOException("Server error: HTTP ${resp.code}")))
                    }
                }
            }
        })
    }
}

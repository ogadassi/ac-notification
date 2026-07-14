package com.example.acnotification.geofence

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.example.acnotification.notification.NotificationHelper
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofenceStatusCodes
import com.google.android.gms.location.GeofencingEvent
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

class GeofenceBroadcastReceiver : BroadcastReceiver() {

    companion object {
        const val TAG = "GeofenceReceiver"
        private const val PREFS_NAME = "ac_notification_prefs"
        private const val KEY_START_HOUR = "time_start_hour"
        private const val KEY_END_HOUR = "time_end_hour"
        private const val KEY_WEEKDAYS_ONLY = "weekdays_only"
        private const val DEFAULT_START_HOUR = 16
        private const val DEFAULT_END_HOUR = 20

        // Diagnostic flag — set to true to bypass time/day filters during testing
        var DIAGNOSTIC_MODE = false
    }

    override fun onReceive(context: Context, intent: Intent) {
        val ts = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault()).format(Date())
        Log.d(TAG, "[$ts] onReceive called — intent: ${intent.action}")

        val geofencingEvent = GeofencingEvent.fromIntent(intent)

        if (geofencingEvent == null) {
            Log.e(TAG, "[$ts] ❌ NULL geofencing event — intent may not be from Geofencing API")
            return
        }

        if (geofencingEvent.hasError()) {
            val errorCode = geofencingEvent.errorCode
            val errorMsg = GeofenceStatusCodes.getStatusCodeString(errorCode)
            Log.e(TAG, "[$ts] ❌ Geofencing ERROR code=$errorCode → $errorMsg")
            // Common error codes and their meanings:
            // 1000 = GEOFENCE_NOT_AVAILABLE — Location unavailable (GPS off, airplane mode, etc)
            // 1001 = GEOFENCE_TOO_MANY_GEOFENCES — App exceeded 100 geofence limit
            // 1002 = GEOFENCE_TOO_MANY_PENDING_INTENTS — Exceeded 5 PendingIntents per app
            when (errorCode) {
                GeofenceStatusCodes.GEOFENCE_NOT_AVAILABLE ->
                    Log.e(TAG, "[$ts] CAUSE: GPS/Location is OFF or airplane mode is active")
                GeofenceStatusCodes.GEOFENCE_TOO_MANY_GEOFENCES ->
                    Log.e(TAG, "[$ts] CAUSE: Too many geofences registered across all apps (>100)")
                GeofenceStatusCodes.GEOFENCE_TOO_MANY_PENDING_INTENTS ->
                    Log.e(TAG, "[$ts] CAUSE: Too many PendingIntents for this app (>5)")
                else ->
                    Log.e(TAG, "[$ts] CAUSE: Unknown geofencing error")
            }
            return
        }

        val transitionType = geofencingEvent.geofenceTransition
        val transitionName = when (transitionType) {
            Geofence.GEOFENCE_TRANSITION_ENTER -> "ENTER"
            Geofence.GEOFENCE_TRANSITION_EXIT -> "EXIT"
            Geofence.GEOFENCE_TRANSITION_DWELL -> "DWELL"
            else -> "UNKNOWN($transitionType)"
        }
        val triggeringGeofences = geofencingEvent.triggeringGeofences
        val triggeringLocation = geofencingEvent.triggeringLocation

        Log.i(TAG, "[$ts] 📍 Transition: $transitionName")
        Log.i(TAG, "[$ts] 📍 Triggering geofences: ${triggeringGeofences?.map { it.requestId }}")
        Log.i(TAG, "[$ts] 📍 Triggering location: lat=${triggeringLocation?.latitude}, lng=${triggeringLocation?.longitude}, acc=${triggeringLocation?.accuracy}m")

        if (transitionType != Geofence.GEOFENCE_TRANSITION_ENTER) {
            Log.d(TAG, "[$ts] Ignoring non-enter transition: $transitionName")
            return
        }

        Log.i(TAG, "[$ts] ✅ Geofence ENTER detected — checking guards...")

        // Cooldown check
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val lastTriggerTime = prefs.getLong("last_trigger_time", 0L)
        val cooldownMillis = 30 * 60 * 1000L
        val timeSinceLast = System.currentTimeMillis() - lastTriggerTime
        if (timeSinceLast < cooldownMillis && !DIAGNOSTIC_MODE) {
            val minutesLeft = ((cooldownMillis - timeSinceLast) / 60000).toInt()
            Log.i(TAG, "[$ts] ⏱ COOLDOWN active — ${minutesLeft}m remaining before next trigger")
            return
        }
        if (DIAGNOSTIC_MODE && timeSinceLast < cooldownMillis) {
            Log.w(TAG, "[$ts] 🧪 DIAGNOSTIC_MODE: bypassing cooldown")
        }

        // Time window check
        val calendar = Calendar.getInstance()
        val currentHour = calendar.get(Calendar.HOUR_OF_DAY)
        val dayOfWeek = calendar.get(Calendar.DAY_OF_WEEK)
        val startHour = prefs.getInt(KEY_START_HOUR, DEFAULT_START_HOUR)
        val endHour = prefs.getInt(KEY_END_HOUR, DEFAULT_END_HOUR)
        val weekdaysOnly = prefs.getBoolean(KEY_WEEKDAYS_ONLY, true)
        val dayName = SimpleDateFormat("EEEE", Locale.getDefault()).format(Date())

        Log.d(TAG, "[$ts] 🕐 Time: ${currentHour}:00, Day: $dayName, Window: ${startHour}:00-${endHour}:00, WeekdaysOnly: $weekdaysOnly")

        if (!DIAGNOSTIC_MODE) {
            if (weekdaysOnly && (dayOfWeek == Calendar.SATURDAY || dayOfWeek == Calendar.FRIDAY)) {
                Log.i(TAG, "[$ts] 📅 BLOCKED — Weekend day ($dayName)")
                return
            }
            if (currentHour !in startHour until endHour) {
                Log.i(TAG, "[$ts] ⏰ BLOCKED — Hour $currentHour is outside window [$startHour-$endHour)")
                return
            }
        } else {
            Log.w(TAG, "[$ts] 🧪 DIAGNOSTIC_MODE: bypassing time and day filters")
        }

        Log.i(TAG, "[$ts] 🚀 All guards passed — firing notification!")

        prefs.edit()
            .putLong("last_trigger_time", System.currentTimeMillis())
            .apply()

        NotificationHelper.showACNotification(context)
    }
}

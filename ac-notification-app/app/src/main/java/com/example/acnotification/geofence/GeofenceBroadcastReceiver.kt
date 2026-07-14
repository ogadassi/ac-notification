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
import java.util.Date
import java.util.Locale

class GeofenceBroadcastReceiver : BroadcastReceiver() {

    companion object {
        const val TAG = "GeofenceReceiver"
        const val ACTION_SIMULATE_ENTRY = "com.example.acnotification.ACTION_SIMULATE_GEOFENCE_ENTRY"
        private const val PREFS_NAME = "ac_notification_prefs"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val ts = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault()).format(Date())
        Log.d(TAG, "[$ts] onReceive — action: ${intent.action}")

        // ── Debug / Test path (ADB or in-app button) ──────────────────────────
        if (intent.action == ACTION_SIMULATE_ENTRY) {
            Log.w(TAG, "[$ts] 🧪 SIMULATED GEOFENCE ENTRY received (debug trigger)")
            fireNotification(context, ts, diagnosticMode = true)
            return
        }

        // ── Real Play Services geofencing path ────────────────────────────────
        val geofencingEvent = GeofencingEvent.fromIntent(intent)

        if (geofencingEvent == null) {
            Log.e(TAG, "[$ts] ❌ NULL geofencing event")
            return
        }

        if (geofencingEvent.hasError()) {
            val errorCode = geofencingEvent.errorCode
            val errorMsg = GeofenceStatusCodes.getStatusCodeString(errorCode)
            Log.e(TAG, "[$ts] ❌ Geofencing ERROR code=$errorCode → $errorMsg")
            when (errorCode) {
                GeofenceStatusCodes.GEOFENCE_NOT_AVAILABLE ->
                    Log.e(TAG, "[$ts] CAUSE: GPS/Location is OFF or Play Services not initialised")
                GeofenceStatusCodes.GEOFENCE_TOO_MANY_GEOFENCES ->
                    Log.e(TAG, "[$ts] CAUSE: System limit (>100 geofences) exceeded")
                GeofenceStatusCodes.GEOFENCE_TOO_MANY_PENDING_INTENTS ->
                    Log.e(TAG, "[$ts] CAUSE: App has too many PendingIntents (>5)")
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
        Log.i(TAG, "[$ts] 📍 Transition: $transitionName")
        Log.i(TAG, "[$ts] 📍 Geofences: ${geofencingEvent.triggeringGeofences?.map { it.requestId }}")
        Log.i(TAG, "[$ts] 📍 Location:  lat=${loc?.latitude}, lng=${loc?.longitude}, acc=${loc?.accuracy}m")

        if (transitionType != Geofence.GEOFENCE_TRANSITION_ENTER) {
            Log.d(TAG, "[$ts] Ignoring non-ENTER transition")
            return
        }

        fireNotification(context, ts, diagnosticMode = false)
    }

    private fun fireNotification(context: Context, ts: String, diagnosticMode: Boolean) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        // Cooldown check
        val lastTriggerTime = prefs.getLong("last_trigger_time", 0L)
        val cooldownMillis = 30 * 60 * 1000L
        val timeSinceLast = System.currentTimeMillis() - lastTriggerTime
        if (timeSinceLast < cooldownMillis) {
            val minutesLeft = ((cooldownMillis - timeSinceLast) / 60000).toInt()
            if (!diagnosticMode) {
                Log.i(TAG, "[$ts] ⏱ COOLDOWN — ${minutesLeft}m remaining")
                return
            } else {
                Log.w(TAG, "[$ts] 🧪 DIAGNOSTIC: bypassing cooldown (${minutesLeft}m remaining)")
            }
        }

        Log.i(TAG, "[$ts] 🚀 Firing notification!")
        prefs.edit().putLong("last_trigger_time", System.currentTimeMillis()).apply()
        NotificationHelper.showACNotification(context)
    }
}

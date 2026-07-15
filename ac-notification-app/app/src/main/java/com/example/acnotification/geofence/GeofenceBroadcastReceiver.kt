package com.example.acnotification.geofence

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.example.acnotification.notification.NotificationHelper
import com.example.acnotification.util.AppLogger
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
        AppLogger.d(TAG, "[$ts] onReceive — action: ${intent.action}")

        if (intent.action == ACTION_SIMULATE_ENTRY) {
            AppLogger.w(TAG, "[$ts] 🧪 SIMULATED GEOFENCE ENTRY received")
            fireNotification(context, ts)
            return
        }

        val geofencingEvent = GeofencingEvent.fromIntent(intent)

        if (geofencingEvent == null) {
            AppLogger.e(TAG, "[$ts] ❌ NULL geofencing event — intent had no geofence data")
            return
        }

        if (geofencingEvent.hasError()) {
            val errorCode = geofencingEvent.errorCode
            val errorMsg = GeofenceStatusCodes.getStatusCodeString(errorCode)
            AppLogger.e(TAG, "[$ts] ❌ Geofencing ERROR code=$errorCode → $errorMsg")
            when (errorCode) {
                GeofenceStatusCodes.GEOFENCE_NOT_AVAILABLE ->
                    AppLogger.e(TAG, "[$ts] CAUSE: GPS/Location is OFF or Play Services not initialised")
                GeofenceStatusCodes.GEOFENCE_TOO_MANY_GEOFENCES ->
                    AppLogger.e(TAG, "[$ts] CAUSE: System limit (>100 geofences) exceeded")
                GeofenceStatusCodes.GEOFENCE_TOO_MANY_PENDING_INTENTS ->
                    AppLogger.e(TAG, "[$ts] CAUSE: App has too many PendingIntents (>5)")
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
        AppLogger.i(TAG, "[$ts] 📍 Transition: $transitionName | geofences: ${geofencingEvent.triggeringGeofences?.map { it.requestId }}")
        AppLogger.i(TAG, "[$ts] 📍 Location: lat=${loc?.latitude}, lng=${loc?.longitude}, acc=${loc?.accuracy}m")

        if (transitionType == Geofence.GEOFENCE_TRANSITION_EXIT) {
            AppLogger.i(TAG, "[$ts] 🚪 EXIT detected — Play Services sees you leaving the zone")
            return
        }

        if (transitionType != Geofence.GEOFENCE_TRANSITION_ENTER) {
            AppLogger.d(TAG, "[$ts] Ignoring non-ENTER transition: $transitionName")
            return
        }

        fireNotification(context, ts)
    }

    private fun fireNotification(context: Context, ts: String) {
        AppLogger.i(TAG, "[$ts] 🚀 Firing notification!")
        NotificationHelper.showACNotification(context)
    }
}

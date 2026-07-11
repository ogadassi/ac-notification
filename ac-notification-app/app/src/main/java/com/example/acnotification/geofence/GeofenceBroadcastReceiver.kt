package com.example.acnotification.geofence

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.example.acnotification.notification.NotificationHelper
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingEvent
import java.util.Calendar

class GeofenceBroadcastReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "GeofenceReceiver"
        private const val PREFS_NAME = "ac_notification_prefs"
        private const val KEY_START_HOUR = "time_start_hour"
        private const val KEY_END_HOUR = "time_end_hour"
        private const val KEY_WEEKDAYS_ONLY = "weekdays_only"
        private const val DEFAULT_START_HOUR = 16
        private const val DEFAULT_END_HOUR = 20
    }

    override fun onReceive(context: Context, intent: Intent) {
        val geofencingEvent = GeofencingEvent.fromIntent(intent)
        if (geofencingEvent == null) {
            Log.e(TAG, "Null geofencing event")
            return
        }
        if (geofencingEvent.hasError()) {
            Log.e(TAG, "Geofencing error: ${geofencingEvent.errorCode}")
            return
        }

        val transitionType = geofencingEvent.geofenceTransition
        if (transitionType != Geofence.GEOFENCE_TRANSITION_ENTER) {
            Log.d(TAG, "Ignoring non-enter transition: $transitionType")
            return
        }

        Log.i(TAG, "Geofence ENTER detected")

        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val lastTriggerTime = prefs.getLong("last_trigger_time", 0L)
        val cooldownMillis = 30 * 60 * 1000 // 30 minutes cooldown to filter out GPS jitter
        if (System.currentTimeMillis() - lastTriggerTime < cooldownMillis) {
            Log.i(TAG, "Geofence triggered, but skipped due to cooldown")
            return
        }

        if (!isWithinTimeWindow(context)) {
            Log.i(TAG, "Outside configured time window, skipping notification")
            return
        }

        // Save last trigger time
        prefs.edit()
            .putLong("last_trigger_time", System.currentTimeMillis())
            .apply()

        NotificationHelper.showACNotification(context)
    }

    private fun isWithinTimeWindow(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val startHour = prefs.getInt(KEY_START_HOUR, DEFAULT_START_HOUR)
        val endHour = prefs.getInt(KEY_END_HOUR, DEFAULT_END_HOUR)
        val weekdaysOnly = prefs.getBoolean(KEY_WEEKDAYS_ONLY, true)

        val calendar = Calendar.getInstance()
        val currentHour = calendar.get(Calendar.HOUR_OF_DAY)
        val dayOfWeek = calendar.get(Calendar.DAY_OF_WEEK)

        if (weekdaysOnly && (dayOfWeek == Calendar.SATURDAY || dayOfWeek == Calendar.FRIDAY)) {
            // In Israel, weekend is Friday-Saturday
            Log.d(TAG, "Weekend day, skipping")
            return false
        }

        return currentHour in startHour until endHour
    }
}

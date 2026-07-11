package com.example.acnotification.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.example.acnotification.geofence.GeofenceManager

class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            Log.i(TAG, "Device booted — re-registering geofence")
            val manager = GeofenceManager(context)
            if (manager.isGeofenceActive) {
                manager.registerGeofence(
                    onSuccess = { Log.i(TAG, "Geofence re-registered after boot") },
                    onFailure = { e -> Log.e(TAG, "Failed to re-register geofence after boot", e) }
                )
            }
        }
    }
}

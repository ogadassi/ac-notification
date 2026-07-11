package com.example.acnotification.geofence

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingRequest
import com.google.android.gms.location.LocationServices

class GeofenceManager(private val context: Context) {

    companion object {
        private const val TAG = "GeofenceManager"
        const val GEOFENCE_ID = "HOME_GEOFENCE"
        private const val PREFS_NAME = "ac_notification_prefs"
        private const val KEY_HOME_LAT = "home_latitude"
        private const val KEY_HOME_LNG = "home_longitude"
        private const val KEY_RADIUS = "geofence_radius"
        private const val KEY_GEOFENCE_ACTIVE = "geofence_active"

        // Default: Ramat Gan city center
        private const val DEFAULT_LAT = 32.0684
        private const val DEFAULT_LNG = 34.8248
        private const val DEFAULT_RADIUS = 200f
    }

    private val geofencingClient = LocationServices.getGeofencingClient(context)
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    val homeLatitude: Double
        get() = prefs.getFloat(KEY_HOME_LAT, DEFAULT_LAT.toFloat()).toDouble()

    val homeLongitude: Double
        get() = prefs.getFloat(KEY_HOME_LNG, DEFAULT_LNG.toFloat()).toDouble()

    val radiusMeters: Float
        get() = prefs.getFloat(KEY_RADIUS, DEFAULT_RADIUS)

    val isGeofenceActive: Boolean
        get() = prefs.getBoolean(KEY_GEOFENCE_ACTIVE, false)

    fun setHomeLocation(lat: Double, lng: Double) {
        prefs.edit()
            .putFloat(KEY_HOME_LAT, lat.toFloat())
            .putFloat(KEY_HOME_LNG, lng.toFloat())
            .apply()
    }

    fun setRadius(radius: Float) {
        prefs.edit().putFloat(KEY_RADIUS, radius).apply()
    }

    fun registerGeofence(onSuccess: () -> Unit = {}, onFailure: (Exception) -> Unit = {}) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "Missing location permission")
            onFailure(SecurityException("Missing location permission"))
            return
        }

        val geofence = Geofence.Builder()
            .setRequestId(GEOFENCE_ID)
            .setCircularRegion(homeLatitude, homeLongitude, radiusMeters)
            .setExpirationDuration(Geofence.NEVER_EXPIRE)
            .setTransitionTypes(Geofence.GEOFENCE_TRANSITION_ENTER)
            .setNotificationResponsiveness(60_000) // 1 minute responsiveness to save battery
            .build()

        val request = GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofence(geofence)
            .build()

        geofencingClient.addGeofences(request, geofencePendingIntent).run {
            addOnSuccessListener {
                Log.i(TAG, "Geofence registered successfully")
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, true).apply()
                onSuccess()
            }
            addOnFailureListener { e ->
                Log.e(TAG, "Failed to register geofence", e)
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, false).apply()
                onFailure(e)
            }
        }
    }

    fun removeGeofence(onComplete: () -> Unit = {}) {
        geofencingClient.removeGeofences(geofencePendingIntent).run {
            addOnCompleteListener {
                Log.i(TAG, "Geofence removed")
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, false).apply()
                onComplete()
            }
        }
    }

    private val geofencePendingIntent: PendingIntent by lazy {
        val intent = Intent(context, GeofenceBroadcastReceiver::class.java)
        PendingIntent.getBroadcast(
            context,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        )
    }
}

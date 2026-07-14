package com.example.acnotification.geofence

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofenceStatusCodes
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
        private const val KEY_HOME_ADDRESS = "home_address_name"

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

    val homeAddressName: String
        get() = prefs.getString(KEY_HOME_ADDRESS, "") ?: ""

    val radiusMeters: Float
        get() = prefs.getFloat(KEY_RADIUS, DEFAULT_RADIUS)

    val isGeofenceActive: Boolean
        get() = prefs.getBoolean(KEY_GEOFENCE_ACTIVE, false)

    fun setHomeLocation(lat: Double, lng: Double, addressName: String? = null) {
        val editor = prefs.edit()
            .putFloat(KEY_HOME_LAT, lat.toFloat())
            .putFloat(KEY_HOME_LNG, lng.toFloat())
        if (addressName != null) {
            editor.putString(KEY_HOME_ADDRESS, addressName)
        }
        editor.apply()
        Log.i(TAG, "Home location updated → lat=$lat, lng=$lng, address=$addressName")
    }

    fun setRadius(radius: Float) {
        prefs.edit().putFloat(KEY_RADIUS, radius).apply()
        Log.i(TAG, "Geofence radius updated → ${radius}m")
    }

    fun registerGeofence(onSuccess: () -> Unit = {}, onFailure: (Exception) -> Unit = {}) {
        // --- Permission Audit ---
        val fineLocation = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION)
        val bgLocation = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        val fineGranted = fineLocation == PackageManager.PERMISSION_GRANTED
        val bgGranted = bgLocation == PackageManager.PERMISSION_GRANTED

        Log.i(TAG, "🔑 Permission audit:")
        Log.i(TAG, "   ACCESS_FINE_LOCATION     → ${if (fineGranted) "✅ GRANTED" else "❌ DENIED"}")
        Log.i(TAG, "   ACCESS_BACKGROUND_LOCATION → ${if (bgGranted) "✅ GRANTED" else "❌ DENIED (Android 10+ requires this for background geofencing)"}")

        if (!fineGranted) {
            val error = SecurityException("Missing ACCESS_FINE_LOCATION permission")
            Log.e(TAG, "❌ Cannot register geofence — ${error.message}")
            onFailure(error)
            return
        }
        if (!bgGranted) {
            Log.w(TAG, "⚠️ ACCESS_BACKGROUND_LOCATION not granted — geofence will NOT fire when app is in background on Android 10+")
        }

        Log.i(TAG, "📍 Registering geofence: id=${GEOFENCE_ID}, center=(${homeLatitude}, ${homeLongitude}), radius=${radiusMeters}m")

        val geofence = Geofence.Builder()
            .setRequestId(GEOFENCE_ID)
            .setCircularRegion(homeLatitude, homeLongitude, radiusMeters)
            .setExpirationDuration(Geofence.NEVER_EXPIRE)
            .setTransitionTypes(Geofence.GEOFENCE_TRANSITION_ENTER)
            .setNotificationResponsiveness(60_000)
            .build()

        val request = GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofence(geofence)
            .build()

        Log.d(TAG, "🔧 PendingIntent flags: FLAG_UPDATE_CURRENT | FLAG_MUTABLE")
        Log.d(TAG, "🔧 InitialTrigger: INITIAL_TRIGGER_ENTER — will fire immediately if already inside geofence")

        geofencingClient.addGeofences(request, geofencePendingIntent).run {
            addOnSuccessListener {
                Log.i(TAG, "✅ Geofence registered successfully!")
                Log.i(TAG, "   ID: $GEOFENCE_ID")
                Log.i(TAG, "   Center: ($homeLatitude, $homeLongitude)")
                Log.i(TAG, "   Radius: ${radiusMeters}m")
                Log.i(TAG, "   Expires: NEVER")
                Log.i(TAG, "   Responsiveness: 60s")
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, true).apply()
                onSuccess()
            }
            addOnFailureListener { e ->
                val statusCode = (e as? com.google.android.gms.common.api.ApiException)?.statusCode ?: -1
                val statusMsg = GeofenceStatusCodes.getStatusCodeString(statusCode)
                Log.e(TAG, "❌ Failed to register geofence — code=$statusCode → $statusMsg")
                Log.e(TAG, "   Exception: ${e.javaClass.simpleName}: ${e.message}")
                when (statusCode) {
                    GeofenceStatusCodes.GEOFENCE_NOT_AVAILABLE ->
                        Log.e(TAG, "   FIX: Enable location services. Check if GPS is ON in device settings.")
                    GeofenceStatusCodes.GEOFENCE_TOO_MANY_GEOFENCES ->
                        Log.e(TAG, "   FIX: Remove existing geofences across apps. System limit is 100 total.")
                    GeofenceStatusCodes.GEOFENCE_TOO_MANY_PENDING_INTENTS ->
                        Log.e(TAG, "   FIX: This app has too many PendingIntents (>5). Check for duplicate registrations.")
                    else ->
                        Log.e(TAG, "   FIX: Check Google Play Services availability and location permissions.")
                }
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, false).apply()
                onFailure(e)
            }
        }
    }

    fun removeGeofence(onComplete: () -> Unit = {}) {
        Log.i(TAG, "🗑 Removing geofence: $GEOFENCE_ID")
        geofencingClient.removeGeofences(geofencePendingIntent).run {
            addOnSuccessListener {
                Log.i(TAG, "✅ Geofence removed successfully")
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, false).apply()
                onComplete()
            }
            addOnFailureListener { e ->
                Log.e(TAG, "❌ Failed to remove geofence: ${e.message}")
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, false).apply()
                onComplete()
            }
        }
    }

    private val geofencePendingIntent: PendingIntent by lazy {
        val intent = Intent(context, GeofenceBroadcastReceiver::class.java)
        Log.d(TAG, "🔧 Creating PendingIntent for GeofenceBroadcastReceiver")
        PendingIntent.getBroadcast(
            context,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        )
    }
}

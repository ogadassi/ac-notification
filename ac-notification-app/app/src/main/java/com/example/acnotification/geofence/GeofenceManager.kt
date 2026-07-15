package com.example.acnotification.geofence

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.example.acnotification.util.AppLogger
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofenceStatusCodes
import com.google.android.gms.location.GeofencingRequest
import com.google.android.gms.location.LocationServices
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

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

        private const val DEFAULT_LAT = 32.0684
        private const val DEFAULT_LNG = 34.8248
        private const val DEFAULT_RADIUS = 200f

        private const val MAX_RETRIES = 3
        private const val RETRY_DELAY_SECONDS = 20L
    }

    private val geofencingClient = LocationServices.getGeofencingClient(context)
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val scheduler = Executors.newSingleThreadScheduledExecutor()

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
        if (addressName != null) editor.putString(KEY_HOME_ADDRESS, addressName)
        editor.apply()
        AppLogger.i(TAG, "Home location updated → lat=$lat, lng=$lng, address=$addressName")
    }

    fun setRadius(radius: Float) {
        prefs.edit().putFloat(KEY_RADIUS, radius).apply()
        AppLogger.i(TAG, "Geofence radius updated → ${radius}m")
    }

    /** Register geofence with automatic retry on transient GEOFENCE_NOT_AVAILABLE errors. */
    fun registerGeofence(
        onSuccess: () -> Unit = {},
        onFailure: (Exception) -> Unit = {},
        retryCount: Int = 0
    ) {
        // --- Permission Audit ---
        val fineGranted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED
        val bgGranted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_BACKGROUND_LOCATION
        ) == PackageManager.PERMISSION_GRANTED

        AppLogger.i(TAG, "🔑 Permission audit (attempt ${retryCount + 1}/$MAX_RETRIES):")
        AppLogger.i(TAG, "   FINE_LOCATION       → ${if (fineGranted) "✅ GRANTED" else "❌ DENIED"}")
        AppLogger.i(TAG, "   BACKGROUND_LOCATION → ${if (bgGranted) "✅ GRANTED" else "❌ DENIED"}")

        if (!fineGranted) {
            val err = SecurityException("Missing ACCESS_FINE_LOCATION")
            AppLogger.e(TAG, "❌ Cannot register geofence — location permission missing")
            onFailure(err)
            return
        }

        AppLogger.i(TAG, "📍 Registering geofence: center=($homeLatitude, $homeLongitude), radius=${radiusMeters}m")

        val geofence = Geofence.Builder()
            .setRequestId(GEOFENCE_ID)
            .setCircularRegion(homeLatitude, homeLongitude, radiusMeters)
            .setExpirationDuration(Geofence.NEVER_EXPIRE)
            .setTransitionTypes(
                Geofence.GEOFENCE_TRANSITION_ENTER or Geofence.GEOFENCE_TRANSITION_EXIT
            )
            .setNotificationResponsiveness(5_000) // 5s — fast enough to catch GPS spoof crossings
            .build()

        val request = GeofencingRequest.Builder()
            .setInitialTrigger(0) // 0 = disabled. Don't fire immediately on registration (e.g. when already home).
            .addGeofence(geofence)
            .build()

        geofencingClient.addGeofences(request, geofencePendingIntent).run {
            addOnSuccessListener {
                AppLogger.i(TAG, "✅ Geofence registered — id=$GEOFENCE_ID, radius=${radiusMeters}m, expires=NEVER")
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, true).apply()
                onSuccess()
            }
            addOnFailureListener { e ->
                val statusCode = (e as? com.google.android.gms.common.api.ApiException)?.statusCode ?: -1
                val statusMsg = GeofenceStatusCodes.getStatusCodeString(statusCode)
                AppLogger.e(TAG, "❌ Geofence registration failed — code=$statusCode ($statusMsg)")

                if (statusCode == GeofenceStatusCodes.GEOFENCE_NOT_AVAILABLE && retryCount < MAX_RETRIES) {
                    val nextRetry = retryCount + 1
                    val delaySec = RETRY_DELAY_SECONDS * nextRetry
                    AppLogger.w(TAG, "⏳ GEOFENCE_NOT_AVAILABLE — retrying in ${delaySec}s (attempt $nextRetry/$MAX_RETRIES)")
                    scheduler.schedule({
                        registerGeofence(onSuccess, onFailure, nextRetry)
                    }, delaySec, TimeUnit.SECONDS)
                } else {
                    when (statusCode) {
                        GeofenceStatusCodes.GEOFENCE_NOT_AVAILABLE ->
                            AppLogger.e(TAG, "   FIX: Enable Location in Settings. Check GPS signal.")
                        GeofenceStatusCodes.GEOFENCE_TOO_MANY_GEOFENCES ->
                            AppLogger.e(TAG, "   FIX: Too many geofences system-wide (>100). Remove others.")
                        GeofenceStatusCodes.GEOFENCE_TOO_MANY_PENDING_INTENTS ->
                            AppLogger.e(TAG, "   FIX: Too many PendingIntents (>5). Check for duplicate registrations.")
                        else ->
                            AppLogger.e(TAG, "   FIX: Unknown error. Ensure Google Play Services is up to date.")
                    }
                    prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, false).apply()
                    onFailure(e)
                }
            }
        }
    }

    fun removeGeofence(onComplete: () -> Unit = {}) {
        AppLogger.i(TAG, "🗑 Removing geofence: $GEOFENCE_ID")
        geofencingClient.removeGeofences(geofencePendingIntent).run {
            addOnSuccessListener {
                AppLogger.i(TAG, "✅ Geofence removed successfully")
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, false).apply()
                onComplete()
            }
            addOnFailureListener { e ->
                AppLogger.e(TAG, "❌ Failed to remove geofence: ${e.message}")
                prefs.edit().putBoolean(KEY_GEOFENCE_ACTIVE, false).apply()
                onComplete()
            }
        }
    }

    private val geofencePendingIntent: PendingIntent by lazy {
        val intent = Intent(context, GeofenceBroadcastReceiver::class.java)
        Log.d(TAG, "🔧 Creating PendingIntent for GeofenceBroadcastReceiver")
        PendingIntent.getBroadcast(
            context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        )
    }
}

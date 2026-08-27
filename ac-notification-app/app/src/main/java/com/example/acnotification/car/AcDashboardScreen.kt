package com.example.acnotification.car

import android.content.Context
import android.graphics.Color
import android.os.Build
import androidx.car.app.CarContext
import androidx.car.app.CarToast
import androidx.car.app.Screen
import androidx.car.app.model.*
import androidx.core.content.ContextCompat
import androidx.core.graphics.drawable.IconCompat
import com.example.acnotification.R
import com.example.acnotification.api.AcApiClient
import com.example.acnotification.geofence.GeofenceManager
import com.example.acnotification.util.AppLogger

class AcDashboardScreen(carContext: CarContext) : Screen(carContext) {

    companion object {
        private const val TAG = "AcDashboardScreen"
    }

    private val apiClient = AcApiClient(carContext)
    private val geofenceManager = GeofenceManager(carContext)

    private var isLoading = false
    private var isAcOn = false
    private var statusDetail = "Checking status..."

    init {
        fetchStatus()
    }

    /**
     * Resolves the primary theme accent color from the user's phone.
     * Uses saved Material You wallpaper colors or Android 12+ system dynamic accent.
     */
    private fun getDynamicThemeColor(): CarColor {
        val prefs = carContext.getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
        val savedHex = prefs.getString("theme_primary", null)
        if (!savedHex.isNullOrBlank()) {
            try {
                val parsed = Color.parseColor(savedHex)
                return CarColor.createCustom(parsed, parsed)
            } catch (_: Exception) {}
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            try {
                val light = ContextCompat.getColor(carContext, android.R.color.system_accent1_500)
                val dark = ContextCompat.getColor(carContext, android.R.color.system_accent1_300)
                return CarColor.createCustom(light, dark)
            } catch (_: Exception) {}
        }

        // Fallback Cyber Cyan from app theme
        return CarColor.createCustom(0xFF5DE6FF.toInt(), 0xFF0284C7.toInt())
    }

    private fun fetchStatus() {
        isLoading = true
        invalidate()
        AppLogger.i(TAG, "Fetching AC status for Car Dashboard...")

        apiClient.fetchStatus { result ->
            isLoading = false
            result.onSuccess { status ->
                isAcOn = status.isAcOn
                statusDetail = if (isAcOn) "Cooling to 22°C (Cool Mode)" else "AC is currently OFF"
                AppLogger.i(TAG, "Car Dashboard status updated: isAcOn=$isAcOn")
            }.onFailure { error ->
                statusDetail = "Unavailable (${error.message ?: "Offline"})"
                AppLogger.w(TAG, "Car Dashboard status check failed: ${error.message}")
            }
            invalidate()
        }
    }

    private fun toggleAc() {
        val targetState = !isAcOn
        isLoading = true
        invalidate()

        CarToast.makeText(
            carContext,
            if (targetState) "Sending Turn ON signal..." else "Sending Turn OFF signal...",
            CarToast.LENGTH_SHORT
        ).show()

        apiClient.triggerAc(targetState) { result ->
            isLoading = false
            result.onSuccess { msg ->
                isAcOn = targetState
                statusDetail = if (isAcOn) "Cooling to 22°C (Cool Mode)" else "AC is currently OFF"
                CarToast.makeText(carContext, msg, CarToast.LENGTH_LONG).show()
                AppLogger.i(TAG, "Car Dashboard AC toggle success: $msg")
            }.onFailure { err ->
                CarToast.makeText(
                    carContext,
                    "⚠️ Failed to control AC: ${err.message}",
                    CarToast.LENGTH_LONG
                ).show()
                AppLogger.e(TAG, "Car Dashboard AC toggle failed: ${err.message}")
            }
            invalidate()
        }
    }

    override fun onGetTemplate(): Template {
        if (isLoading) {
            return PaneTemplate.Builder(
                Pane.Builder()
                    .setLoading(true)
                    .build()
            )
            .setTitle("AC Proximity Automation")
            .setHeaderAction(Action.APP_ICON)
            .build()
        }

        val themeAccent = getDynamicThemeColor()

        // 1. Relevant Compartment: AC Power State
        val statusRow = Row.Builder()
            .setTitle("AC Power Status")
            .addText(if (isAcOn) "🟢 ON — $statusDetail" else "⚪ OFF — $statusDetail")
            .setImage(
                CarIcon.Builder(
                    IconCompat.createWithResource(carContext, R.drawable.ic_notification)
                ).build()
            )
            .build()

        // 2. Relevant Compartment: Target Preset
        val targetTempRow = Row.Builder()
            .setTitle("Target Preset")
            .addText("22.0°C • Auto Fan • Cool Mode")
            .build()

        // 3. Relevant Compartment: Geofence Telemetry
        val geofenceRow = Row.Builder()
            .setTitle("Geofence Proximity")
            .addText(
                if (geofenceManager.isGeofenceActive)
                    "Armed • ${geofenceManager.radiusMeters.toInt()}m radius around Home"
                else "Inactive • Open phone app to arm"
            )
            .build()

        // Primary Toggle Action styled with dynamic phone theme color
        val toggleAction = Action.Builder()
            .setTitle(if (isAcOn) "Turn Off AC" else "Turn On AC ❄️")
            .setBackgroundColor(if (isAcOn) CarColor.RED else themeAccent)
            .setOnClickListener { toggleAc() }
            .build()

        val refreshAction = Action.Builder()
            .setTitle("Refresh")
            .setOnClickListener { fetchStatus() }
            .build()

        val pane = Pane.Builder()
            .addRow(statusRow)
            .addRow(targetTempRow)
            .addRow(geofenceRow)
            .addAction(toggleAction)
            .addAction(refreshAction)
            .build()

        val actionStrip = ActionStrip.Builder()
            .addAction(
                Action.Builder()
                    .setTitle("Refresh")
                    .setOnClickListener { fetchStatus() }
                    .build()
            )
            .build()

        return PaneTemplate.Builder(pane)
            .setTitle("AC Proximity Automation")
            .setHeaderAction(Action.APP_ICON)
            .setActionStrip(actionStrip)
            .build()
    }
}

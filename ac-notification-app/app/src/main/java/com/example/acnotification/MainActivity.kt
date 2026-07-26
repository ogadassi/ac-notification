package com.example.acnotification

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.viewinterop.AndroidView
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import androidx.core.content.ContextCompat
import com.example.acnotification.geofence.GeofenceBroadcastReceiver
import com.example.acnotification.geofence.GeofenceManager
import com.example.acnotification.notification.NotificationHelper
import com.example.acnotification.theme.ACNotificationTheme
import com.example.acnotification.util.AppLogger
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import okhttp3.OkHttpClient

class MainActivity : ComponentActivity() {

    private lateinit var geofenceManager: GeofenceManager
    private val httpClient = OkHttpClient()

    private var geofenceRegisteredThisSession = false
    private var systemColorsMap: Map<String, String>? = null

    private var realACState = "OFF"
    private val handler = android.os.Handler(android.os.Looper.getMainLooper())
    private val statusPollRunnable = object : Runnable {
        override fun run() {
            queryRealACState()
            handler.postDelayed(this, 10000)
        }
    }

    private var locationPermissionGranted = mutableStateOf(false)
    private var backgroundLocationGranted = mutableStateOf(false)
    private var notificationPermissionGranted = mutableStateOf(false)
    private var batteryOptimizationIgnored = mutableStateOf(false)
    private var geofenceActive = mutableStateOf(false)
    private var homeLatitude = mutableStateOf(0.0)
    private var homeLongitude = mutableStateOf(0.0)
    private var homeAddressName = mutableStateOf("")

    private var mainWebView: WebView? = null
    private var lastWebhookTriggerState = false
    private var lastKnownLocation: android.location.Location? = null

    private val locationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        locationPermissionGranted.value = permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true
        if (locationPermissionGranted.value) {
            requestBackgroundLocation()
        }
        refreshUIState()
    }

    private val backgroundLocationLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        backgroundLocationGranted.value = granted
        refreshUIState()
    }

    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        notificationPermissionGranted.value = granted
        refreshUIState()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        geofenceManager = GeofenceManager(this)
        AppLogger.i("MainActivity", "=== App started (onCreate) ===")
        NotificationHelper.createNotificationChannel(this)
        checkPermissions()

        if (geofenceManager.isGeofenceActive && !geofenceRegisteredThisSession) {
            geofenceRegisteredThisSession = true
            AppLogger.i("MainActivity", "onCreate: re-submitting geofence to Play Services (first launch)")
            geofenceManager.registerGeofence(
                onSuccess = {
                    AppLogger.i("MainActivity", "onCreate re-register: SUCCESS")
                    geofenceActive.value = true
                    refreshUIState()
                },
                onFailure = { e ->
                    AppLogger.e("MainActivity", "onCreate re-register: FAILED — ${e.message}")
                    geofenceActive.value = geofenceManager.isGeofenceActive
                    refreshUIState()
                }
            )
        }

        AppLogger.onLogAdded = { entry ->
            val timestamp = entry.time
            val level = entry.level.name
            val escapedMessage = entry.message.replace("'", "\\'")
            runOnUiThread {
                mainWebView?.evaluateJavascript(
                    "if (window.pushLogFromNative) { window.pushLogFromNative('$timestamp', '$level', '$escapedMessage'); }",
                    null
                )
            }
        }

        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(
                android.graphics.Color.TRANSPARENT
            ),
            navigationBarStyle = SystemBarStyle.dark(
                android.graphics.Color.TRANSPARENT
            )
        )
        setContent {
            ACNotificationTheme {
                val colorScheme = MaterialTheme.colorScheme
                systemColorsMap = remember(colorScheme) {
                    mapOf(
                        "primary" to colorScheme.primary.toHex(),
                        "on-primary" to colorScheme.onPrimary.toHex(),
                        "primary-container" to colorScheme.primaryContainer.toHex(),
                        "on-primary-container" to colorScheme.onPrimaryContainer.toHex(),
                        "secondary" to colorScheme.secondary.toHex(),
                        "on-secondary" to colorScheme.onSecondary.toHex(),
                        "secondary-container" to colorScheme.secondaryContainer.toHex(),
                        "on-secondary-container" to colorScheme.onSecondaryContainer.toHex(),
                        "surface" to colorScheme.surface.toHex(),
                        "on-surface" to colorScheme.onSurface.toHex(),
                        "surface-variant" to colorScheme.surfaceVariant.toHex(),
                        "on-surface-variant" to colorScheme.onSurfaceVariant.toHex(),
                        "background" to colorScheme.background.toHex(),
                        "on-background" to colorScheme.onBackground.toHex(),
                        "outline" to colorScheme.outline.toHex(),
                        "outline-variant" to colorScheme.outlineVariant.toHex(),
                        "error" to colorScheme.error.toHex(),
                        "on-error" to colorScheme.onError.toHex(),
                        "surface-container" to colorScheme.surfaceContainer.toHex(),
                        "surface-container-high" to colorScheme.surfaceContainerHigh.toHex(),
                        "surface-container-highest" to colorScheme.surfaceContainerHighest.toHex(),
                        "surface-container-low" to colorScheme.surfaceContainerLow.toHex(),
                        "surface-container-lowest" to colorScheme.surfaceContainerLowest.toHex(),
                        "surface-dim" to colorScheme.surfaceDim.toHex(),
                        "surface-bright" to colorScheme.surfaceBright.toHex()
                    )
                }

                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFF050B14)
                ) {
                    AndroidView(
                        modifier = Modifier.fillMaxSize(),
                        factory = { ctx ->
                            WebView(ctx).apply {
                                layoutParams = ViewGroup.LayoutParams(
                                    ViewGroup.LayoutParams.MATCH_PARENT,
                                    ViewGroup.LayoutParams.MATCH_PARENT
                                )
                                settings.javaScriptEnabled = true
                                settings.domStorageEnabled = true
                                settings.databaseEnabled = true
                                settings.allowFileAccess = true
                                settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                                
                                webViewClient = object : WebViewClient() {
                                    override fun shouldOverrideUrlLoading(view: WebView?, request: android.webkit.WebResourceRequest?): Boolean {
                                        val url = request?.url?.toString() ?: return false
                                        if (url.startsWith("http://") || url.startsWith("https://")) {
                                            try {
                                                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                                                ctx.startActivity(intent)
                                            } catch (e: Exception) {
                                                AppLogger.e("MainActivity", "Failed to open external link: ${e.message}")
                                            }
                                            return true
                                        }
                                        return false
                                    }

                                    override fun onPageFinished(view: WebView?, url: String?) {
                                        super.onPageFinished(view, url)
                                        refreshUIState()
                                    }
                                }
                                
                                addJavascriptInterface(AndroidBridge(ctx), "AndroidBridge")
                                loadUrl("file:///android_asset/index.html")
                                mainWebView = this
                            }
                        }
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        AppLogger.i("MainActivity", "--- onResume ---")
        checkPermissions()
        fetchLastKnownLocation()
        geofenceActive.value = geofenceManager.isGeofenceActive
        homeLatitude.value = geofenceManager.homeLatitude
        homeLongitude.value = geofenceManager.homeLongitude
        homeAddressName.value = geofenceManager.homeAddressName
        refreshUIState()
        handler.post(statusPollRunnable)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(statusPollRunnable)
    }

    private fun checkPermissions() {
        locationPermissionGranted.value = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED

        backgroundLocationGranted.value = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_BACKGROUND_LOCATION
        ) == PackageManager.PERMISSION_GRANTED

        notificationPermissionGranted.value = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(
                this, Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
        } else true

        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        batteryOptimizationIgnored.value = pm.isIgnoringBatteryOptimizations(packageName)
    }

    private fun fetchLastKnownLocation() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            val locationClient = LocationServices.getFusedLocationProviderClient(this)
            locationClient.lastLocation.addOnSuccessListener { loc ->
                if (loc != null) {
                    lastKnownLocation = loc
                    refreshUIState()
                }
            }
        }
    }

    private fun getCurrentLocationDistance(homeLat: Double, homeLng: Double): Double? {
        if (homeLat == 0.0 || homeLng == 0.0) return null
        val loc = lastKnownLocation ?: return null
        val results = FloatArray(1)
        android.location.Location.distanceBetween(loc.latitude, loc.longitude, homeLat, homeLng, results)
        return (results[0] / 1000.0)
    }

    private fun requestLocationPermission() {
        AppLogger.i("MainActivity", "[BTN] Request Fine Location permission")
        locationPermissionLauncher.launch(
            arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            )
        )
    }

    private fun requestBackgroundLocation() {
        AppLogger.i("MainActivity", "[BTN] Request Background Location permission")
        backgroundLocationLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
    }

    private fun requestNotificationPermission() {
        AppLogger.i("MainActivity", "[BTN] Request Notification permission")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    private fun toggleGeofence(enabled: Boolean) {
        AppLogger.i("MainActivity", "Geofence monitoring toggled → ${if (enabled) "ON" else "OFF"}")
        if (enabled) {
            geofenceManager.registerGeofence(
                onSuccess = {
                    AppLogger.i("MainActivity", "Geofence registered successfully")
                    geofenceActive.value = true
                    refreshUIState()
                },
                onFailure = { e ->
                    AppLogger.e("MainActivity", "Geofence registration FAILED — ${e.message}")
                    geofenceActive.value = false
                    refreshUIState()
                    Toast.makeText(this, "Geofence registration failed", Toast.LENGTH_LONG).show()
                }
            )
        } else {
            geofenceManager.removeGeofence {
                AppLogger.i("MainActivity", "Geofence removed")
                geofenceActive.value = false
                refreshUIState()
            }
        }
    }

    private fun simulateGeofenceEntry() {
        AppLogger.i("MainActivity", "Simulating Geofence Entry")
        val intent = Intent(GeofenceBroadcastReceiver.ACTION_SIMULATE_ENTRY).apply {
            setClass(this@MainActivity, GeofenceBroadcastReceiver::class.java)
        }
        sendBroadcast(intent)
        Toast.makeText(this, "Simulated geofence entry sent!", Toast.LENGTH_SHORT).show()
    }

    private fun clearCooldown() {
        AppLogger.i("MainActivity", "Clearing action cooldown")
        val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
        prefs.edit().remove("last_action_time").apply()
        Toast.makeText(this, "Action cooldown cleared!", Toast.LENGTH_SHORT).show()
    }

    private fun updateGeofenceRadius(radius: Float) {
        AppLogger.i("MainActivity", "Radius changed → ${radius.toInt()}m")
        geofenceManager.setRadius(radius)
        if (geofenceActive.value) {
            geofenceManager.registerGeofence()
        }
    }

    private fun disableBatteryOptimization() {
        AppLogger.i("MainActivity", "Disable Battery Optimization requested")
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        if (!pm.isIgnoringBatteryOptimizations(packageName)) {
            try {
                val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                }
                startActivity(intent)
            } catch (e: Exception) {
                AppLogger.w("MainActivity", "Battery optimization dialog failed: ${e.message}")
                try {
                    val intent = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
                    startActivity(intent)
                } catch (ex: Exception) {
                    AppLogger.e("MainActivity", "Could not open battery settings: ${ex.message}")
                }
            }
        }
    }

    private fun openChannelSettings() {
        AppLogger.i("MainActivity", "Opening notification channel settings")
        try {
            val intent = Intent(Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS).apply {
                putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                putExtra(Settings.EXTRA_CHANNEL_ID, NotificationHelper.CHANNEL_ID)
            }
            startActivity(intent)
        } catch (e: Exception) {
            try {
                val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).apply {
                    putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                }
                startActivity(intent)
            } catch (ex: Exception) {
                AppLogger.e("MainActivity", "Could not open notification settings: ${ex.message}")
            }
        }
    }

    private fun setHomeLocationFromSearch(lat: Double, lng: Double, addressName: String) {
        AppLogger.i("MainActivity", "Applying Location: '$addressName' ($lat, $lng)")
        geofenceManager.setHomeLocation(lat, lng, addressName)
        homeLatitude.value = lat
        homeLongitude.value = lng
        homeAddressName.value = addressName
        Toast.makeText(this, "Home address set successfully", Toast.LENGTH_SHORT).show()
        if (geofenceActive.value) {
            toggleGeofence(true)
        }
    }

    private fun setHomeToCurrentLocationWeb() {
        AppLogger.i("MainActivity", "Requesting current GPS fix for Web UI")
        val locationClient = LocationServices.getFusedLocationProviderClient(this)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            val cts = CancellationTokenSource()
            locationClient.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, cts.token)
                .addOnSuccessListener { location ->
                    if (location != null) {
                        AppLogger.i("MainActivity", "GPS fix obtained: lat=${location.latitude}, lng=${location.longitude}")
                        val lat = location.latitude
                        val lng = location.longitude
                        lastKnownLocation = location
                        runOnUiThread {
                            mainWebView?.evaluateJavascript("if (window.onGPSFix) { window.onGPSFix($lat, $lng, 'Current Location'); }", null)
                        }
                    } else {
                        AppLogger.w("MainActivity", "getCurrentLocation returned null — GPS may be off")
                    }
                }
                .addOnFailureListener { e ->
                    AppLogger.e("MainActivity", "getCurrentLocation FAILED: ${e.message}")
                }
        }
    }

    private fun checkAndTriggerProximityIfNeeded() {
        val homeLat = geofenceManager.homeLatitude
        val homeLng = geofenceManager.homeLongitude
        val radius = geofenceManager.radiusMeters
        val isMonitoring = geofenceManager.isGeofenceActive

        if (!isMonitoring || homeLat == 0.0 || homeLng == 0.0) return

        val currentLoc = lastKnownLocation ?: return
        val results = FloatArray(1)
        android.location.Location.distanceBetween(
            currentLoc.latitude, currentLoc.longitude,
            homeLat, homeLng,
            results
        )
        val currentDistanceMeters = results[0]

        AppLogger.i("MainActivity", "Refresh Proximity Audit: Distance=${currentDistanceMeters.toInt()}m, Geofence Radius=${radius}m")

        if (currentDistanceMeters <= radius) {
            val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
            val webhookUrl = prefs.getString("webhook_url", "") ?: ""
            val apiKey = prefs.getString("api_key", "") ?: ""
            
            if (webhookUrl.isNotEmpty()) {
                val statusUrl = webhookUrl.replace("/trigger", "/status")
                kotlin.concurrent.thread {
                    try {
                        val conn = java.net.URL(statusUrl).openConnection() as java.net.HttpURLConnection
                        conn.requestMethod = "GET"
                        conn.connectTimeout = 3000
                        conn.readTimeout = 3000
                        if (apiKey.isNotEmpty()) conn.setRequestProperty("X-API-Key", apiKey)
                        
                        if (conn.responseCode == 200) {
                            val responseText = conn.inputStream.bufferedReader().readText()
                            val json = org.json.JSONObject(responseText)
                            val isAcOn = json.optBoolean("power", false) || json.optString("state", "").equals("ON", ignoreCase = true)
                            
                            if (!isAcOn) {
                                AppLogger.i("MainActivity", "Pull-To-Refresh Proximity Trigger: User inside radius & AC is OFF! Triggering Notification Prompt...")
                                com.example.acnotification.notification.NotificationHelper.showACNotification(this@MainActivity)
                            } else {
                                AppLogger.i("MainActivity", "Pull-To-Refresh Proximity Trigger: User inside radius, but AC is ALREADY ON.")
                            }
                        }
                    } catch (e: Exception) {
                        AppLogger.w("MainActivity", "Proximity server audit error: ${e.message}")
                    }
                }
            }
        }
    }

    private fun refreshUIState() {
        val webView = mainWebView ?: return
        val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
        val webhookUrl = prefs.getString("webhook_url", "") ?: ""
        val apiKey = prefs.getString("api_key", "") ?: ""
        val radius = geofenceManager.radiusMeters
        val homeLat = geofenceManager.homeLatitude
        val homeLng = geofenceManager.homeLongitude
        val homeAddress = geofenceManager.homeAddressName
        val geofenceActiveVal = geofenceManager.isGeofenceActive

        val lastActionTime = prefs.getLong("last_action_time", 0L)
        val cooldownMillis = 30 * 60 * 1000L
        val elapsed = System.currentTimeMillis() - lastActionTime
        val cooldownRemaining = if (elapsed < cooldownMillis) {
            ((cooldownMillis - elapsed) / 1000).toInt()
        } else 0

        val lastLocationDist = getCurrentLocationDistance(homeLat, homeLng)

        if (cooldownRemaining > 0) {
            lastWebhookTriggerState = true
        } else if (lastWebhookTriggerState && cooldownRemaining == 0) {
            lastWebhookTriggerState = false
        }

        val json = org.json.JSONObject().apply {
            put("webhookUrl", webhookUrl)
            put("apiKey", apiKey)
            put("radius", radius)
            put("homeLat", homeLat)
            put("homeLng", homeLng)
            put("homeAddress", homeAddress)
            put("distance", lastLocationDist ?: org.json.JSONObject.NULL)
            put("acState", realACState)
            put("geofenceActive", geofenceActiveVal)
            put("permissions", org.json.JSONObject().apply {
                put("location", locationPermissionGranted.value)
                put("backgroundLocation", backgroundLocationGranted.value)
                put("notifications", notificationPermissionGranted.value)
                put("batteryOptimization", batteryOptimizationIgnored.value)
            })
            put("cooldownRemainingSeconds", cooldownRemaining)

            val colors = systemColorsMap
            if (colors != null) {
                put("colors", org.json.JSONObject().apply {
                    colors.forEach { (k, v) -> put(k, v) }
                })
            }
        }

        val jsonStr = json.toString().replace("'", "\\'")
        runOnUiThread {
            webView.evaluateJavascript("if (window.updateState) { window.updateState($jsonStr); }", null)
        }
    }

    inner class AndroidBridge(private val context: Context) {
        @JavascriptInterface
        fun getInitialState(): String {
            val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
            val webhookUrl = prefs.getString("webhook_url", "") ?: ""
            val apiKey = prefs.getString("api_key", "") ?: ""
            val radius = geofenceManager.radiusMeters
            val homeLat = geofenceManager.homeLatitude
            val homeLng = geofenceManager.homeLongitude
            val homeAddress = geofenceManager.homeAddressName
            val geofenceActiveVal = geofenceManager.isGeofenceActive
            val hasCompletedOnboarding = prefs.getBoolean("has_completed_onboarding", false)

            val lastActionTime = prefs.getLong("last_action_time", 0L)
            val cooldownMillis = 30 * 60 * 1000L
            val elapsed = System.currentTimeMillis() - lastActionTime
            val cooldownRemaining = if (elapsed < cooldownMillis) {
                ((cooldownMillis - elapsed) / 1000).toInt()
            } else 0

            val lastLocationDist = getCurrentLocationDistance(homeLat, homeLng)

            val json = org.json.JSONObject().apply {
                put("webhookUrl", webhookUrl)
                put("apiKey", apiKey)
                put("radius", radius)
                put("homeLat", homeLat)
                put("homeLng", homeLng)
                put("homeAddress", homeAddress)
                put("distance", lastLocationDist ?: org.json.JSONObject.NULL)
                put("acState", realACState)
                put("geofenceActive", geofenceActiveVal)
                put("hasCompletedOnboarding", hasCompletedOnboarding)
                put("permissions", org.json.JSONObject().apply {
                    put("location", locationPermissionGranted.value)
                    put("backgroundLocation", backgroundLocationGranted.value)
                    put("notifications", notificationPermissionGranted.value)
                    put("batteryOptimization", batteryOptimizationIgnored.value)
                })
                put("cooldownRemainingSeconds", cooldownRemaining)

                val colors = systemColorsMap
                if (colors != null) {
                    put("colors", org.json.JSONObject().apply {
                        colors.forEach { (k, v) -> put(k, v) }
                    })
                }
            }
            queryRealACState()
            return json.toString()
        }

        @JavascriptInterface
        fun performFullRefresh() {
            runOnUiThread {
                AppLogger.i("MainActivity", "=== Pull-To-Refresh Requested by User ===")
                checkPermissions()
                fetchLastKnownLocation()
                geofenceActive.value = geofenceManager.isGeofenceActive
                homeLatitude.value = geofenceManager.homeLatitude
                homeLongitude.value = geofenceManager.homeLongitude
                homeAddressName.value = geofenceManager.homeAddressName
                checkAndTriggerProximityIfNeeded()
                refreshUIState()
            }
        }

        @JavascriptInterface
        fun setOnboardingCompleted(completed: Boolean) {
            val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
            prefs.edit().putBoolean("has_completed_onboarding", completed).apply()
            AppLogger.i("MainActivity", "Onboarding completed saved: $completed")
        }

        @JavascriptInterface
        fun openExternalUrl(url: String) {
            runOnUiThread {
                try {
                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                    context.startActivity(intent)
                    AppLogger.i("MainActivity", "Launched external URL intent: $url")
                } catch (e: Exception) {
                    AppLogger.e("MainActivity", "Failed to launch external URL: ${e.message}")
                }
            }
        }

        @JavascriptInterface
        fun requestPermission(type: String) {
            runOnUiThread {
                when (type) {
                    "location" -> requestLocationPermission()
                    "backgroundLocation" -> requestBackgroundLocation()
                    "notifications" -> requestNotificationPermission()
                    "batteryOptimization" -> disableBatteryOptimization()
                    "channelSettings" -> openChannelSettings()
                }
            }
        }

        @JavascriptInterface
        fun logClientEvent(tag: String, msg: String) {
            AppLogger.i(tag, msg)
        }

        @JavascriptInterface
        fun performHapticFeedback() {
            runOnUiThread {
                window.decorView.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY)
            }
        }

        @JavascriptInterface
        fun checkLiveACStatusAndHandleLogoTap() {
            runOnUiThread {
                AppLogger.i("MainActivity", "Logo tapped — Querying live AC status from server first...")
                window.decorView.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY)

                val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
                val webhookUrl = prefs.getString("webhook_url", "") ?: ""
                val apiKey = prefs.getString("api_key", "") ?: ""

                if (webhookUrl.isBlank()) {
                    mainWebView?.evaluateJavascript("showInAppNotification('⚠️ No webhook URL configured', 'warning')", null)
                    return@runOnUiThread
                }

                mainWebView?.evaluateJavascript("showInAppNotification('🔍 Checking live AC status...', 'info')", null)

                val baseUrl = webhookUrl.substringBefore("/api/v1/")
                val statusUrl = "$baseUrl/api/v1/ac/status"

                val request = okhttp3.Request.Builder()
                    .url(statusUrl)
                    .get()
                    .apply {
                        if (apiKey.isNotBlank()) addHeader("X-API-Key", apiKey)
                        addHeader("ngrok-skip-browser-warning", "true")
                    }
                    .build()

                httpClient.newCall(request).enqueue(object : okhttp3.Callback {
                    override fun onFailure(call: okhttp3.Call, e: java.io.IOException) {
                        AppLogger.w("MainActivity", "Live status check failed, using cached state: ${e.message}")
                        val cachedState = prefs.getString("real_ac_state", "OFF") ?: "OFF"
                        val isAcOn = cachedState.equals("ON", ignoreCase = true)
                        runOnUiThread {
                            mainWebView?.evaluateJavascript("onLiveACStatusResolved($isAcOn)", null)
                        }
                    }

                    override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                        response.use { resp ->
                            var isAcOn = false
                            if (resp.isSuccessful) {
                                val body = resp.body?.string()
                                if (body != null) {
                                    try {
                                        val json = org.json.JSONObject(body)
                                        isAcOn = json.optBoolean("ac_on", false)
                                        prefs.edit().putString("real_ac_state", if (isAcOn) "ON" else "OFF").apply()
                                        realACState = if (isAcOn) "ON" else "OFF"
                                    } catch (e: Exception) {
                                        AppLogger.e("MainActivity", "Parsing status failed: ${e.message}")
                                    }
                                }
                            }
                            runOnUiThread {
                                refreshUIState()
                                mainWebView?.evaluateJavascript("onLiveACStatusResolved($isAcOn)", null)
                            }
                        }
                    }
                })
            }
        }

        @JavascriptInterface
        fun triggerACTurnOn() {
            runOnUiThread {
                AppLogger.i("MainActivity", "Logo tapped — Triggering AC Turn On")
                window.decorView.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY)

                val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
                val webhookUrl = prefs.getString("webhook_url", "") ?: ""
                val apiKey = prefs.getString("api_key", "") ?: ""

                if (webhookUrl.isBlank()) {
                    AppLogger.w("MainActivity", "No webhook URL configured for logo click")
                    mainWebView?.evaluateJavascript("showInAppNotification('⚠️ No webhook URL configured', 'warning')", null)
                    return@runOnUiThread
                }

                mainWebView?.evaluateJavascript("showInAppNotification('❄️ Turning on AC...', 'info')", null)

                Thread {
                    try {
                        val client = okhttp3.OkHttpClient()
                        val jsonBody = "{\"action\": \"ac_on\", \"timestamp\": ${System.currentTimeMillis()}}"
                        val body = jsonBody.toRequestBody("application/json".toMediaType())

                        val request = okhttp3.Request.Builder()
                            .url(webhookUrl)
                            .addHeader("X-API-Key", apiKey)
                            .addHeader("ngrok-skip-browser-warning", "true")
                            .post(body)
                            .build()

                        val response = client.newCall(request).execute()
                        response.use { resp ->
                            if (resp.isSuccessful) {
                                prefs.edit().putLong("last_action_time", System.currentTimeMillis()).apply()
                                prefs.edit().putString("real_ac_state", "ON").apply()
                                realACState = "ON"
                                runOnUiThread {
                                    mainWebView?.evaluateJavascript("showInAppNotification('✅ AC is turning on! ❄️', 'success')", null)
                                    refreshUIState()
                                }
                            } else {
                                runOnUiThread {
                                    mainWebView?.evaluateJavascript("showInAppNotification('❌ Webhook error: ${resp.code}', 'error')", null)
                                }
                            }
                        }
                    } catch (e: Exception) {
                        AppLogger.e("MainActivity", "Logo AC trigger failed: ${e.message}")
                        runOnUiThread {
                            mainWebView?.evaluateJavascript("showInAppNotification('❌ Failed to reach AC server', 'error')", null)
                        }
                    }
                }.start()
            }
        }

        @JavascriptInterface
        fun triggerACTurnOff() {
            runOnUiThread {
                AppLogger.i("MainActivity", "Logo tapped — Triggering AC Turn OFF")
                window.decorView.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY)

                val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
                val webhookUrl = prefs.getString("webhook_url", "") ?: ""
                val apiKey = prefs.getString("api_key", "") ?: ""

                if (webhookUrl.isBlank()) {
                    AppLogger.w("MainActivity", "No webhook URL configured for logo click")
                    mainWebView?.evaluateJavascript("showInAppNotification('⚠️ No webhook URL configured', 'warning')", null)
                    return@runOnUiThread
                }

                mainWebView?.evaluateJavascript("showInAppNotification('❄️ Turning OFF AC...', 'info')", null)

                Thread {
                    try {
                        val client = okhttp3.OkHttpClient()
                        val jsonBody = "{\"action\": \"ac_off\", \"timestamp\": ${System.currentTimeMillis()}}"
                        val body = jsonBody.toRequestBody("application/json".toMediaType())

                        val request = okhttp3.Request.Builder()
                            .url(webhookUrl)
                            .addHeader("X-API-Key", apiKey)
                            .addHeader("ngrok-skip-browser-warning", "true")
                            .post(body)
                            .build()

                        val response = client.newCall(request).execute()
                        response.use { resp ->
                            if (resp.isSuccessful) {
                                prefs.edit().putString("real_ac_state", "OFF").apply()
                                realACState = "OFF"
                                runOnUiThread {
                                    mainWebView?.evaluateJavascript("showInAppNotification('✅ AC has been turned OFF', 'info')", null)
                                    refreshUIState()
                                }
                            } else {
                                runOnUiThread {
                                    mainWebView?.evaluateJavascript("showInAppNotification('❌ Webhook error: ${resp.code}', 'error')", null)
                                }
                            }
                        }
                    } catch (e: Exception) {
                        AppLogger.e("MainActivity", "Logo AC turn off failed: ${e.message}")
                        runOnUiThread {
                            mainWebView?.evaluateJavascript("showInAppNotification('❌ Failed to reach AC server', 'error')", null)
                        }
                    }
                }.start()
            }
        }

        @JavascriptInterface
        fun resolveAllPermissions() {
            runOnUiThread {
                if (!locationPermissionGranted.value) {
                    requestLocationPermission()
                } else if (!backgroundLocationGranted.value) {
                    requestBackgroundLocation()
                } else if (!notificationPermissionGranted.value) {
                    requestNotificationPermission()
                } else if (!batteryOptimizationIgnored.value) {
                    disableBatteryOptimization()
                }
            }
        }

        @JavascriptInterface
        fun saveSettings(webhookUrlStr: String, apiKeyStr: String) {
            runOnUiThread {
                val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
                prefs.edit().apply {
                    putString("webhook_url", webhookUrlStr)
                    putString("api_key", apiKeyStr)
                    apply()
                }
                AppLogger.i("MainActivity", "Settings updated via Web UI: endpoint=$webhookUrlStr")
                refreshUIState()
                queryRealACState()
            }
        }

        @JavascriptInterface
        fun saveRadius(radiusVal: Float) {
            runOnUiThread {
                updateGeofenceRadius(radiusVal)
                refreshUIState()
            }
        }

        @JavascriptInterface
        fun applyLocation(lat: Double, lng: Double, address: String) {
            runOnUiThread {
                setHomeLocationFromSearch(lat, lng, address)
                refreshUIState()
            }
        }

        @JavascriptInterface
        fun useCurrentLocation() {
            runOnUiThread {
                setHomeToCurrentLocationWeb()
            }
        }

        @JavascriptInterface
        fun simulateGeofenceEntry() {
            runOnUiThread {
                this@MainActivity.simulateGeofenceEntry()
                lastWebhookTriggerState = true
                refreshUIState()
                handler.postDelayed({
                    queryRealACState()
                }, 1500)
            }
        }

        @JavascriptInterface
        fun sendTestNotification() {
            runOnUiThread {
                NotificationHelper.showACNotification(this@MainActivity)
            }
        }

        @JavascriptInterface
        fun clearActionCooldown() {
            runOnUiThread {
                this@MainActivity.clearCooldown()
                refreshUIState()
            }
        }

        @JavascriptInterface
        fun getLogsJSON(): String {
            val array = org.json.JSONArray()
            AppLogger.entries.forEach { entry ->
                array.put(org.json.JSONObject().apply {
                    put("timestamp", entry.time)
                    put("level", entry.level.name)
                    put("message", entry.message)
                })
            }
            return array.toString()
        }

        @JavascriptInterface
        fun clearLogs() {
            runOnUiThread {
                AppLogger.clear()
                refreshUIState()
            }
        }
    }

    private fun queryRealACState() {
        val prefs = getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
        val webhookUrl = prefs.getString("webhook_url", "") ?: ""
        val apiKey = prefs.getString("api_key", "") ?: ""

        if (webhookUrl.isBlank()) {
            return
        }

        // Derive base URL: strip trailing /api/v1/ac/trigger if present
        val baseUrl = webhookUrl.substringBefore("/api/v1/")
        val statusUrl = "$baseUrl/api/v1/ac/status"

        val request = okhttp3.Request.Builder()
            .url(statusUrl)
            .get()
            .apply {
                if (apiKey.isNotBlank()) addHeader("X-API-Key", apiKey)
                addHeader("ngrok-skip-browser-warning", "true")
            }
            .build()

        httpClient.newCall(request).enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: java.io.IOException) {
                AppLogger.d("MainActivity", "Failed to query real AC status: ${e.message}")
            }

            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                response.use {
                    if (response.isSuccessful) {
                        val body = response.body?.string()
                        if (body != null) {
                            try {
                                val json = org.json.JSONObject(body)
                                val acOn = json.optBoolean("ac_on", false)
                                val newState = if (acOn) "ON" else "OFF"
                                if (realACState != newState) {
                                    realACState = newState
                                    runOnUiThread {
                                        refreshUIState()
                                    }
                                }
                            } catch (e: Exception) {
                                AppLogger.d("MainActivity", "Error parsing AC status json: ${e.message}")
                            }
                        }
                    } else {
                        AppLogger.d("MainActivity", "AC status query returned code ${response.code}")
                    }
                }
            }
        })
    }

    fun Color.toHex(): String {
        return String.format("#%06X", 0xFFFFFF and this.toArgb())
    }
}

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
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.example.acnotification.geofence.GeofenceManager
import com.example.acnotification.notification.NotificationHelper
import com.example.acnotification.theme.ACNotificationTheme
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

class MainActivity : ComponentActivity() {

    private lateinit var geofenceManager: GeofenceManager

    private var locationPermissionGranted = mutableStateOf(false)
    private var backgroundLocationGranted = mutableStateOf(false)
    private var notificationPermissionGranted = mutableStateOf(false)
    private var geofenceActive = mutableStateOf(false)
    private var homeLatitude = mutableStateOf(0.0)
    private var homeLongitude = mutableStateOf(0.0)

    private val locationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        locationPermissionGranted.value = permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true
        if (locationPermissionGranted.value) {
            requestBackgroundLocation()
        }
    }

    private val backgroundLocationLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        backgroundLocationGranted.value = granted
    }

    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        notificationPermissionGranted.value = granted
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        geofenceManager = GeofenceManager(this)

        NotificationHelper.createNotificationChannel(this)
        checkPermissions()

        enableEdgeToEdge()
        setContent {
            ACNotificationTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    ACControlScreen(
                        geofenceManager = geofenceManager,
                        locationPermissionGranted = locationPermissionGranted.value,
                        backgroundLocationGranted = backgroundLocationGranted.value,
                        notificationPermissionGranted = notificationPermissionGranted.value,
                        geofenceActive = geofenceActive.value,
                        homeLatitude = homeLatitude.value,
                        homeLongitude = homeLongitude.value,
                        onRequestLocationPermission = { requestLocationPermission() },
                        onRequestBackgroundLocation = { requestBackgroundLocation() },
                        onRequestNotificationPermission = { requestNotificationPermission() },
                        onToggleGeofence = { enabled -> toggleGeofence(enabled) },
                        onDisableBatteryOptimization = { disableBatteryOptimization() },
                        onSetHomeLocation = { setHomeToCurrentLocation() },
                        onRadiusChange = { radius -> updateGeofenceRadius(radius) }
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        checkPermissions()
        geofenceActive.value = geofenceManager.isGeofenceActive
        homeLatitude.value = geofenceManager.homeLatitude
        homeLongitude.value = geofenceManager.homeLongitude
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
    }

    private fun requestLocationPermission() {
        locationPermissionLauncher.launch(
            arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            )
        )
    }

    private fun requestBackgroundLocation() {
        backgroundLocationLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    private fun toggleGeofence(enabled: Boolean) {
        if (enabled) {
            geofenceManager.registerGeofence(
                onSuccess = { geofenceActive.value = true },
                onFailure = { geofenceActive.value = false }
            )
        } else {
            geofenceManager.removeGeofence {
                geofenceActive.value = false
            }
        }
    }

    private fun updateGeofenceRadius(radius: Float) {
        geofenceManager.setRadius(radius)
        // If the geofence is currently active, re-register it with the new radius immediately!
        if (geofenceActive.value) {
            geofenceManager.registerGeofence(
                onSuccess = { geofenceActive.value = true },
                onFailure = { geofenceActive.value = false }
            )
        }
    }

    private fun disableBatteryOptimization() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        if (!pm.isIgnoringBatteryOptimizations(packageName)) {
            val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                data = Uri.parse("package:$packageName")
            }
            startActivity(intent)
        }
    }

    private fun setHomeToCurrentLocation() {
        val locationClient = LocationServices.getFusedLocationProviderClient(this)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            val cts = CancellationTokenSource()
            locationClient.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, cts.token)
                .addOnSuccessListener { location ->
                    if (location != null) {
                        geofenceManager.setHomeLocation(location.latitude, location.longitude)
                        homeLatitude.value = location.latitude
                        homeLongitude.value = location.longitude
                        Toast.makeText(this, "Home set to: ${location.latitude}, ${location.longitude}", Toast.LENGTH_LONG).show()
                        
                        // Auto re-register geofence if active
                        if (geofenceActive.value) {
                            toggleGeofence(true)
                        }
                    } else {
                        Toast.makeText(this, "Could not get location. Ensure GPS is on.", Toast.LENGTH_LONG).show()
                    }
                }
                .addOnFailureListener { e ->
                    Toast.makeText(this, "Location error: ${e.message}", Toast.LENGTH_LONG).show()
                }
        } else {
            Toast.makeText(this, "Location permission not granted.", Toast.LENGTH_SHORT).show()
        }
    }
}

@Composable
fun ACControlScreen(
    geofenceManager: GeofenceManager,
    locationPermissionGranted: Boolean,
    backgroundLocationGranted: Boolean,
    notificationPermissionGranted: Boolean,
    geofenceActive: Boolean,
    homeLatitude: Double,
    homeLongitude: Double,
    onRequestLocationPermission: () -> Unit,
    onRequestBackgroundLocation: () -> Unit,
    onRequestNotificationPermission: () -> Unit,
    onToggleGeofence: (Boolean) -> Unit,
    onDisableBatteryOptimization: () -> Unit,
    onSetHomeLocation: () -> Unit,
    onRadiusChange: (Float) -> Unit
) {
    val context = LocalContext.current
    val prefs = context.getSharedPreferences("ac_notification_prefs", Context.MODE_PRIVATE)
    var webhookUrl by remember { mutableStateOf(prefs.getString("webhook_url", "") ?: "") }
    var apiKey by remember { mutableStateOf(prefs.getString("api_key", "") ?: "") }
    var radiusValue by remember { mutableStateOf(geofenceManager.radiusMeters) }
    
    val lastTriggerTime = prefs.getLong("last_trigger_time", 0L)
    val allPermissionsGranted = locationPermissionGranted && backgroundLocationGranted && notificationPermissionGranted

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp)
            .statusBarsPadding()
            .navigationBarsPadding(),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "Home AC Automation",
            fontSize = 28.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )

        Text(
            text = "Location-based proximity AC controller",
            fontSize = 14.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        HorizontalDivider()

        // --- Permissions Section ---
        Text("Permissions", fontWeight = FontWeight.SemiBold, fontSize = 18.sp)

        PermissionRow(
            label = "Location Access",
            granted = locationPermissionGranted,
            onRequest = onRequestLocationPermission
        )
        PermissionRow(
            label = "Background Location",
            granted = backgroundLocationGranted,
            onRequest = onRequestBackgroundLocation
        )
        PermissionRow(
            label = "Notifications",
            granted = notificationPermissionGranted,
            onRequest = onRequestNotificationPermission
        )

        HorizontalDivider()

        // --- Webhook URL ---
        Text("Webhook URL & Security", fontWeight = FontWeight.SemiBold, fontSize = 18.sp)

        OutlinedTextField(
            value = webhookUrl,
            onValueChange = { newUrl ->
                webhookUrl = newUrl
                prefs.edit().putString("webhook_url", newUrl).apply()
            },
            label = { Text("https://your-webhook-url.com/ac/trigger") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )

        Spacer(modifier = Modifier.height(8.dp))

        OutlinedTextField(
            value = apiKey,
            onValueChange = { newKey ->
                apiKey = newKey
                prefs.edit().putString("api_key", newKey).apply()
            },
            label = { Text("API Secret Key (X-API-Key)") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )

        HorizontalDivider()

        // --- Geofence Control ---
        Text("Geofence Location", fontWeight = FontWeight.SemiBold, fontSize = 18.sp)

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant
            ),
            border = if (geofenceActive) BorderStroke(1.dp, MaterialTheme.colorScheme.primary) else null
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = if (geofenceActive) "Monitoring Active" else "Monitoring Inactive",
                            fontWeight = FontWeight.Bold,
                            color = if (geofenceActive) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Home Location: ${"%.5f".format(homeLatitude)}, ${"%.5f".format(homeLongitude)}",
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "Radius: ${radiusValue.toInt()}m",
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Switch(
                        checked = geofenceActive,
                        onCheckedChange = { onToggleGeofence(it) },
                        enabled = allPermissionsGranted
                    )
                }
                
                Spacer(modifier = Modifier.height(16.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.2f))
                Spacer(modifier = Modifier.height(12.dp))
                
                Text(
                    text = "Adjust Radius: ${radiusValue.toInt()}m",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium
                )
                
                Slider(
                    value = radiusValue,
                    onValueChange = { newValue ->
                        radiusValue = (newValue / 10).roundToInt() * 10f
                    },
                    onValueChangeFinished = {
                        onRadiusChange(radiusValue)
                    },
                    valueRange = 50f..1000f,
                    modifier = Modifier.fillMaxWidth()
                )

                // Circle Overlay Map using OpenStreetMap (OSM) Leaflet in WebView
                if (homeLatitude != 0.0 && homeLongitude != 0.0) {
                    Spacer(modifier = Modifier.height(12.dp))
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(200.dp),
                        shape = MaterialTheme.shapes.medium
                    ) {
                        GeofenceMap(
                            latitude = homeLatitude,
                            longitude = homeLongitude,
                            radius = radiusValue,
                            modifier = Modifier.fillMaxSize()
                        )
                    }
                }
            }
        }

        Button(
            onClick = onSetHomeLocation,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer,
                contentColor = MaterialTheme.colorScheme.onPrimaryContainer
            ),
            enabled = locationPermissionGranted
        ) {
            Text("📍 Set Current Location as Home")
        }

        if (!allPermissionsGranted) {
            Text(
                text = "⚠️ Grant all permissions above before enabling the geofence.",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.error
            )
        }

        // --- Battery Optimization ---
        Button(
            onClick = onDisableBatteryOptimization,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(
                containerColor = MaterialTheme.colorScheme.secondaryContainer,
                contentColor = MaterialTheme.colorScheme.onSecondaryContainer
            )
        ) {
            Text("Disable Battery Optimization")
        }

        // --- Status ---
        HorizontalDivider()
        Text("Status", fontWeight = FontWeight.SemiBold, fontSize = 18.sp)

        if (lastTriggerTime > 0) {
            val formatted = SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.getDefault())
                .format(Date(lastTriggerTime))
            Text("Last triggered: $formatted", fontSize = 13.sp)
        } else {
            Text("No triggers yet", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        // --- Test Button ---
        HorizontalDivider()
        OutlinedButton(
            onClick = { NotificationHelper.showACNotification(context) },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("🔔 Send Test Notification")
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}

@Composable
fun GeofenceMap(
    latitude: Double,
    longitude: Double,
    radius: Float,
    modifier: Modifier = Modifier
) {
    val htmlContent = remember(latitude, longitude) {
        """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <style>
                html, body, #map {
                    width: 100%;
                    height: 100%;
                    margin: 0;
                    padding: 0;
                    background: #0C110C;
                }
                .leaflet-control-attribution {
                    font-size: 8px !important;
                    background: rgba(12,17,12,0.7) !important;
                    color: #8CAF8F !important;
                }
                .leaflet-control-attribution a {
                    color: #4CD964 !important;
                }
            </style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                var map = L.map('map', {
                    zoomControl: false
                }).setView([$latitude, $longitude], 15);

                L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
                    subdomains: 'abcd',
                    maxZoom: 19
                }).addTo(map);

                var marker = L.circleMarker([$latitude, $longitude], {
                    radius: 6,
                    color: '#4CD964',
                    fillColor: '#4CD964',
                    fillOpacity: 1,
                    weight: 2
                }).addTo(map);

                var circle = L.circle([$latitude, $longitude], {
                    color: '#4CD964',
                    fillColor: '#2D5A27',
                    fillOpacity: 0.2,
                    weight: 2,
                    radius: $radius
                }).addTo(map);

                function updateMap(lat, lng, rad) {
                    var newLatLng = L.latLng(lat, lng);
                    marker.setLatLng(newLatLng);
                    circle.setLatLng(newLatLng);
                    circle.setRadius(rad);
                    
                    var zoom = 16;
                    if (rad > 800) zoom = 13;
                    else if (rad > 500) zoom = 14;
                    else if (rad > 200) zoom = 15;
                    
                    map.setView(newLatLng, zoom);
                }
            </script>
        </body>
        </html>
        """.trimIndent()
    }

    var webViewRef by remember { mutableStateOf<WebView?>(null) }

    LaunchedEffect(latitude, longitude, radius) {
        webViewRef?.evaluateJavascript("updateMap($latitude, $longitude, $radius)", null)
    }

    AndroidView(
        factory = { context ->
            WebView(context).apply {
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT
                )
                settings.javaScriptEnabled = true
                settings.userAgentString = "ACProximityApp/1.0"
                settings.domStorageEnabled = true
                webViewClient = WebViewClient()
                loadDataWithBaseURL("https://carto.com", htmlContent, "text/html", "UTF-8", null)
                webViewRef = this
            }
        },
        update = {},
        modifier = modifier
    )
}

@Composable
fun PermissionRow(
    label: String,
    granted: Boolean,
    onRequest: () -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = if (granted) "✅" else "❌",
                fontSize = 16.sp
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(text = label, fontSize = 14.sp)
        }
        if (!granted) {
            TextButton(onClick = onRequest) {
                Text("Grant")
            }
        }
    }
}

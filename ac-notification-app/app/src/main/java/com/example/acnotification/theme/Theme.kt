package com.example.acnotification.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext

// Fallback colors for devices below Android 12 (no Material You support)
private val FallbackDarkScheme = darkColorScheme(
    primary = MintHighlight,
    secondary = ForestGreen,
    tertiary = SageGreen,
    background = DeepDarkBackground,
    surface = SurfaceCardDark,
    onPrimary = DeepDarkBackground,
    onSecondary = OnSurfaceTextDark,
    onBackground = OnSurfaceTextDark,
    onSurface = OnSurfaceTextDark,
    onSurfaceVariant = OnSurfaceVariantTextDark,
    primaryContainer = EmeraldDark,
    onPrimaryContainer = OnSurfaceTextDark,
    surfaceVariant = SurfaceCardDark
)

private val FallbackLightScheme = lightColorScheme(
    primary = ForestGreen,
    secondary = MintHighlight,
    tertiary = SageGreen,
    background = CleanLightBackground,
    surface = SurfaceCardLight,
    onPrimary = CleanLightBackground,
    onSecondary = OnSurfaceTextLight,
    onBackground = OnSurfaceTextLight,
    onSurface = OnSurfaceTextLight,
    onSurfaceVariant = OnSurfaceVariantTextLight,
    primaryContainer = SageGreen,
    onPrimaryContainer = OnSurfaceTextLight,
    surfaceVariant = SurfaceCardLight
)

@Composable
fun ACNotificationTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colorScheme = when {
        // Android 12+: Use Material You dynamic colors from the user's wallpaper
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        // Older devices: Fall back to our custom forest green theme
        darkTheme -> FallbackDarkScheme
        else -> FallbackLightScheme
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}

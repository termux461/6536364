package com.lizercool.lcvpn.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val AccentGreen = Color(0xFF22C55E)
val AccentBlue = Color(0xFF3B82F6)

private val DarkColors = darkColorScheme(
    primary = AccentBlue,
    secondary = AccentGreen,
    background = Color(0xFF0B1220),
    surface = Color(0xFF111A2B),
    onBackground = Color(0xFFF2F5F9),
    onSurface = Color(0xFFF2F5F9),
)

private val LightColors = lightColorScheme(
    primary = AccentBlue,
    secondary = AccentGreen,
    background = Color(0xFFF5F7FA),
    surface = Color.White,
    onBackground = Color(0xFF0B1220),
    onSurface = Color(0xFF0B1220),
)

@Composable
fun LcVpnTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val colors = if (darkTheme) DarkColors else LightColors
    MaterialTheme(colorScheme = colors, content = content)
}

package com.lizercool.lcvpn.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Layers
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.lizercool.lcvpn.BuildConfig
import com.lizercool.lcvpn.R
import com.lizercool.lcvpn.ui.home.HomeScreen
import com.lizercool.lcvpn.ui.servers.ServersScreen
import com.lizercool.lcvpn.ui.settings.SettingsScreen
import com.lizercool.lcvpn.ui.subscriptions.SubscriptionsScreen
import com.lizercool.lcvpn.ui.theme.LcVpnTheme
import com.lizercool.lcvpn.util.Prefs
import kotlinx.coroutines.launch

private sealed class Destination(val route: String, val icon: androidx.compose.ui.graphics.vector.ImageVector, val labelRes: Int) {
    data object Home : Destination("home", Icons.Filled.Home, R.string.nav_home)
    data object Servers : Destination("servers", Icons.Filled.Public, R.string.nav_servers)
    data object Subscriptions : Destination("subscriptions", Icons.Filled.Layers, R.string.nav_subscriptions)
    data object Settings : Destination("settings", Icons.Filled.Settings, R.string.nav_settings)
}

private val destinations = listOf(Destination.Home, Destination.Servers, Destination.Subscriptions, Destination.Settings)

@Composable
fun LcVpnRoot(
    darkTheme: Boolean,
    onRequestConnect: () -> Unit,
    onDisconnect: () -> Unit,
) {
    LcVpnTheme(darkTheme = darkTheme) {
        val navController = rememberNavController()
        val context = LocalContext.current
        val coroutineScope = rememberCoroutineScope()
        var showAnnouncement by remember { mutableStateOf(false) }

        LaunchedEffect(Unit) {
            val prefs = Prefs(context)
            showAnnouncement = !prefs.hasSeenAnnouncement(BuildConfig.VERSION_NAME)
        }

        if (showAnnouncement) {
            AlertDialog(
                onDismissRequest = { showAnnouncement = false },
                title = { Text("Объявление") },
                text = { Text("Добро пожаловать в Lizercool! Приложение в активной разработке - расскажите нам, если что-то работает не так.") },
                confirmButton = {
                    TextButton(onClick = {
                        showAnnouncement = false
                        coroutineScope.launch { Prefs(context).markAnnouncementSeen(BuildConfig.VERSION_NAME) }
                    }) { Text("Понятно") }
                },
            )
        }

        Scaffold(
            bottomBar = {
                NavigationBar {
                    val backStackEntry by navController.currentBackStackEntryAsState()
                    val currentDestination = backStackEntry?.destination
                    destinations.forEach { destination ->
                        val selected = currentDestination?.hierarchy?.any { it.route == destination.route } == true
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                navController.navigate(destination.route) {
                                    popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(destination.icon, contentDescription = null) },
                            label = { Text(stringResource(destination.labelRes)) },
                        )
                    }
                }
            },
        ) { padding ->
            NavHost(
                navController = navController,
                startDestination = Destination.Home.route,
                modifier = Modifier.padding(padding),
            ) {
                composable(Destination.Home.route) {
                    HomeScreen(onRequestConnect = onRequestConnect, onDisconnect = onDisconnect)
                }
                composable(Destination.Servers.route) { ServersScreen() }
                composable(Destination.Subscriptions.route) { SubscriptionsScreen() }
                composable(Destination.Settings.route) { SettingsScreen() }
            }
        }
    }
}

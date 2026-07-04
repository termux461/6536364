package com.lizercool.lcvpn.ui

import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.lifecycleScope
import com.lizercool.lcvpn.util.Prefs
import com.lizercool.lcvpn.vpn.LcVpnService
import com.lizercool.lcvpn.work.SubscriptionRefreshWorker
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private val vpnPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        if (result.resultCode == RESULT_OK) startVpnService()
    }

    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { /* no-op either way, the foreground notification still shows without it pre-33 */ }

    private val darkThemeState = mutableStateOf(true)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val prefs = Prefs(this)
        lifecycleScope.launch {
            prefs.darkTheme.collectLatest { darkThemeState.value = it }
        }

        SubscriptionRefreshWorker.schedulePeriodic(this)

        if (android.os.Build.VERSION.SDK_INT >= 33) {
            notificationPermissionLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS)
        }

        setContent {
            LcVpnRoot(
                darkTheme = darkThemeState.value,
                onRequestConnect = ::requestConnect,
                onDisconnect = ::disconnect,
            )
        }
    }

    private fun requestConnect() {
        val intent = VpnService.prepare(this)
        if (intent != null) {
            vpnPermissionLauncher.launch(intent)
        } else {
            startVpnService()
        }
    }

    private fun startVpnService() {
        val intent = Intent(this, LcVpnService::class.java).setAction(LcVpnService.ACTION_CONNECT)
        startForegroundService(intent)
    }

    private fun disconnect() {
        val intent = Intent(this, LcVpnService::class.java).setAction(LcVpnService.ACTION_DISCONNECT)
        startService(intent)
    }
}

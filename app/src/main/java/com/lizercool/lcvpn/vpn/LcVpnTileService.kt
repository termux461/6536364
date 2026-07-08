package com.lizercool.lcvpn.vpn

import android.app.PendingIntent
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import com.lizercool.lcvpn.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Quick Settings tile: one tap to connect/disconnect the VPN straight from the notification
 * shade. Reflects the live connection state while the shade is open.
 */
class LcVpnTileService : TileService() {

    private var scope: CoroutineScope? = null

    override fun onStartListening() {
        super.onStartListening()
        val s = CoroutineScope(Dispatchers.Main)
        scope = s
        s.launch { LcVpnService.stateFlow.collectLatest { render(it) } }
    }

    override fun onStopListening() {
        scope?.cancel()
        scope = null
        super.onStopListening()
    }

    override fun onClick() {
        super.onClick()
        val state = LcVpnService.stateFlow.value
        if (state is ConnectionState.Connected || state == ConnectionState.Connecting) {
            startService(Intent(this, LcVpnService::class.java).setAction(LcVpnService.ACTION_DISCONNECT))
            return
        }
        // First-time connect needs the system VPN consent dialog, which only an Activity can show;
        // once granted we can start the service directly from the tile.
        if (VpnService.prepare(this) == null) {
            val connect = Intent(this, LcVpnService::class.java).setAction(LcVpnService.ACTION_CONNECT)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(connect) else startService(connect)
        } else {
            val intent = Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                .putExtra(MainActivity.EXTRA_CONNECT, true)
            if (Build.VERSION.SDK_INT >= 34) {
                val pi = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_IMMUTABLE)
                startActivityAndCollapse(pi)
            } else {
                @Suppress("DEPRECATION")
                startActivityAndCollapse(intent)
            }
        }
    }

    private fun render(state: ConnectionState) {
        val tile = qsTile ?: return
        tile.state = when (state) {
            is ConnectionState.Connected -> Tile.STATE_ACTIVE
            else -> Tile.STATE_INACTIVE
        }
        tile.subtitle = when (state) {
            is ConnectionState.Connected -> "Подключено"
            ConnectionState.Connecting -> "Подключение..."
            is ConnectionState.Error -> "Ошибка"
            ConnectionState.Disconnected -> "Отключено"
        }
        tile.updateTile()
    }
}

package com.lizercool.lcvpn.ui.servers

import android.app.Application
import android.content.Intent
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.lizercool.lcvpn.data.db.AppDatabase
import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.network.ping.PingTester
import com.lizercool.lcvpn.util.Prefs
import com.lizercool.lcvpn.vpn.ConnectionState
import com.lizercool.lcvpn.vpn.LcVpnService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** A subscription's servers, shown as a section on the Servers screen. */
data class ServerGroup(val title: String, val servers: List<ServerEntity>)

class ServersViewModel(application: Application) : AndroidViewModel(application) {

    private val db = AppDatabase.get(application)
    private val prefs = Prefs(application)

    val servers: StateFlow<List<ServerEntity>> = db.serverDao().observeAll()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    /** Servers grouped under their subscription, in subscription order; ungrouped ones last. */
    val groups: StateFlow<List<ServerGroup>> =
        combine(db.serverDao().observeAll(), db.subscriptionDao().observeAll()) { servers, subs ->
            val bySub = servers.groupBy { it.subscriptionId }
            val result = mutableListOf<ServerGroup>()
            subs.forEach { sub ->
                val list = bySub[sub.id].orEmpty()
                if (list.isNotEmpty()) result += ServerGroup(sub.name, list)
            }
            // Servers whose subscription is missing/null go into a trailing catch-all group.
            val orphaned = servers.filter { s -> subs.none { it.id == s.subscriptionId } }
            if (orphaned.isNotEmpty()) result += ServerGroup("Прочие", orphaned)
            result
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _isPinging = MutableStateFlow(false)
    val isPinging: StateFlow<Boolean> = _isPinging

    fun select(server: ServerEntity) {
        viewModelScope.launch {
            db.serverDao().clearSelection()
            db.serverDao().select(server.id)
            // If the VPN is already up, switch to the newly-selected server live by asking the
            // service to restart Xray-core (and the tun bridge) with it - no manual reconnect.
            val state = LcVpnService.stateFlow.value
            if (state is ConnectionState.Connected || state is ConnectionState.Connecting) {
                val ctx = getApplication<Application>()
                val intent = Intent(ctx, LcVpnService::class.java).setAction(LcVpnService.ACTION_RECONNECT)
                runCatching { ctx.startForegroundService(intent) }
            }
        }
    }

    fun refreshPings() {
        viewModelScope.launch {
            _isPinging.value = true
            val mode = prefs.pingMode.first()
            // Each ping in proxy mode spins up a real temporary Xray-core instance and can take
            // a few seconds, so servers are pinged one at a time and the result is written as
            // soon as it's ready rather than waiting for the whole batch to finish.
            servers.value.forEach { server ->
                val ms = PingTester.pingMillis(server, mode)
                db.serverDao().updatePing(server.id, ms)
            }
            _isPinging.value = false
        }
    }
}

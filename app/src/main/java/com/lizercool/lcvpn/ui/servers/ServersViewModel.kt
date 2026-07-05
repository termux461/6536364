package com.lizercool.lcvpn.ui.servers

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.lizercool.lcvpn.data.db.AppDatabase
import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.network.ping.PingTester
import com.lizercool.lcvpn.util.Prefs
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class ServersViewModel(application: Application) : AndroidViewModel(application) {

    private val db = AppDatabase.get(application)
    private val prefs = Prefs(application)

    val servers: StateFlow<List<ServerEntity>> = db.serverDao().observeAll()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _isPinging = MutableStateFlow(false)
    val isPinging: StateFlow<Boolean> = _isPinging

    fun select(server: ServerEntity) {
        viewModelScope.launch {
            db.serverDao().clearSelection()
            db.serverDao().select(server.id)
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

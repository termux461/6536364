package com.lizercool.lcvpn.ui.servers

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.lizercool.lcvpn.data.db.AppDatabase
import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.network.ping.PingTester
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class ServersViewModel(application: Application) : AndroidViewModel(application) {

    private val db = AppDatabase.get(application)

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
            val current = servers.value
            val results = PingTester.pingAll(current)
            results.forEach { (serverId, ms) -> db.serverDao().updatePing(serverId, ms) }
            _isPinging.value = false
        }
    }
}

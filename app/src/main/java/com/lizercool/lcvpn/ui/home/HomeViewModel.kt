package com.lizercool.lcvpn.ui.home

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.lizercool.lcvpn.data.db.AppDatabase
import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.vpn.ConnectionState
import com.lizercool.lcvpn.vpn.LcVpnService
import com.lizercool.lcvpn.vpn.ProxyStats
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn

data class HomeUiState(
    val connectionState: ConnectionState = ConnectionState.Disconnected,
    val selectedServer: ServerEntity? = null,
    val stats: ProxyStats = ProxyStats(),
)

class HomeViewModel(application: Application) : AndroidViewModel(application) {

    private val db = AppDatabase.get(application)

    val uiState: StateFlow<HomeUiState> = combine(
        LcVpnService.stateFlow,
        db.serverDao().observeSelected(),
        LcVpnService.statsFlow,
    ) { connectionState, server, stats ->
        HomeUiState(connectionState, server, stats)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), HomeUiState())
}

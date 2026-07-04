package com.lizercool.lcvpn.vpn

sealed interface ConnectionState {
    data object Disconnected : ConnectionState
    data object Connecting : ConnectionState
    data class Connected(val sinceEpochMs: Long, val serverName: String) : ConnectionState
    data class Error(val message: String) : ConnectionState
}

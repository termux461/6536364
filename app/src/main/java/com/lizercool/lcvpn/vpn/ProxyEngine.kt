package com.lizercool.lcvpn.vpn

import kotlinx.coroutines.flow.StateFlow

data class ProxyStats(
    val downlinkBytesPerSec: Long = 0,
    val uplinkBytesPerSec: Long = 0,
    val totalDownlinkBytes: Long = 0,
    val totalUplinkBytes: Long = 0,
)

/**
 * Abstraction over the actual proxy core (Xray-core). [LcVpnService] talks to this interface
 * only, so the native binding can be swapped in without touching the service/UI layer.
 *
 * Current implementation: [StubProxyEngine] - builds the real outbound config and reports state,
 * but does not yet forward packets. Wired in as the very first native core lands.
 */
interface ProxyEngine {
    val stats: StateFlow<ProxyStats>

    /** Starts the proxy core with the given config (see [ConfigBuilder]). Returns the local SOCKS port used for TUN mode's tun2socks, or -1 in proxy-only mode. */
    suspend fun start(configJson: String, tunFd: Int?): Boolean

    suspend fun stop()

    fun isRunning(): Boolean
}

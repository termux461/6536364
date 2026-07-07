package com.lizercool.lcvpn.vpn

import android.content.Context
import hev.htproxy.TProxyService
import java.io.File

/**
 * JNI bridge to github.com/heiher/hev-socks5-tunnel (same library v2rayNG uses) - reads raw IP
 * packets off the VpnService tun fd and forwards them into a local SOCKS5 server (Xray-core's
 * inbound, see ConfigBuilder), which is what actually makes TUN mode route real device traffic
 * instead of just capturing it into a fd nobody reads from.
 *
 * The actual @external declarations live in [hev.htproxy.TProxyService] - that exact
 * package/class name is a hard requirement of the native library itself, not a naming choice;
 * see the comment there.
 */
object HevSocks5Tunnel {

    fun start(
        context: Context,
        tunFd: Int,
        socksPort: Int,
        mtu: Int,
        tunIpv4Client: String,
        tunIpv6Client: String? = null,
        idleTimeoutSec: Int = 300,
        socksUser: String? = null,
        socksPass: String? = null,
    ) {
        val configFile = File(context.filesDir, "hev-socks5-tunnel.yaml").apply {
            writeText(buildConfig(socksPort, mtu, tunIpv4Client, tunIpv6Client, idleTimeoutSec, socksUser, socksPass))
        }
        TProxyService.TProxyStartService(configFile.absolutePath, tunFd)
    }

    fun stop() {
        TProxyService.TProxyStopService()
    }

    private fun buildConfig(
        socksPort: Int,
        mtu: Int,
        tunIpv4Client: String,
        tunIpv6Client: String?,
        idleTimeoutSec: Int,
        socksUser: String?,
        socksPass: String?,
    ): String = buildString {
        // hev takes the read/write timeouts in milliseconds; the setting is exposed to users in
        // seconds ("Таймаут простоя"). UDP flows are short-lived so they get a quarter of it.
        val tcpTimeoutMs = idleTimeoutSec.coerceAtLeast(10) * 1000
        val udpTimeoutMs = (tcpTimeoutMs / 5).coerceAtLeast(20000)
        appendLine("tunnel:")
        appendLine("  mtu: $mtu")
        appendLine("  ipv4: $tunIpv4Client")
        // Only advertise an IPv6 client address when the VpnService actually captured IPv6 too,
        // so hev forwards those packets into the SOCKS proxy instead of dropping them.
        if (!tunIpv6Client.isNullOrEmpty()) appendLine("  ipv6: '$tunIpv6Client'")
        appendLine("socks5:")
        appendLine("  port: $socksPort")
        appendLine("  address: 127.0.0.1")
        // Must match the auth on Xray's socks-in inbound (see ConfigBuilder) - the loopback proxy
        // is password-guarded so a hostile localhost app can't use it to fingerprint the server.
        if (!socksUser.isNullOrEmpty() && !socksPass.isNullOrEmpty()) {
            appendLine("  username: '$socksUser'")
            appendLine("  password: '$socksPass'")
        }
        appendLine("  udp: 'udp'")
        appendLine("misc:")
        appendLine("  tcp-read-write-timeout: $tcpTimeoutMs")
        appendLine("  udp-read-write-timeout: $udpTimeoutMs")
        appendLine("  log-level: warn")
    }
}

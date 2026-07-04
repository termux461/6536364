package com.lizercool.lcvpn.vpn

import android.content.Context
import java.io.File

/**
 * JNI bridge to github.com/heiher/hev-socks5-tunnel (same library v2rayNG uses via its
 * TProxyService) - reads raw IP packets off the VpnService tun fd and forwards them into a
 * local SOCKS5 server (Xray-core's inbound, see ConfigBuilder), which is what actually makes
 * TUN mode route real device traffic instead of just capturing it into a fd nobody reads from.
 */
object HevSocks5Tunnel {

    init {
        System.loadLibrary("hev-socks5-tunnel")
    }

    @JvmStatic
    private external fun TProxyStartService(configPath: String, fd: Int)

    @JvmStatic
    private external fun TProxyStopService()

    @JvmStatic
    external fun TProxyGetStats(): LongArray?

    fun start(context: Context, tunFd: Int, socksPort: Int, mtu: Int, tunIpv4Client: String) {
        val configFile = File(context.filesDir, "hev-socks5-tunnel.yaml").apply {
            writeText(buildConfig(socksPort, mtu, tunIpv4Client))
        }
        TProxyStartService(configFile.absolutePath, tunFd)
    }

    fun stop() {
        TProxyStopService()
    }

    private fun buildConfig(socksPort: Int, mtu: Int, tunIpv4Client: String): String = buildString {
        appendLine("tunnel:")
        appendLine("  mtu: $mtu")
        appendLine("  ipv4: $tunIpv4Client")
        appendLine("socks5:")
        appendLine("  port: $socksPort")
        appendLine("  address: 127.0.0.1")
        appendLine("  udp: 'udp'")
        appendLine("misc:")
        appendLine("  tcp-read-write-timeout: 300000")
        appendLine("  udp-read-write-timeout: 60000")
        appendLine("  log-level: warn")
    }
}

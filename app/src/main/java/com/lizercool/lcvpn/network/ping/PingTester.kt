package com.lizercool.lcvpn.network.ping

import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.data.model.PingMode
import com.lizercool.lcvpn.data.model.TunnelMode
import com.lizercool.lcvpn.vpn.ConfigBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import libv2ray.CoreCallbackHandler
import libv2ray.Libv2ray
import okhttp3.OkHttpClient
import okhttp3.Request
import timber.log.Timber
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.TimeUnit

/**
 * Measures a server's latency using whichever [PingMode] the user picked in Settings:
 * - TCP: bare TCP connect to address:port, outside the tunnel - fast but can misreport a working
 *   REALITY/censorship-resistant server as dead if the ISP blocks raw TCP to its IP specifically.
 * - ICMP: shells out to the system `ping` binary (apps can send raw ICMP via the AID_INET group,
 *   no root needed) - also outside the tunnel, but ICMP is sometimes let through by the same ISPs
 *   that block or throttle raw TCP to VPN endpoints.
 * - PROXY_HEAD/PROXY_GET: actually establishes this server's VLESS/REALITY connection through a
 *   temporary Xray-core instance and times an HTTP request through it - same approach v2rayNG's
 *   own delay test uses. Slower (a real Xray-core start/stop per server) but reflects real usable
 *   latency.
 */
object PingTester {

    private const val PROBE_URL = "https://cp.cloudflare.com/generate_204"
    private const val DEFAULT_TIMEOUT_MS = 8000L

    suspend fun pingMillis(server: ServerEntity, mode: PingMode, timeoutMs: Long = DEFAULT_TIMEOUT_MS): Int? =
        withContext(Dispatchers.IO) {
            withTimeoutOrNull(timeoutMs) {
                when (mode) {
                    PingMode.TCP -> measureTcp(server, timeoutMs)
                    PingMode.ICMP -> measureIcmp(server, timeoutMs)
                    PingMode.PROXY_HEAD -> measureProxy(server, useHead = true)
                    PingMode.PROXY_GET -> measureProxy(server, useHead = false)
                }
            }
        }

    private fun measureTcp(server: ServerEntity, timeoutMs: Long): Int? = runCatching {
        val start = System.currentTimeMillis()
        Socket().use { it.connect(InetSocketAddress(server.address, server.port), timeoutMs.toInt()) }
        (System.currentTimeMillis() - start).toInt()
    }.getOrElse {
        Timber.d(it, "Ping(TCP): %s failed", server.name)
        null
    }

    private fun measureIcmp(server: ServerEntity, timeoutMs: Long): Int? = runCatching {
        val timeoutSec = maxOf(1, (timeoutMs / 1000).toInt())
        val process = ProcessBuilder("/system/bin/ping", "-c", "1", "-W", timeoutSec.toString(), server.address)
            .redirectErrorStream(true)
            .start()
        val output = process.inputStream.bufferedReader().readText()
        process.waitFor()
        Regex("time[=<]([0-9.]+)").find(output)?.groupValues?.get(1)?.toFloat()?.toInt()
    }.getOrElse {
        Timber.d(it, "Ping(ICMP): %s failed", server.name)
        null
    }

    private fun measureProxy(server: ServerEntity, useHead: Boolean): Int? {
        val port = runCatching { findFreeLoopbackPort() }.getOrNull() ?: return null
        val configJson = ConfigBuilder.build(server, TunnelMode.PROXY, port)

        val callback = object : CoreCallbackHandler {
            override fun startup(): Long = 0
            override fun shutdown(): Long = 0
            override fun onEmitStatus(code: Long, message: String?): Long = 0
        }
        val controller = runCatching { Libv2ray.newCoreController(callback) }
            .onFailure { Timber.w(it, "Ping: failed to create CoreController for %s", server.name) }
            .getOrNull() ?: return null

        return try {
            runCatching { controller.startLoop(configJson, 0) }
                .onFailure { Timber.d(it, "Ping: %s failed to start", server.name) }
                .getOrNull() ?: return null

            val client = OkHttpClient.Builder()
                .proxy(Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", port)))
                .connectTimeout(6, TimeUnit.SECONDS)
                .readTimeout(6, TimeUnit.SECONDS)
                .build()
            val requestBuilder = Request.Builder().url(PROBE_URL)
            if (useHead) requestBuilder.head()
            val request = requestBuilder.build()

            val start = System.currentTimeMillis()
            runCatching {
                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful && response.code !in 200..399) error("HTTP ${response.code}")
                }
                (System.currentTimeMillis() - start).toInt()
            }.getOrElse {
                Timber.d(it, "Ping: %s request failed", server.name)
                null
            }
        } finally {
            runCatching { controller.stopLoop() }
        }
    }

    private fun findFreeLoopbackPort(): Int =
        ServerSocket(0, 1, java.net.InetAddress.getByName("127.0.0.1")).use { it.localPort }
}

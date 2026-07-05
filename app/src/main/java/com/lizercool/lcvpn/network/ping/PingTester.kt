package com.lizercool.lcvpn.network.ping

import com.lizercool.lcvpn.data.db.entity.ServerEntity
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
import java.util.concurrent.TimeUnit

/**
 * Measures real usable latency by actually establishing this server's VLESS/REALITY connection
 * through a temporary Xray-core instance and timing an HTTP request through it - same approach
 * v2rayNG's own delay test uses. A bare TCP connect (the previous implementation) isn't good
 * enough here: a provider can legitimately drop raw TCP to a REALITY/censorship-resistant
 * endpoint from outside the tunnel while the actual proxied connection still works fine once
 * established, so that test was reporting a lot of working servers as unreachable.
 */
object PingTester {

    private const val PROBE_URL = "https://cp.cloudflare.com/generate_204"
    private const val DEFAULT_TIMEOUT_MS = 8000L

    suspend fun pingMillis(server: ServerEntity, timeoutMs: Long = DEFAULT_TIMEOUT_MS): Int? =
        withContext(Dispatchers.IO) {
            withTimeoutOrNull(timeoutMs) { measure(server) }
        }

    private fun measure(server: ServerEntity): Int? {
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
            val request = Request.Builder().url(PROBE_URL).build()

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

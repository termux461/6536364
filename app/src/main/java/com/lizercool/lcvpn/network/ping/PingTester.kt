package com.lizercool.lcvpn.network.ping

import com.lizercool.lcvpn.data.db.entity.ServerEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import java.net.InetSocketAddress
import java.net.Socket

/** TCP-connect latency test (ms) - a reasonable proxy for "is this server reachable and how fast". */
object PingTester {

    suspend fun pingMillis(server: ServerEntity, timeoutMs: Int = 3000): Int? = withContext(Dispatchers.IO) {
        runCatching {
            val start = System.currentTimeMillis()
            Socket().use { socket ->
                socket.connect(InetSocketAddress(server.address, server.port), timeoutMs)
            }
            (System.currentTimeMillis() - start).toInt()
        }.getOrNull()
    }

    suspend fun pingAll(servers: List<ServerEntity>, timeoutMs: Int = 3000): Map<Long, Int?> = coroutineScope {
        servers.associate { server ->
            server.id to async { pingMillis(server, timeoutMs) }
        }.mapValues { it.value.await() }
    }
}

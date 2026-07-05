package com.lizercool.lcvpn.vpn

import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.data.model.ProxyProtocol
import com.lizercool.lcvpn.data.model.TunnelMode
import org.json.JSONArray
import org.json.JSONObject

/**
 * Builds an Xray-core style JSON config for a given server profile. Kept separate from
 * [ProxyEngine] so it can be unit-tested without touching Android/VpnService plumbing, and so
 * the actual core binding (whichever it ends up being) just needs a config string + a tun fd.
 */
object ConfigBuilder {

    /** Tag prefix shared by every per-server outbound in [buildAuto] - BurstObservatory and the
     *  balancer both select on this prefix, so it must stay in sync between the two. */
    private const val AUTO_TAG_PREFIX = "auto-"
    private const val AUTO_BALANCER_TAG = "auto-balancer"
    private const val PROBE_URL = "https://www.gstatic.com/generate_204"

    fun build(
        server: ServerEntity,
        tunnelMode: TunnelMode,
        socksPort: Int,
        lanProxyPort: Int = 0,
        lanProxyPassword: String? = null,
    ): String = buildRoot(tunnelMode, socksPort, lanProxyPort, lanProxyPassword) { root ->
        val outbounds = JSONArray()
        outbounds.put(buildOutbound(server, "proxy"))
        outbounds.put(JSONObject().put("tag", "direct").put("protocol", "freedom"))
        outbounds.put(JSONObject().put("tag", "block").put("protocol", "blackhole"))
        root.put("outbounds", outbounds)
    }

    /**
     * Builds a config where every server gets its own outbound, and Xray-core's own
     * BurstObservatory continuously pings all of them and routes traffic through whichever
     * currently has the lowest latency - auto-selecting the best server instead of pinning to
     * one manually picked one.
     */
    fun buildAuto(
        servers: List<ServerEntity>,
        tunnelMode: TunnelMode,
        socksPort: Int,
        lanProxyPort: Int = 0,
        lanProxyPassword: String? = null,
    ): String = buildRoot(tunnelMode, socksPort, lanProxyPort, lanProxyPassword) { root ->
        val outbounds = JSONArray()
        servers.forEachIndexed { index, server ->
            outbounds.put(buildOutbound(server, "$AUTO_TAG_PREFIX$index"))
        }
        outbounds.put(JSONObject().put("tag", "direct").put("protocol", "freedom"))
        outbounds.put(JSONObject().put("tag", "block").put("protocol", "blackhole"))
        root.put("outbounds", outbounds)

        root.put(
            "burstObservatory",
            JSONObject()
                .put("subjectSelector", JSONArray().put(AUTO_TAG_PREFIX))
                .put(
                    "pingConfig",
                    JSONObject()
                        .put("destination", PROBE_URL)
                        .put("interval", "1m")
                        .put("timeout", "10s")
                        .put("sampling", 2),
                ),
        )
        root.put(
            "routing",
            JSONObject()
                .put("domainStrategy", "AsIs")
                .put(
                    "balancers",
                    JSONArray().put(
                        JSONObject()
                            .put("tag", AUTO_BALANCER_TAG)
                            .put("selector", JSONArray().put(AUTO_TAG_PREFIX))
                            .put("strategy", JSONObject().put("type", "leastPing")),
                    ),
                )
                .put(
                    "rules",
                    JSONArray().put(
                        JSONObject()
                            .put("type", "field")
                            .put("network", "tcp,udp")
                            .put("balancerTag", AUTO_BALANCER_TAG),
                    ),
                ),
        )
    }

    private inline fun buildRoot(
        tunnelMode: TunnelMode,
        socksPort: Int,
        lanProxyPort: Int,
        lanProxyPassword: String?,
        putOutbounds: (JSONObject) -> Unit,
    ): String {
        val root = JSONObject()
        root.put("log", JSONObject().put("loglevel", "warning"))

        val inbounds = JSONArray()
        inbounds.put(
            JSONObject()
                .put("tag", "socks-in")
                .put("port", socksPort)
                .put("listen", "127.0.0.1")
                .put("protocol", "socks")
                .put("settings", JSONObject().put("udp", true)),
        )
        if (tunnelMode == TunnelMode.TUN_AND_PROXY && lanProxyPort > 0 && !lanProxyPassword.isNullOrEmpty()) {
            inbounds.put(
                JSONObject()
                    .put("tag", "socks-in-lan")
                    .put("port", lanProxyPort)
                    .put("listen", "0.0.0.0")
                    .put("protocol", "socks")
                    .put(
                        "settings",
                        JSONObject()
                            .put("udp", true)
                            .put("auth", "password")
                            .put(
                                "accounts",
                                JSONArray().put(
                                    JSONObject().put("user", "lcvpn").put("pass", lanProxyPassword),
                                ),
                            ),
                    ),
            )
        }
        root.put("inbounds", inbounds)

        putOutbounds(root)

        // Needed for CoreController.queryAllOutboundTrafficStats() to return real numbers.
        root.put("stats", JSONObject())
        root.put(
            "policy",
            JSONObject().put(
                "system",
                JSONObject()
                    .put("statsOutboundUplink", true)
                    .put("statsOutboundDownlink", true),
            ),
        )

        return root.toString()
    }

    private fun buildOutbound(server: ServerEntity, tag: String): JSONObject {
        return when (server.protocol) {
            ProxyProtocol.HYSTERIA2 -> buildHysteria2Outbound(server, tag)
            else -> buildVlessOutbound(server, tag)
        }
    }

    private fun buildVlessOutbound(server: ServerEntity, tag: String): JSONObject {
        val user = JSONObject()
            .put("id", server.uuid)
            .put("encryption", "none")
        server.flow?.let { user.put("flow", it) }

        val vnextEntry = JSONObject()
            .put("address", server.address)
            .put("port", server.port)
            .put("users", JSONArray().put(user))

        val settings = JSONObject().put("vnext", JSONArray().put(vnextEntry))

        val streamSettings = JSONObject().put("network", server.network)
        when (server.protocol) {
            ProxyProtocol.VLESS_REALITY -> {
                streamSettings.put("security", "reality")
                streamSettings.put(
                    "realitySettings",
                    JSONObject()
                        .put("serverName", server.sni)
                        .put("publicKey", server.realityPublicKey)
                        .put("shortId", server.realityShortId ?: "")
                        .put("fingerprint", server.realityFingerprint ?: "chrome"),
                )
            }
            ProxyProtocol.VLESS_TLS -> {
                streamSettings.put("security", "tls")
                streamSettings.put("tlsSettings", JSONObject().put("serverName", server.sni ?: server.address))
            }
            else -> streamSettings.put("security", "none")
        }
        when (server.network) {
            "ws" -> streamSettings.put(
                "wsSettings",
                JSONObject()
                    .put("path", server.wsPath ?: "/")
                    .put("headers", JSONObject().put("Host", server.wsHost ?: server.sni ?: server.address)),
            )
            "xhttp" -> {
                val xhttpSettings = JSONObject()
                    .put("path", server.wsPath ?: "/")
                    .put("host", server.wsHost ?: server.sni ?: server.address)
                    .put("mode", server.xhttpMode ?: "auto")
                server.xhttpExtraJson?.let { extra ->
                    runCatching { JSONObject(extra) }.onSuccess { xhttpSettings.put("extra", it) }
                }
                streamSettings.put("xhttpSettings", xhttpSettings)
            }
        }

        return JSONObject()
            .put("tag", tag)
            .put("protocol", "vless")
            .put("settings", settings)
            .put("streamSettings", streamSettings)
    }

    private fun buildHysteria2Outbound(server: ServerEntity, tag: String): JSONObject {
        // NOTE: mainline Xray-core does not natively speak Hysteria2 at the time this was
        // written. This shape mirrors sing-box's hysteria2 outbound and is here so the rest of
        // the pipeline (server list, selection, connect flow) works end-to-end; it will need to
        // be swapped in for whatever core we actually end up embedding for this protocol -
        // see the ProxyEngine TODO.
        val settings = JSONObject()
            .put("server", server.address)
            .put("server_port", server.port)
            .put("password", server.hysteria2Password)
        server.sni?.let { settings.put("tls", JSONObject().put("server_name", it)) }
        server.hysteria2Obfs?.let {
            settings.put("obfs", JSONObject().put("type", "salamander").put("password", it))
        }

        return JSONObject()
            .put("tag", tag)
            .put("protocol", "hysteria2")
            .put("settings", settings)
    }
}

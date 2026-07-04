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

    fun build(server: ServerEntity, tunnelMode: TunnelMode, socksPort: Int): String {
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
        root.put("inbounds", inbounds)

        val outbounds = JSONArray()
        outbounds.put(buildOutbound(server))
        outbounds.put(JSONObject().put("tag", "direct").put("protocol", "freedom"))
        outbounds.put(JSONObject().put("tag", "block").put("protocol", "blackhole"))
        root.put("outbounds", outbounds)

        return root.toString()
    }

    private fun buildOutbound(server: ServerEntity): JSONObject {
        return when (server.protocol) {
            ProxyProtocol.HYSTERIA2 -> buildHysteria2Outbound(server)
            else -> buildVlessOutbound(server)
        }
    }

    private fun buildVlessOutbound(server: ServerEntity): JSONObject {
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
            .put("tag", "proxy")
            .put("protocol", "vless")
            .put("settings", settings)
            .put("streamSettings", streamSettings)
    }

    private fun buildHysteria2Outbound(server: ServerEntity): JSONObject {
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
            .put("tag", "proxy")
            .put("protocol", "hysteria2")
            .put("settings", settings)
    }
}

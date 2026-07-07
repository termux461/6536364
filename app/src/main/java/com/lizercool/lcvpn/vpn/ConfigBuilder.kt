package com.lizercool.lcvpn.vpn

import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.data.model.AntiDpiOptions
import com.lizercool.lcvpn.data.model.ProxyProtocol
import com.lizercool.lcvpn.data.model.RoutingMode
import com.lizercool.lcvpn.data.model.RoutingOptions
import com.lizercool.lcvpn.data.model.TunnelMode
import com.lizercool.lcvpn.util.GeoAssets
import org.json.JSONArray
import org.json.JSONObject
import timber.log.Timber

/**
 * Builds an Xray-core style JSON config for a given server profile. Kept separate from
 * [ProxyEngine] so it can be unit-tested without touching Android/VpnService plumbing, and so
 * the actual core binding (whichever it ends up being) just needs a config string + a tun fd.
 */
object ConfigBuilder {

    fun build(
        server: ServerEntity,
        tunnelMode: TunnelMode,
        socksPort: Int,
        lanProxyPort: Int = 0,
        lanProxyPassword: String? = null,
        // Whether to emit "geosite:"/"geoip:" routing rules. Defaults to whatever GeoAssets found
        // on disk, but the connect path can force it false to retry after the geo-enabled config
        // failed to start the core (see LcVpnService), so a device with unusable geodata still
        // connects with degraded (proxy-everything) routing instead of failing outright.
        geoRouting: Boolean = GeoAssets.available,
        // Ping/latency probes only need to reach the proxy - they don't care about ad-block or
        // RU-split routing, and pulling in geodata just makes the core slower to start and able to
        // fail for reasons unrelated to whether the server itself is reachable. When true, routing
        // collapses to a single "everything through the proxy" rule with no geo dependency at all.
        minimalRouting: Boolean = false,
        // Advanced tuning (Расширенные настройки).
        sniffing: Boolean = true,
        blockUdp: Boolean = false,
        // Optional username/password guarding the internal 127.0.0.1 SOCKS inbound. Without it a
        // malicious app on the same device can connect to that loopback port directly (bypassing
        // the Android VPN service / per-app split-tunnel / Knox-Shelter-Island isolation) and use
        // it to discover the VPN server's real IP - the runetfreedom disclosure. hev-socks5-tunnel
        // is handed the same creds so the real tunnel still works.
        socksUser: String? = null,
        socksPass: String? = null,
        // Routing + anti-DPI/mux choices (Маршрутизация / Анти-DPI). Only applied to configs we
        // build ourselves; panel-authored Автовыбор configs are used as authored.
        routing: RoutingOptions = RoutingOptions(),
        antiDpi: AntiDpiOptions = AntiDpiOptions(),
    ): String {
        // Panel-authored full configs (Автовыбор profiles) carry their own routing/balancers -
        // geoRouting/minimalRouting/blockUdp/routing/antiDpi don't apply, the config is used as
        // authored (only our inbounds + sniffing preference are swapped in).
        server.fullConfigJson?.let {
            return buildFromFullConfig(it, tunnelMode, socksPort, lanProxyPort, lanProxyPassword, sniffing, socksUser, socksPass)
        }
        return buildRoot(tunnelMode, socksPort, lanProxyPort, lanProxyPassword, sniffing, socksUser, socksPass) { root ->
            val outbounds = JSONArray()
            outbounds.put(buildOutbound(server, "proxy", antiDpi))
            // A freedom outbound that fragments the TLS ClientHello to slip past DPI; the proxy
            // outbound dials through it via sockopt.dialerProxy (see buildVlessOutbound).
            if (antiDpi.fragmentEnabled) outbounds.put(buildFragmentOutbound(antiDpi))
            outbounds.put(JSONObject().put("tag", "direct").put("protocol", "freedom"))
            outbounds.put(JSONObject().put("tag", "block").put("protocol", "blackhole"))
            root.put("outbounds", outbounds)

            root.put("routing", buildRouting(geo = geoRouting, minimal = minimalRouting, blockUdp = blockUdp, routing = routing))
        }
    }

    private fun buildFragmentOutbound(antiDpi: AntiDpiOptions): JSONObject =
        JSONObject()
            .put("tag", "fragment")
            .put("protocol", "freedom")
            .put(
                "settings",
                JSONObject().put(
                    "fragment",
                    JSONObject()
                        .put("packets", antiDpi.fragmentPackets.ifBlank { "tlshello" })
                        .put("length", antiDpi.fragmentLength.ifBlank { "100-200" })
                        .put("interval", antiDpi.fragmentInterval.ifBlank { "10-20" }),
                ),
            )

    /**
     * Adapts a complete panel-authored client config (an Автовыбор profile with a leastLoad
     * balancer + burstObservatory, or any other xray-json subscription entry) for use here:
     * its outbounds/routing/balancers/observatory are kept exactly as authored - that IS the
     * auto-select logic - while the inbounds are replaced with ours (the panel's assume fixed
     * ports 10808/10809; we bind a dynamic loopback port and optionally the LAN proxy).
     */
    private fun buildFromFullConfig(
        configJson: String,
        tunnelMode: TunnelMode,
        socksPort: Int,
        lanProxyPort: Int,
        lanProxyPassword: String?,
        sniffing: Boolean,
        socksUser: String?,
        socksPass: String?,
    ): String {
        val root = JSONObject(configJson)
        // The panel template's log block may point at file paths that don't exist on Android.
        root.put("log", JSONObject().put("loglevel", "warning"))
        root.put("inbounds", buildInbounds(tunnelMode, socksPort, lanProxyPort, lanProxyPassword, sniffing, socksUser, socksPass))

        // Traffic counters for the speed/usage UI (harmless if the config already has them).
        if (!root.has("stats")) root.put("stats", JSONObject())
        val policy = root.optJSONObject("policy") ?: JSONObject()
        val system = policy.optJSONObject("system") ?: JSONObject()
        system.put("statsOutboundUplink", true)
        system.put("statsOutboundDownlink", true)
        policy.put("system", system)
        root.put("policy", policy)

        return root.toString()
    }

    /**
     * Common routing shape: block ads/torrent trackers, keep Russian services and anything
     * geolocated inside Russia going direct (no point tunnelling traffic that isn't blocked),
     * then send everything else through the proxy. Mirrors the routing template the Remnawave
     * panel itself ships in its own exported configs.
     */
    private fun buildRouting(
        geo: Boolean,
        minimal: Boolean,
        blockUdp: Boolean = false,
        routing: RoutingOptions = RoutingOptions(),
    ): JSONObject {
        // Latency probes: route everything straight through the proxy, nothing else. No geo, no
        // RU bypass - the whole point is to time a request that actually traverses the tunnel.
        if (minimal) {
            val rules = JSONArray().put(
                JSONObject().put("type", "field").put("network", "tcp,udp").put("outboundTag", "proxy"),
            )
            return JSONObject().put("domainStrategy", "AsIs").put("rules", rules)
        }

        val global = routing.mode == RoutingMode.GLOBAL
        // Xray-core refuses to start on a config whose "geosite:"/"geoip:" rules can't resolve
        // their .dat files, so those rules are only emitted when the caller confirmed the files
        // are on disk - otherwise routing degrades to regexp-only RU bypass + proxy-everything.
        // Every rule carries "type":"field" - Xray-core rejects routing rules without it.
        val rules = JSONArray()
        // Optional: drop all UDP (breaks QUIC/DoU/games/voice - some users want it to force
        // everything onto TCP-based tunnels). Placed first so it wins over the rules below.
        if (blockUdp) {
            rules.put(JSONObject().put("type", "field").put("network", "udp").put("outboundTag", "block"))
        }
        // User's explicit "always through VPN" domains win over everything below.
        if (routing.proxyDomains.isNotEmpty()) {
            rules.put(JSONObject().put("type", "field").put("domain", JSONArray(routing.proxyDomains.map { normalizeDomain(it) })).put("outboundTag", "proxy"))
        }
        // User's explicit "bypass" domains go direct.
        if (routing.directDomains.isNotEmpty()) {
            rules.put(JSONObject().put("type", "field").put("domain", JSONArray(routing.directDomains.map { normalizeDomain(it) })).put("outboundTag", "direct"))
        }
        // GLOBAL mode: no ad-block, no RU bypass - just LAN/private stays off-tunnel and the rest
        // is proxied. SMART mode (default) keeps the panel-style RU-direct + ad-block behaviour.
        if (!global && geo) {
            rules.put(
                JSONObject()
                    .put("type", "field")
                    .put("domain", JSONArray().put("geosite:category-ads-all"))
                    .put("outboundTag", "block"),
            )
        }
        val directDomains = JSONArray()
        if (!global && geo) {
            directDomains.put("geosite:private")
            directDomains.put("geosite:category-ru")
        }
        if (!global) {
            directDomains.put("regexp:.*\\.ru$")
            directDomains.put("regexp:.*\\.su$")
            directDomains.put("regexp:.*\\.рф$")
        }
        if (directDomains.length() > 0) {
            rules.put(JSONObject().put("type", "field").put("domain", directDomains).put("outboundTag", "direct"))
        }
        // Private/LAN IPs always go direct (even in GLOBAL) so localhost and the local network
        // aren't pointlessly tunnelled; RU geoip only in SMART.
        val directIps = JSONArray().put("geoip:private")
        if (!global && geo) directIps.put("geoip:ru")
        if (geo) {
            rules.put(JSONObject().put("type", "field").put("ip", directIps).put("outboundTag", "direct"))
        }
        rules.put(JSONObject().put("type", "field").put("network", "tcp,udp").put("outboundTag", "proxy"))

        return JSONObject()
            .put("domainStrategy", "IPIfNonMatch")
            .put("domainMatcher", "hybrid")
            .put("rules", rules)
    }

    /** Bare domains get Xray's "domain:" matcher; entries with a matcher prefix are left as-is. */
    private fun normalizeDomain(raw: String): String {
        val d = raw.trim()
        val hasPrefix = d.startsWith("domain:") || d.startsWith("full:") || d.startsWith("regexp:") ||
            d.startsWith("geosite:") || d.startsWith("keyword:")
        return if (hasPrefix) d else "domain:$d"
    }

    private inline fun buildRoot(
        tunnelMode: TunnelMode,
        socksPort: Int,
        lanProxyPort: Int,
        lanProxyPassword: String?,
        sniffing: Boolean,
        socksUser: String?,
        socksPass: String?,
        putOutboundsAndRouting: (JSONObject) -> Unit,
    ): String {
        val root = JSONObject()
        root.put("log", JSONObject().put("loglevel", "warning"))
        root.put(
            "dns",
            JSONObject()
                .put("servers", JSONArray().put("1.1.1.1").put("1.0.0.1"))
                .put("queryStrategy", "UseIP"),
        )

        root.put("inbounds", buildInbounds(tunnelMode, socksPort, lanProxyPort, lanProxyPassword, sniffing, socksUser, socksPass))

        putOutboundsAndRouting(root)

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

    private fun buildInbounds(
        tunnelMode: TunnelMode,
        socksPort: Int,
        lanProxyPort: Int,
        lanProxyPassword: String?,
        sniffingEnabled: Boolean,
        socksUser: String?,
        socksPass: String?,
    ): JSONArray {
        // Sniffing recovers the destination domain from TLS/HTTP/QUIC handshakes - without it a
        // SOCKS inbound only ever sees bare IPs, so every domain-based routing rule (geosite
        // ad-block, RU bypass, the balancer selectors in Автовыбор configs) silently misses.
        // Exposed as a setting because on rare networks it can interfere; default on.
        val sniffing = JSONObject()
            .put("enabled", sniffingEnabled)
            .put("destOverride", JSONArray().put("http").put("tls").put("quic"))

        // Password-guard the loopback SOCKS inbound when creds were supplied (the real tunnel),
        // so a hostile localhost app can't ride it to fingerprint the VPN server's IP.
        val socksInSettings = JSONObject().put("udp", true)
        if (!socksUser.isNullOrEmpty() && !socksPass.isNullOrEmpty()) {
            socksInSettings
                .put("auth", "password")
                .put("accounts", JSONArray().put(JSONObject().put("user", socksUser).put("pass", socksPass)))
        }

        val inbounds = JSONArray()
        inbounds.put(
            JSONObject()
                .put("tag", "socks-in")
                .put("port", socksPort)
                .put("listen", "127.0.0.1")
                .put("protocol", "socks")
                .put("settings", socksInSettings)
                .put("sniffing", sniffing),
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
                    )
                    .put("sniffing", sniffing),
            )
        }
        return inbounds
    }

    private fun buildOutbound(server: ServerEntity, tag: String, antiDpi: AntiDpiOptions = AntiDpiOptions()): JSONObject {
        return when (server.protocol) {
            ProxyProtocol.HYSTERIA2 -> buildHysteria2Outbound(server, tag)
            else -> buildVlessOutbound(server, tag, antiDpi)
        }
    }

    private fun buildVlessOutbound(server: ServerEntity, tag: String, antiDpi: AntiDpiOptions): JSONObject {
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
                // "extra" carries the panel's advanced xhttp knobs (xmux, downloadSettings,
                // headers, ...) as a nested JSON object, exactly as Xray-core expects it.
                server.xhttpExtraJson?.let { extra ->
                    runCatching { JSONObject(extra) }
                        .onSuccess { xhttpSettings.put("extra", it) }
                        .onFailure { Timber.w(it, "Bad xhttp 'extra' JSON for %s, ignoring", server.name) }
                }
                streamSettings.put("xhttpSettings", xhttpSettings)
            }
        }

        // Anti-DPI: dial the proxy through the fragment outbound so its TLS ClientHello is split.
        if (antiDpi.fragmentEnabled) {
            streamSettings.put("sockopt", JSONObject().put("dialerProxy", "fragment"))
        }

        val outbound = JSONObject()
            .put("tag", tag)
            .put("protocol", "vless")
            .put("settings", settings)
            .put("streamSettings", streamSettings)

        // Mux multiplexes many streams over one connection - fewer handshakes, but can hurt
        // throughput; opt-in. XUDP is what carries UDP (QUIC etc.) over the mux link.
        if (antiDpi.muxEnabled) {
            outbound.put(
                "mux",
                JSONObject()
                    .put("enabled", true)
                    .put("concurrency", antiDpi.muxConcurrency.coerceIn(1, 128))
                    .put("xudpConcurrency", 8)
                    .put("xudpProxyUDP443", "reject"),
            )
        }
        return outbound
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

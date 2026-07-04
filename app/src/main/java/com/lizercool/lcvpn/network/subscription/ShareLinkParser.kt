package com.lizercool.lcvpn.network.subscription

import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.data.model.ProxyProtocol
import java.net.URI
import java.net.URLDecoder

/**
 * Parses individual share links (the "vless://...", "hysteria2://..." lines you get out of a
 * decoded Xray/sing-box-style subscription body) into a [ServerEntity].
 *
 * This is the generic/lowest-common-denominator format almost every panel (Remnawave included)
 * falls back to for an unrecognized client User-Agent. Once we see the actual JSON your panel
 * returns for the "Lizercool" client we can add a dedicated parser next to this one.
 */
object ShareLinkParser {

    fun parse(rawLine: String, subscriptionId: Long?): ServerEntity? {
        val line = rawLine.trim()
        return runCatching {
            when {
                line.startsWith("vless://") -> parseVless(line, subscriptionId)
                line.startsWith("hysteria2://") || line.startsWith("hy2://") -> parseHysteria2(line, subscriptionId)
                else -> null
            }
        }.getOrNull()
    }

    private fun parseVless(line: String, subscriptionId: Long?): ServerEntity {
        val uri = URI(line)
        val uuid = uri.userInfo
        val host = uri.host
        val port = if (uri.port > 0) uri.port else 443
        val params = queryParams(uri.rawQuery)
        val name = decodeFragment(uri.rawFragment) ?: host

        val security = params["security"]?.lowercase()
        val network = params["type"]?.lowercase() ?: "tcp"
        val protocol = when {
            security == "reality" -> ProxyProtocol.VLESS_REALITY
            network == "ws" -> ProxyProtocol.VLESS_WS
            security == "tls" -> ProxyProtocol.VLESS_TLS
            else -> ProxyProtocol.VLESS_TCP
        }

        return ServerEntity(
            subscriptionId = subscriptionId,
            name = name,
            countryFlagEmoji = "",
            protocol = protocol,
            address = host,
            port = port,
            uuid = uuid,
            flow = params["flow"],
            network = network,
            wsPath = params["path"],
            wsHost = params["host"],
            sni = params["sni"],
            realityPublicKey = params["pbk"],
            realityShortId = params["sid"],
            realityFingerprint = params["fp"],
        )
    }

    private fun parseHysteria2(line: String, subscriptionId: Long?): ServerEntity {
        val uri = URI(line)
        val password = uri.userInfo
        val host = uri.host
        val port = if (uri.port > 0) uri.port else 443
        val params = queryParams(uri.rawQuery)
        val name = decodeFragment(uri.rawFragment) ?: host

        return ServerEntity(
            subscriptionId = subscriptionId,
            name = name,
            countryFlagEmoji = "",
            protocol = ProxyProtocol.HYSTERIA2,
            address = host,
            port = port,
            sni = params["sni"],
            hysteria2Password = password,
            hysteria2Obfs = params["obfs-password"] ?: params["obfs"],
        )
    }

    private fun queryParams(rawQuery: String?): Map<String, String> {
        if (rawQuery.isNullOrBlank()) return emptyMap()
        return rawQuery.split("&").mapNotNull { pair ->
            val idx = pair.indexOf('=')
            if (idx < 0) return@mapNotNull null
            val key = pair.substring(0, idx)
            val value = URLDecoder.decode(pair.substring(idx + 1), "UTF-8")
            key to value
        }.toMap()
    }

    private fun decodeFragment(rawFragment: String?): String? =
        rawFragment?.let { runCatching { URLDecoder.decode(it, "UTF-8") }.getOrNull() }
}

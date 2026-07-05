package com.lizercool.lcvpn.network.subscription

import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.data.model.ProxyProtocol
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import timber.log.Timber
import android.util.Base64

/**
 * Parser for the sub.lizercoolvpn.space subscription endpoint. Handles, in priority order:
 *
 *  1. xray-json format: a JSON array of complete Xray client configs (each with "remarks" +
 *     "outbounds", optionally routing/balancers/burstObservatory) - this is how the panel
 *     delivers the Автовыбор profiles, which are inexpressible as share links because they
 *     bundle every server as an outbound behind a leastLoad balancer. The whole config is kept
 *     verbatim in [ServerEntity.fullConfigJson].
 *  2. base64 body of newline-separated "vless://..." share links (the panel's default format).
 *  3. A generic JSON array of host objects with a "link"/"url" field, kept as a fallback.
 */
object SubscriptionBodyParser {

    private val json = Json { ignoreUnknownKeys = true }

    fun parseServers(body: String, subscriptionId: Long?): List<ServerEntity> {
        val trimmed = body.trim()
        if (trimmed.isEmpty()) return emptyList()

        // Raw JSON (xray-json full configs or host-object arrays).
        if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
            runCatching { parseJson(trimmed, subscriptionId) }
                .onSuccess { if (it.isNotEmpty()) return it }
                .onFailure { Timber.w(it, "Subscription body looked like JSON but did not match the expected shape") }
        }

        // Base64 body - decodes to either share links or (some panels) the same JSON as above.
        val decoded = runCatching {
            String(Base64.decode(trimmed, Base64.DEFAULT))
        }.getOrElse { trimmed } // maybe it wasn't base64-encoded at all, treat as plain text

        val decodedTrimmed = decoded.trim()
        if (decodedTrimmed.startsWith("{") || decodedTrimmed.startsWith("[")) {
            runCatching { parseJson(decodedTrimmed, subscriptionId) }
                .onSuccess { if (it.isNotEmpty()) return it }
                .onFailure { Timber.w(it, "Decoded subscription body looked like JSON but did not match the expected shape") }
        }

        val links = decoded.lines().map { it.trim() }.filter { it.isNotEmpty() }
        val servers = links.mapNotNull { ShareLinkParser.parse(it, subscriptionId) }
        if (servers.isEmpty() && links.isNotEmpty()) {
            Timber.w("Decoded subscription body but none of the %d lines matched a known share-link format", links.size)
        }
        return servers
    }

    private fun parseJson(text: String, subscriptionId: Long?): List<ServerEntity> {
        val element = json.parseToJsonElement(text)

        // A single full config delivered as one object.
        if (element is JsonObject && element["outbounds"] is JsonArray) {
            return listOfNotNull(parseFullConfig(element, subscriptionId))
        }

        val hostArray: JsonArray = when {
            element is JsonArray -> element
            element is JsonObject && element["servers"] is JsonArray -> element["servers"]!!.jsonArray
            element is JsonObject && element["hosts"] is JsonArray -> element["hosts"]!!.jsonArray
            else -> return emptyList()
        }

        return hostArray.mapNotNull { entry ->
            val obj = entry as? JsonObject ?: return@mapNotNull null
            if (obj["outbounds"] is JsonArray) return@mapNotNull parseFullConfig(obj, subscriptionId)
            val link = obj["link"]?.jsonPrimitive?.content
                ?: obj["url"]?.jsonPrimitive?.content
                ?: obj["config"]?.jsonPrimitive?.content
            link?.let { ShareLinkParser.parse(it, subscriptionId) }
        }
    }

    /**
     * Wraps one complete Xray client config into a ServerEntity. The address/port/protocol
     * columns are display/dedup metadata pulled from the first real proxy outbound; the config
     * itself rides along verbatim in fullConfigJson and is what actually gets used on connect.
     */
    private fun parseFullConfig(obj: JsonObject, subscriptionId: Long?): ServerEntity? {
        val outbounds = obj["outbounds"] as? JsonArray ?: return null
        val name = obj["remarks"]?.jsonPrimitive?.content?.takeIf { it.isNotBlank() } ?: "Конфигурация"

        var address = ""
        var port = 443
        var protocol = ProxyProtocol.VLESS_TCP
        for (entry in outbounds) {
            val outbound = entry as? JsonObject ?: continue
            if (outbound["protocol"]?.jsonPrimitive?.content != "vless") continue
            val vnextFirst = ((outbound["settings"] as? JsonObject)?.get("vnext") as? JsonArray)
                ?.firstOrNull() as? JsonObject
            if (vnextFirst == null) continue
            address = vnextFirst["address"]?.jsonPrimitive?.content ?: continue
            port = vnextFirst["port"]?.jsonPrimitive?.content?.toIntOrNull() ?: 443
            protocol = when ((outbound["streamSettings"] as? JsonObject)?.get("security")?.jsonPrimitive?.content) {
                "reality" -> ProxyProtocol.VLESS_REALITY
                "tls" -> ProxyProtocol.VLESS_TLS
                else -> ProxyProtocol.VLESS_TCP
            }
            break
        }
        if (address.isEmpty()) {
            Timber.w("Skipping full-config subscription entry '%s': no usable vless outbound found", name)
            return null
        }

        return ServerEntity(
            subscriptionId = subscriptionId,
            name = name,
            countryFlagEmoji = "",
            protocol = protocol,
            address = address,
            port = port,
            fullConfigJson = obj.toString(),
        )
    }
}

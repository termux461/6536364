package com.lizercool.lcvpn.network.subscription

import com.lizercool.lcvpn.data.db.entity.ServerEntity
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import timber.log.Timber
import android.util.Base64

/**
 * Best-effort parser for whatever a Remnawave-style subscription endpoint returns.
 *
 * Two shapes are supported today:
 *  1. The universal fallback: base64-encoded, newline-separated share links
 *     (vless://..., hysteria2://...) - what most panels serve to an unrecognized client.
 *  2. A generic JSON array of host objects, in case the panel is configured to answer
 *     the "Lizercool" User-Agent with structured JSON instead.
 *
 * TODO: once we have a real sample response from sub.lizercoolvpn.space, replace shape 2
 * with an exact match of Remnawave's actual schema.
 */
object SubscriptionBodyParser {

    private val json = Json { ignoreUnknownKeys = true }

    fun parseServers(body: String, subscriptionId: Long?): List<ServerEntity> {
        val trimmed = body.trim()
        if (trimmed.isEmpty()) return emptyList()

        // Shape 2: raw JSON.
        if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
            runCatching { parseJson(trimmed, subscriptionId) }
                .onSuccess { if (it.isNotEmpty()) return it }
                .onFailure { Timber.w(it, "Subscription body looked like JSON but did not match the expected shape") }
        }

        // Shape 1: base64 body of share links.
        val decoded = runCatching {
            String(Base64.decode(trimmed, Base64.DEFAULT))
        }.getOrElse { trimmed } // maybe it wasn't base64-encoded at all, treat as plain text

        val links = decoded.lines().map { it.trim() }.filter { it.isNotEmpty() }
        val servers = links.mapNotNull { ShareLinkParser.parse(it, subscriptionId) }
        if (servers.isEmpty() && links.isNotEmpty()) {
            Timber.w("Decoded subscription body but none of the %d lines matched a known share-link format", links.size)
        }
        return servers
    }

    private fun parseJson(text: String, subscriptionId: Long?): List<ServerEntity> {
        val element = json.parseToJsonElement(text)
        val hostArray: JsonArray = when {
            element is JsonArray -> element
            element is JsonObject && element["servers"] is JsonArray -> element["servers"]!!.jsonArray
            element is JsonObject && element["hosts"] is JsonArray -> element["hosts"]!!.jsonArray
            else -> return emptyList()
        }

        return hostArray.mapNotNull { entry ->
            val obj = entry as? JsonObject ?: return@mapNotNull null
            val link = obj["link"]?.jsonPrimitive?.content
                ?: obj["url"]?.jsonPrimitive?.content
                ?: obj["config"]?.jsonPrimitive?.content
            link?.let { ShareLinkParser.parse(it, subscriptionId) }
        }
    }
}

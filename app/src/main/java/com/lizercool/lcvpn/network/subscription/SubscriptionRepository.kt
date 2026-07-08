package com.lizercool.lcvpn.network.subscription

import android.content.Context
import com.lizercool.lcvpn.data.db.dao.ServerDao
import com.lizercool.lcvpn.data.db.dao.SubscriptionDao
import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.data.db.entity.SubscriptionEntity
import com.lizercool.lcvpn.util.DeviceInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import timber.log.Timber
import java.util.concurrent.TimeUnit

/** After this many consecutive failed refreshes of every primary subscription, the reserve activates. */
const val RESERVE_FALLBACK_THRESHOLD = 2

class SubscriptionRepository(
    private val subscriptionDao: SubscriptionDao,
    private val serverDao: ServerDao,
    private val context: Context,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    // Sent on every subscription request so the Remnawave panel can bind/limit this device (HWID).
    private val hwidHeaders = DeviceInfo.subscriptionHeaders(context)
    private val happUserAgent = DeviceInfo.happUserAgent(context)

    /** Refreshes every non-reserve subscription; if all of them fail twice in a row, activates the reserve. */
    suspend fun refreshAll() {
        val primaries = subscriptionDao.primaries()
        var anyPrimarySucceeded = false

        for (sub in primaries) {
            val ok = refreshOne(sub)
            if (ok) anyPrimarySucceeded = true
        }

        if (!anyPrimarySucceeded && primaries.isNotEmpty()) {
            val allExhausted = primaries.all {
                (subscriptionDao.byId(it.id)?.failedRefreshCount ?: 0) >= RESERVE_FALLBACK_THRESHOLD
            }
            if (allExhausted) {
                val reserve = subscriptionDao.reserves().firstOrNull()
                if (reserve != null) {
                    Timber.w("Primary subscriptions failed %d+ times, activating reserve '%s'", RESERVE_FALLBACK_THRESHOLD, reserve.name)
                    refreshOne(reserve)
                } else {
                    Timber.w("Primary subscriptions exhausted retries but no reserve subscription is configured")
                }
            }
        }
    }

    private data class FetchAttempt(val url: String, val userAgent: String, val accept: String)
    private data class Parsed(val servers: List<ServerEntity>, val userInfo: SubscriptionUserInfo?)

    suspend fun refreshOne(subscription: SubscriptionEntity): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            // The Автовыбор profiles (multi-outbound configs with a leastLoad balancer +
            // burstObservatory) only exist in the panel's xray-json subscription format - they
            // can't be expressed as vless:// share links. Remnawave picks the format by client
            // User-Agent (Happ and friends get xray-json) and some deployments also expose an
            // explicit /json route, so those are tried first; the plain share-link format stays
            // as the fallback that always works.
            val attempts = listOf(
                FetchAttempt(subscription.url, happUserAgent, "application/json"),
                FetchAttempt(subscription.url.trimEnd('/') + "/json", happUserAgent, "application/json"),
                FetchAttempt(subscription.url, "LizercoolVPN/1.0", "text/plain"),
            )

            var best: Parsed? = null
            for (attempt in attempts) {
                val parsed = runCatching { fetchAndParse(attempt, subscription.id) }.getOrNull() ?: continue
                if (parsed.servers.isEmpty()) continue
                if (parsed.servers.any { it.fullConfigJson != null }) {
                    best = parsed
                    break
                }
                if (best == null) best = parsed
            }

            val servers = best?.servers ?: error("No servers parsed from subscription body")
            val userInfo = best.userInfo

            // Refresh replaces every row (ids reset), so the previous selection would otherwise
            // silently disappear - remember it and restore it on the matching new row once
            // inserted. Matched by name first (Автовыбор profiles can share the same first
            // outbound address+port between each other), then by address+port as a fallback.
            val previouslySelected = serverDao.selectedInSubscription(subscription.id)

            serverDao.deleteBySubscription(subscription.id)
            serverDao.insertAll(servers)

            if (previouslySelected != null) {
                val restored = serverDao.selectByName(subscription.id, previouslySelected.name)
                if (restored == 0) {
                    serverDao.selectByAddressPort(subscription.id, previouslySelected.address, previouslySelected.port)
                }
            }
            if (serverDao.selectedCount() == 0) {
                serverDao.firstServer()?.let { serverDao.select(it.id) }
            }

            subscriptionDao.update(
                subscription.copy(
                    usedBytes = userInfo?.usedBytes ?: subscription.usedBytes,
                    limitBytes = userInfo?.totalBytes ?: subscription.limitBytes,
                    expiresAtEpochMs = userInfo?.expireEpochSeconds?.times(1000) ?: subscription.expiresAtEpochMs,
                    failedRefreshCount = 0,
                    lastUpdatedEpochMs = System.currentTimeMillis(),
                ),
            )
            Timber.i(
                "Subscription '%s' refreshed: %d servers (%d full-config)",
                subscription.name,
                servers.size,
                servers.count { it.fullConfigJson != null },
            )
        }.onFailure { e ->
            Timber.e(e, "Failed to refresh subscription '%s'", subscription.name)
            subscriptionDao.update(subscription.copy(failedRefreshCount = subscription.failedRefreshCount + 1))
        }.isSuccess
    }

    private fun fetchAndParse(attempt: FetchAttempt, subscriptionId: Long): Parsed {
        val builder = Request.Builder()
            .url(attempt.url)
            .header("User-Agent", attempt.userAgent)
            .header("Accept", attempt.accept)
        hwidHeaders.forEach { (k, v) -> builder.header(k, v) }
        val request = builder.build()

        return client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) error("HTTP ${response.code} for ${attempt.url}")
            val body = response.body?.string().orEmpty()
            Parsed(
                servers = SubscriptionBodyParser.parseServers(body, subscriptionId),
                userInfo = SubscriptionUserInfo.parse(response.header("Subscription-Userinfo")),
            )
        }
    }
}

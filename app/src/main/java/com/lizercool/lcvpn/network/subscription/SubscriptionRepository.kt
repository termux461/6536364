package com.lizercool.lcvpn.network.subscription

import com.lizercool.lcvpn.data.db.dao.ServerDao
import com.lizercool.lcvpn.data.db.dao.SubscriptionDao
import com.lizercool.lcvpn.data.db.entity.SubscriptionEntity
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
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

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

    suspend fun refreshOne(subscription: SubscriptionEntity): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            val request = Request.Builder()
                .url(subscription.url)
                .header("User-Agent", "LizercoolVPN/1.0")
                .header("Accept", "text/plain")
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) error("HTTP ${response.code}")
                val body = response.body?.string().orEmpty()
                val userInfo = SubscriptionUserInfo.parse(response.header("Subscription-Userinfo"))
                val servers = SubscriptionBodyParser.parseServers(body, subscription.id)

                if (servers.isEmpty()) error("No servers parsed from subscription body")

                serverDao.deleteBySubscription(subscription.id)
                serverDao.insertAll(servers)

                subscriptionDao.update(
                    subscription.copy(
                        usedBytes = userInfo?.usedBytes ?: subscription.usedBytes,
                        limitBytes = userInfo?.totalBytes ?: subscription.limitBytes,
                        expiresAtEpochMs = userInfo?.expireEpochSeconds?.times(1000) ?: subscription.expiresAtEpochMs,
                        failedRefreshCount = 0,
                        lastUpdatedEpochMs = System.currentTimeMillis(),
                    ),
                )
                Timber.i("Subscription '%s' refreshed: %d servers", subscription.name, servers.size)
            }
        }.onFailure { e ->
            Timber.e(e, "Failed to refresh subscription '%s'", subscription.name)
            subscriptionDao.update(subscription.copy(failedRefreshCount = subscription.failedRefreshCount + 1))
        }.isSuccess
    }
}

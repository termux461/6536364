package com.lizercool.lcvpn.network.subscription

/**
 * Parses the de-facto standard "Subscription-Userinfo" response header used by Xray/sing-box
 * subscription panels (Marzban, Remnawave, 3x-ui, ...):
 *   Subscription-Userinfo: upload=123; download=456; total=789000000; expire=1735689600
 */
data class SubscriptionUserInfo(
    val uploadBytes: Long = 0,
    val downloadBytes: Long = 0,
    val totalBytes: Long? = null,
    val expireEpochSeconds: Long? = null,
) {
    val usedBytes: Long get() = uploadBytes + downloadBytes

    companion object {
        fun parse(headerValue: String?): SubscriptionUserInfo? {
            if (headerValue.isNullOrBlank()) return null
            val fields = headerValue.split(";")
                .mapNotNull { part ->
                    val idx = part.indexOf('=')
                    if (idx < 0) return@mapNotNull null
                    part.substring(0, idx).trim() to part.substring(idx + 1).trim()
                }.toMap()

            return SubscriptionUserInfo(
                uploadBytes = fields["upload"]?.toLongOrNull() ?: 0,
                downloadBytes = fields["download"]?.toLongOrNull() ?: 0,
                totalBytes = fields["total"]?.toLongOrNull()?.takeIf { it > 0 },
                expireEpochSeconds = fields["expire"]?.toLongOrNull()?.takeIf { it > 0 },
            )
        }
    }
}

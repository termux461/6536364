package com.lizercool.lcvpn.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "subscriptions")
data class SubscriptionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
    val url: String,
    val telegramLink: String? = null,
    val usedBytes: Long = 0,
    val limitBytes: Long? = null, // null = unlimited
    val expiresAtEpochMs: Long? = null,
    val isActive: Boolean = false,
    /** Marked by the user as a fallback; not auto-refreshed on schedule, only activated after failedRefreshCount hits the threshold on the primary subscription(s). */
    val isReserve: Boolean = false,
    val failedRefreshCount: Int = 0,
    val lastUpdatedEpochMs: Long? = null,
)

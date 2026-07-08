package com.lizercool.lcvpn.data.db.entity

import androidx.room.Entity

/**
 * A package marked here is part of the "selected" set referenced by AppRoutingMode
 * (either the set that's excluded from the tunnel, or the only set routed through it,
 * depending on the current mode stored in Prefs).
 */
@Entity(tableName = "app_routing_rules", primaryKeys = ["packageName"])
data class AppRoutingRuleEntity(
    val packageName: String,
)

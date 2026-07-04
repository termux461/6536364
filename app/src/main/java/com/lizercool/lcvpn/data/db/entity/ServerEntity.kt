package com.lizercool.lcvpn.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.lizercool.lcvpn.data.model.ProxyProtocol

@Entity(tableName = "servers")
data class ServerEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val subscriptionId: Long?,
    val name: String,
    val countryFlagEmoji: String,
    val protocol: ProxyProtocol,
    val address: String,
    val port: Int,

    // VLESS
    val uuid: String? = null,
    val flow: String? = null,
    val network: String = "tcp", // tcp / ws / grpc
    val wsPath: String? = null,
    val wsHost: String? = null,
    val sni: String? = null,
    val realityPublicKey: String? = null,
    val realityShortId: String? = null,
    val realityFingerprint: String? = null,

    // Hysteria2
    val hysteria2Password: String? = null,
    val hysteria2Obfs: String? = null,

    val lastPingMs: Int? = null,
    val isSelected: Boolean = false,
)

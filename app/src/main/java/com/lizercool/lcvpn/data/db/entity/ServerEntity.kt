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
    val network: String = "tcp", // tcp / ws / xhttp / grpc
    val wsPath: String? = null,
    val wsHost: String? = null,
    val sni: String? = null,
    val realityPublicKey: String? = null,
    val realityShortId: String? = null,
    val realityFingerprint: String? = null,

    // xhttp transport (used by the Lizercool/Remnawave panel for CDN-friendly + anti-DPI routes)
    val xhttpMode: String? = null,
    val xhttpExtraJson: String? = null,

    // Hysteria2
    val hysteria2Password: String? = null,
    val hysteria2Obfs: String? = null,

    // Set when this entry came from an xray-json subscription as a complete client config
    // (multi-outbound Автовыбор profiles with a leastLoad balancer + burstObservatory, etc.).
    // When present it is used as the base config on connect - our own inbounds are swapped in
    // but its outbounds/routing/balancers/observatory are kept as the panel authored them.
    val fullConfigJson: String? = null,

    val lastPingMs: Int? = null,
    val isSelected: Boolean = false,
)

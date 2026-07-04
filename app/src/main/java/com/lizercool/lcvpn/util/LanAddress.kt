package com.lizercool.lcvpn.util

import java.net.Inet4Address
import java.net.NetworkInterface

/** Best-effort local IPv4 address (Wi-Fi/LAN), used to show users where to point a manual proxy. */
object LanAddress {
    fun current(): String? = runCatching {
        NetworkInterface.getNetworkInterfaces().asSequence()
            .filter { it.isUp && !it.isLoopback }
            .flatMap { it.inetAddresses.asSequence() }
            .filterIsInstance<Inet4Address>()
            .firstOrNull { !it.isLoopbackAddress }
            ?.hostAddress
    }.getOrNull()
}

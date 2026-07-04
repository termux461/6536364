package com.lizercool.lcvpn.data.model

/** Transport/security combinations shown on the Servers screen (e.g. "VLESS · REALITY"). */
enum class ProxyProtocol(val label: String) {
    VLESS_REALITY("VLESS · REALITY"),
    VLESS_TLS("VLESS · TLS"),
    VLESS_WS("VLESS · WS"),
    VLESS_TCP("VLESS · TCP"),
    HYSTERIA2("HYSTERIA2");

    companion object {
        fun fromLabel(label: String): ProxyProtocol =
            entries.firstOrNull { it.label.equals(label, ignoreCase = true) } ?: VLESS_TLS
    }
}

enum class TunnelMode { PROXY, TUN, TUN_AND_PROXY }

enum class AppRoutingMode { ALL_EXCEPT_SELECTED, ONLY_SELECTED }

enum class ServerListSort { NONE, PING, ALPHABETICAL }

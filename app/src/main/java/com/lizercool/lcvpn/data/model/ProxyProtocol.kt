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

/**
 * How the Servers screen measures a server's latency.
 * - TCP: bare TCP connect to address:port, outside the tunnel - fastest but unreliable for
 *   REALITY/censorship-resistant endpoints an ISP may block at the raw-TCP level.
 * - ICMP: shells out to the system `ping` binary (no root needed, apps are allowed raw ICMP via
 *   the AID_INET group) - measures raw network latency to the address, still outside the tunnel.
 * - PROXY_HEAD/PROXY_GET: establishes the real VLESS/REALITY connection through a temporary
 *   Xray-core instance and times an HTTP HEAD or GET request through it - the only mode that
 *   reflects real usable latency, at the cost of taking longer per server.
 */
enum class PingMode { TCP, ICMP, PROXY_HEAD, PROXY_GET }

/**
 * Which IP versions the TUN interface captures and routes.
 * - BOTH: capture IPv4 + IPv6 (default) - everything goes through the VPN.
 * - IPV4_ONLY: capture only IPv4; IPv6 is left to the system (may leak past the VPN, but avoids
 *   trouble on networks/servers where proxied IPv6 misbehaves).
 * - IPV6_ONLY: capture only IPv6 (rarely needed, exposed for completeness).
 */
enum class IpStackMode { BOTH, IPV4_ONLY, IPV6_ONLY }

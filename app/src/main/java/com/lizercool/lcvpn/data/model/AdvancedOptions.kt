package com.lizercool.lcvpn.data.model

/**
 * How traffic is split between the proxy and direct.
 * - SMART: keep Russian services / RFC1918 / private going direct, block ads, proxy the rest
 *   (default - matches the Remnawave panel template).
 * - GLOBAL: send everything through the proxy (no RU bypass, no ad-block).
 * Custom per-domain lists are layered on top of either mode.
 */
enum class RoutingMode { SMART, GLOBAL }

/**
 * User routing choices (Настройки → Маршрутизация).
 *
 * [enabled] is the master switch for CLIENT-side routing. When false, our own configs just send
 * everything through the proxy (only the local network stays direct) and the custom domain lists
 * are ignored - but panel-authored Автовыбор configs still use their own SERVER-side routing,
 * because that lives inside the config itself and we never override it.
 */
data class RoutingOptions(
    val enabled: Boolean = true,
    val mode: RoutingMode = RoutingMode.SMART,
    val directDomains: List<String> = emptyList(),
    val proxyDomains: List<String> = emptyList(),
)

/**
 * Anti-DPI + multiplexing options (Настройки → Анти-DPI). Only applied to configs we build
 * ourselves; panel-authored Автовыбор configs are used as-is.
 */
data class AntiDpiOptions(
    val fragmentEnabled: Boolean = false,
    val fragmentPackets: String = "tlshello",
    val fragmentLength: String = "100-200",
    val fragmentInterval: String = "10-20",
    val muxEnabled: Boolean = false,
    val muxConcurrency: Int = 8,
)

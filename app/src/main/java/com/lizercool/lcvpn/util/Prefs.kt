package com.lizercool.lcvpn.util

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.lizercool.lcvpn.data.model.AntiDpiOptions
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.IpStackMode
import com.lizercool.lcvpn.data.model.PingMode
import com.lizercool.lcvpn.data.model.RoutingMode
import com.lizercool.lcvpn.data.model.RoutingOptions
import com.lizercool.lcvpn.data.model.ServerListSort
import com.lizercool.lcvpn.data.model.TunnelMode
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "lcvpn_prefs")

/** Thin wrapper over DataStore for the toggles shown across the Settings tabs. */
class Prefs(private val context: Context) {

    private object Keys {
        val LANGUAGE = stringPreferencesKey("language") // "ru" | "en"
        val DARK_THEME = booleanPreferencesKey("dark_theme")
        val SORT_ORDER = stringPreferencesKey("sort_order")
        val CONNECT_ON_LAUNCH = booleanPreferencesKey("connect_on_launch")
        val UPDATE_ON_LAUNCH = booleanPreferencesKey("update_on_launch")
        val TUNNEL_MODE = stringPreferencesKey("tunnel_mode")
        val APP_ROUTING_MODE = stringPreferencesKey("app_routing_mode")
        val ANNOUNCEMENT_SEEN_VERSION = stringPreferencesKey("announcement_seen_version")
        val LAN_PROXY_PASSWORD = stringPreferencesKey("lan_proxy_password")
        val KILL_SWITCH = booleanPreferencesKey("kill_switch")
        val PING_MODE = stringPreferencesKey("ping_mode")
        val IP_STACK_MODE = stringPreferencesKey("ip_stack_mode")

        // Advanced / performance tuning (Расширенные настройки).
        val SNIFFING = booleanPreferencesKey("sniffing")
        val IDLE_TIMEOUT_SEC = intPreferencesKey("idle_timeout_sec")
        val BLOCK_UDP = booleanPreferencesKey("block_udp")
        val KEEP_AWAKE = booleanPreferencesKey("keep_awake")
        val LOG_RETENTION_HOURS = intPreferencesKey("log_retention_hours") // 0 = forever

        // Routing (Маршрутизация).
        val ROUTING_ENABLED = booleanPreferencesKey("routing_enabled")
        val ROUTING_MODE = stringPreferencesKey("routing_mode")
        val DIRECT_DOMAINS = stringPreferencesKey("direct_domains")
        val PROXY_DOMAINS = stringPreferencesKey("proxy_domains")

        // Anti-DPI + Mux (Анти-DPI).
        val FRAGMENT_ENABLED = booleanPreferencesKey("fragment_enabled")
        val FRAGMENT_PACKETS = stringPreferencesKey("fragment_packets")
        val FRAGMENT_LENGTH = stringPreferencesKey("fragment_length")
        val FRAGMENT_INTERVAL = stringPreferencesKey("fragment_interval")
        val MUX_ENABLED = booleanPreferencesKey("mux_enabled")
        val MUX_CONCURRENCY = intPreferencesKey("mux_concurrency")

        // Memory cap for the Go (Xray-core) runtime.
        val MEMORY_LIMIT_MB = intPreferencesKey("memory_limit_mb")
        val MEMORY_UNLIMITED = booleanPreferencesKey("memory_unlimited")
    }

    val language: Flow<String> = context.dataStore.data.map { it[Keys.LANGUAGE] ?: "ru" }
    val darkTheme: Flow<Boolean> = context.dataStore.data.map { it[Keys.DARK_THEME] ?: true }
    val sortOrder: Flow<ServerListSort> = context.dataStore.data.map {
        runCatching { ServerListSort.valueOf(it[Keys.SORT_ORDER] ?: "") }.getOrDefault(ServerListSort.NONE)
    }
    val connectOnLaunch: Flow<Boolean> = context.dataStore.data.map { it[Keys.CONNECT_ON_LAUNCH] ?: false }
    val updateOnLaunch: Flow<Boolean> = context.dataStore.data.map { it[Keys.UPDATE_ON_LAUNCH] ?: false }
    val tunnelMode: Flow<TunnelMode> = context.dataStore.data.map {
        // TUN + Proxy by default: full-device VPN plus a password-protected LAN SOCKS proxy other
        // devices on the same Wi-Fi can use. Confirmed working on real devices.
        runCatching { TunnelMode.valueOf(it[Keys.TUNNEL_MODE] ?: "") }.getOrDefault(TunnelMode.TUN_AND_PROXY)
    }
    val appRoutingMode: Flow<AppRoutingMode> = context.dataStore.data.map {
        runCatching { AppRoutingMode.valueOf(it[Keys.APP_ROUTING_MODE] ?: "") }
            .getOrDefault(AppRoutingMode.ALL_EXCEPT_SELECTED)
    }
    val killSwitch: Flow<Boolean> = context.dataStore.data.map { it[Keys.KILL_SWITCH] ?: false }
    val pingMode: Flow<PingMode> = context.dataStore.data.map {
        runCatching { PingMode.valueOf(it[Keys.PING_MODE] ?: "") }.getOrDefault(PingMode.PROXY_GET)
    }
    val ipStackMode: Flow<IpStackMode> = context.dataStore.data.map {
        runCatching { IpStackMode.valueOf(it[Keys.IP_STACK_MODE] ?: "") }.getOrDefault(IpStackMode.BOTH)
    }
    val sniffing: Flow<Boolean> = context.dataStore.data.map { it[Keys.SNIFFING] ?: true }
    val idleTimeoutSec: Flow<Int> = context.dataStore.data.map { it[Keys.IDLE_TIMEOUT_SEC] ?: 300 }
    val blockUdp: Flow<Boolean> = context.dataStore.data.map { it[Keys.BLOCK_UDP] ?: false }
    val keepAwake: Flow<Boolean> = context.dataStore.data.map { it[Keys.KEEP_AWAKE] ?: false }
    val logRetentionHours: Flow<Int> = context.dataStore.data.map { it[Keys.LOG_RETENTION_HOURS] ?: 1 }

    val routingEnabled: Flow<Boolean> = context.dataStore.data.map { it[Keys.ROUTING_ENABLED] ?: true }
    val routingMode: Flow<RoutingMode> = context.dataStore.data.map {
        runCatching { RoutingMode.valueOf(it[Keys.ROUTING_MODE] ?: "") }.getOrDefault(RoutingMode.SMART)
    }
    val directDomains: Flow<String> = context.dataStore.data.map { it[Keys.DIRECT_DOMAINS] ?: "" }
    val proxyDomains: Flow<String> = context.dataStore.data.map { it[Keys.PROXY_DOMAINS] ?: "" }
    val routingOptions: Flow<RoutingOptions> = context.dataStore.data.map { p ->
        RoutingOptions(
            enabled = p[Keys.ROUTING_ENABLED] ?: true,
            mode = runCatching { RoutingMode.valueOf(p[Keys.ROUTING_MODE] ?: "") }.getOrDefault(RoutingMode.SMART),
            directDomains = splitDomains(p[Keys.DIRECT_DOMAINS]),
            proxyDomains = splitDomains(p[Keys.PROXY_DOMAINS]),
        )
    }

    val fragmentEnabled: Flow<Boolean> = context.dataStore.data.map { it[Keys.FRAGMENT_ENABLED] ?: false }
    val fragmentPackets: Flow<String> = context.dataStore.data.map { it[Keys.FRAGMENT_PACKETS] ?: "tlshello" }
    val fragmentLength: Flow<String> = context.dataStore.data.map { it[Keys.FRAGMENT_LENGTH] ?: "100-200" }
    val fragmentInterval: Flow<String> = context.dataStore.data.map { it[Keys.FRAGMENT_INTERVAL] ?: "10-20" }
    val muxEnabled: Flow<Boolean> = context.dataStore.data.map { it[Keys.MUX_ENABLED] ?: false }
    val muxConcurrency: Flow<Int> = context.dataStore.data.map { it[Keys.MUX_CONCURRENCY] ?: 8 }
    val antiDpiOptions: Flow<AntiDpiOptions> = context.dataStore.data.map { p ->
        AntiDpiOptions(
            fragmentEnabled = p[Keys.FRAGMENT_ENABLED] ?: false,
            fragmentPackets = p[Keys.FRAGMENT_PACKETS] ?: "tlshello",
            fragmentLength = p[Keys.FRAGMENT_LENGTH] ?: "100-200",
            fragmentInterval = p[Keys.FRAGMENT_INTERVAL] ?: "10-20",
            muxEnabled = p[Keys.MUX_ENABLED] ?: false,
            muxConcurrency = p[Keys.MUX_CONCURRENCY] ?: 8,
        )
    }

    val memoryLimitMb: Flow<Int> = context.dataStore.data.map { it[Keys.MEMORY_LIMIT_MB] ?: 100 }
    val memoryUnlimited: Flow<Boolean> = context.dataStore.data.map { it[Keys.MEMORY_UNLIMITED] ?: false }

    /** Read synchronously at app start (before Xray-core loads) to set the Go runtime env. */
    suspend fun memoryLimitMbOnce(): Int = context.dataStore.data.map { it[Keys.MEMORY_LIMIT_MB] ?: 100 }.first()
    suspend fun memoryUnlimitedOnce(): Boolean = context.dataStore.data.map { it[Keys.MEMORY_UNLIMITED] ?: false }.first()

    private fun splitDomains(raw: String?): List<String> =
        raw?.split(',', '\n', ' ')?.map { it.trim() }?.filter { it.isNotEmpty() } ?: emptyList()

    suspend fun setLanguage(value: String) = context.dataStore.edit { it[Keys.LANGUAGE] = value }
    suspend fun setDarkTheme(value: Boolean) = context.dataStore.edit { it[Keys.DARK_THEME] = value }
    suspend fun setSortOrder(value: ServerListSort) = context.dataStore.edit { it[Keys.SORT_ORDER] = value.name }
    suspend fun setConnectOnLaunch(value: Boolean) = context.dataStore.edit { it[Keys.CONNECT_ON_LAUNCH] = value }
    suspend fun setUpdateOnLaunch(value: Boolean) = context.dataStore.edit { it[Keys.UPDATE_ON_LAUNCH] = value }
    suspend fun setTunnelMode(value: TunnelMode) = context.dataStore.edit { it[Keys.TUNNEL_MODE] = value.name }
    suspend fun setAppRoutingMode(value: AppRoutingMode) =
        context.dataStore.edit { it[Keys.APP_ROUTING_MODE] = value.name }
    suspend fun setKillSwitch(value: Boolean) = context.dataStore.edit { it[Keys.KILL_SWITCH] = value }
    suspend fun setPingMode(value: PingMode) = context.dataStore.edit { it[Keys.PING_MODE] = value.name }
    suspend fun setIpStackMode(value: IpStackMode) = context.dataStore.edit { it[Keys.IP_STACK_MODE] = value.name }
    suspend fun setSniffing(value: Boolean) = context.dataStore.edit { it[Keys.SNIFFING] = value }
    suspend fun setIdleTimeoutSec(value: Int) = context.dataStore.edit { it[Keys.IDLE_TIMEOUT_SEC] = value }
    suspend fun setBlockUdp(value: Boolean) = context.dataStore.edit { it[Keys.BLOCK_UDP] = value }
    suspend fun setKeepAwake(value: Boolean) = context.dataStore.edit { it[Keys.KEEP_AWAKE] = value }
    suspend fun setLogRetentionHours(value: Int) = context.dataStore.edit { it[Keys.LOG_RETENTION_HOURS] = value }
    suspend fun setRoutingEnabled(value: Boolean) = context.dataStore.edit { it[Keys.ROUTING_ENABLED] = value }
    suspend fun setRoutingMode(value: RoutingMode) = context.dataStore.edit { it[Keys.ROUTING_MODE] = value.name }
    suspend fun setDirectDomains(value: String) = context.dataStore.edit { it[Keys.DIRECT_DOMAINS] = value }
    suspend fun setProxyDomains(value: String) = context.dataStore.edit { it[Keys.PROXY_DOMAINS] = value }
    suspend fun setFragmentEnabled(value: Boolean) = context.dataStore.edit { it[Keys.FRAGMENT_ENABLED] = value }
    suspend fun setFragmentPackets(value: String) = context.dataStore.edit { it[Keys.FRAGMENT_PACKETS] = value }
    suspend fun setFragmentLength(value: String) = context.dataStore.edit { it[Keys.FRAGMENT_LENGTH] = value }
    suspend fun setFragmentInterval(value: String) = context.dataStore.edit { it[Keys.FRAGMENT_INTERVAL] = value }
    suspend fun setMuxEnabled(value: Boolean) = context.dataStore.edit { it[Keys.MUX_ENABLED] = value }
    suspend fun setMuxConcurrency(value: Int) = context.dataStore.edit { it[Keys.MUX_CONCURRENCY] = value }
    suspend fun setMemoryLimitMb(value: Int) = context.dataStore.edit { it[Keys.MEMORY_LIMIT_MB] = value }
    suspend fun setMemoryUnlimited(value: Boolean) = context.dataStore.edit { it[Keys.MEMORY_UNLIMITED] = value }

    suspend fun hasSeenAnnouncement(version: String): Boolean {
        val seen = context.dataStore.data.map { it[Keys.ANNOUNCEMENT_SEEN_VERSION] }.first()
        return seen == version
    }

    suspend fun markAnnouncementSeen(version: String) =
        context.dataStore.edit { it[Keys.ANNOUNCEMENT_SEEN_VERSION] = version }

    /** Generated once on first use of TUN + Proxy mode and reused after that, so LAN clients can be set up once. */
    suspend fun lanProxyPassword(): String {
        val existing = context.dataStore.data.map { it[Keys.LAN_PROXY_PASSWORD] }.first()
        if (existing != null) return existing
        val generated = (1..12).map { "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".random() }.joinToString("")
        context.dataStore.edit { it[Keys.LAN_PROXY_PASSWORD] = generated }
        return generated
    }
}

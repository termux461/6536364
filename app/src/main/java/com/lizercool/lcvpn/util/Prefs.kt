package com.lizercool.lcvpn.util

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.PingMode
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
    }

    val language: Flow<String> = context.dataStore.data.map { it[Keys.LANGUAGE] ?: "ru" }
    val darkTheme: Flow<Boolean> = context.dataStore.data.map { it[Keys.DARK_THEME] ?: true }
    val sortOrder: Flow<ServerListSort> = context.dataStore.data.map {
        runCatching { ServerListSort.valueOf(it[Keys.SORT_ORDER] ?: "") }.getOrDefault(ServerListSort.NONE)
    }
    val connectOnLaunch: Flow<Boolean> = context.dataStore.data.map { it[Keys.CONNECT_ON_LAUNCH] ?: false }
    val updateOnLaunch: Flow<Boolean> = context.dataStore.data.map { it[Keys.UPDATE_ON_LAUNCH] ?: false }
    val tunnelMode: Flow<TunnelMode> = context.dataStore.data.map {
        // Defaults to PROXY until TUN mode (now bridged via hev-socks5-tunnel, see
        // LcVpnService) has been confirmed working on a real device - flip this default once
        // that's verified.
        runCatching { TunnelMode.valueOf(it[Keys.TUNNEL_MODE] ?: "") }.getOrDefault(TunnelMode.PROXY)
    }
    val appRoutingMode: Flow<AppRoutingMode> = context.dataStore.data.map {
        runCatching { AppRoutingMode.valueOf(it[Keys.APP_ROUTING_MODE] ?: "") }
            .getOrDefault(AppRoutingMode.ALL_EXCEPT_SELECTED)
    }
    val killSwitch: Flow<Boolean> = context.dataStore.data.map { it[Keys.KILL_SWITCH] ?: false }
    val pingMode: Flow<PingMode> = context.dataStore.data.map {
        runCatching { PingMode.valueOf(it[Keys.PING_MODE] ?: "") }.getOrDefault(PingMode.PROXY_GET)
    }

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

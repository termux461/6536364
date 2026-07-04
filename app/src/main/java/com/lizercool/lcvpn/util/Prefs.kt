package com.lizercool.lcvpn.util

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.ServerListSort
import com.lizercool.lcvpn.data.model.TunnelMode
import kotlinx.coroutines.flow.Flow
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
    }

    val language: Flow<String> = context.dataStore.data.map { it[Keys.LANGUAGE] ?: "ru" }
    val darkTheme: Flow<Boolean> = context.dataStore.data.map { it[Keys.DARK_THEME] ?: true }
    val sortOrder: Flow<ServerListSort> = context.dataStore.data.map {
        runCatching { ServerListSort.valueOf(it[Keys.SORT_ORDER] ?: "") }.getOrDefault(ServerListSort.NONE)
    }
    val connectOnLaunch: Flow<Boolean> = context.dataStore.data.map { it[Keys.CONNECT_ON_LAUNCH] ?: false }
    val updateOnLaunch: Flow<Boolean> = context.dataStore.data.map { it[Keys.UPDATE_ON_LAUNCH] ?: false }
    val tunnelMode: Flow<TunnelMode> = context.dataStore.data.map {
        runCatching { TunnelMode.valueOf(it[Keys.TUNNEL_MODE] ?: "") }.getOrDefault(TunnelMode.TUN)
    }
    val appRoutingMode: Flow<AppRoutingMode> = context.dataStore.data.map {
        runCatching { AppRoutingMode.valueOf(it[Keys.APP_ROUTING_MODE] ?: "") }
            .getOrDefault(AppRoutingMode.ALL_EXCEPT_SELECTED)
    }

    suspend fun setLanguage(value: String) = context.dataStore.edit { it[Keys.LANGUAGE] = value }
    suspend fun setDarkTheme(value: Boolean) = context.dataStore.edit { it[Keys.DARK_THEME] = value }
    suspend fun setSortOrder(value: ServerListSort) = context.dataStore.edit { it[Keys.SORT_ORDER] = value.name }
    suspend fun setConnectOnLaunch(value: Boolean) = context.dataStore.edit { it[Keys.CONNECT_ON_LAUNCH] = value }
    suspend fun setUpdateOnLaunch(value: Boolean) = context.dataStore.edit { it[Keys.UPDATE_ON_LAUNCH] = value }
    suspend fun setTunnelMode(value: TunnelMode) = context.dataStore.edit { it[Keys.TUNNEL_MODE] = value.name }
    suspend fun setAppRoutingMode(value: AppRoutingMode) =
        context.dataStore.edit { it[Keys.APP_ROUTING_MODE] = value.name }

    suspend fun hasSeenAnnouncement(version: String): Boolean {
        val seen = kotlinx.coroutines.flow.first(context.dataStore.data.map { it[Keys.ANNOUNCEMENT_SEEN_VERSION] })
        return seen == version
    }

    suspend fun markAnnouncementSeen(version: String) =
        context.dataStore.edit { it[Keys.ANNOUNCEMENT_SEEN_VERSION] = version }
}

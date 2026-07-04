package com.lizercool.lcvpn.ui.settings

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.lizercool.lcvpn.data.db.AppDatabase
import com.lizercool.lcvpn.data.db.entity.AppRoutingRuleEntity
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.ServerListSort
import com.lizercool.lcvpn.data.model.TunnelMode
import com.lizercool.lcvpn.util.LanAddress
import com.lizercool.lcvpn.util.LogSharing
import com.lizercool.lcvpn.util.Prefs
import com.lizercool.lcvpn.vpn.AppRoutingManager
import com.lizercool.lcvpn.vpn.InstalledAppInfo
import com.lizercool.lcvpn.vpn.LcVpnService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class SettingsViewModel(application: Application) : AndroidViewModel(application) {

    private val db = AppDatabase.get(application)
    val prefs = Prefs(application)

    val language: StateFlow<String> = prefs.language.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), "ru")
    val darkTheme: StateFlow<Boolean> = prefs.darkTheme.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), true)
    val sortOrder: StateFlow<ServerListSort> = prefs.sortOrder.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), ServerListSort.NONE)
    val connectOnLaunch: StateFlow<Boolean> = prefs.connectOnLaunch.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)
    val updateOnLaunch: StateFlow<Boolean> = prefs.updateOnLaunch.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)
    val tunnelMode: StateFlow<TunnelMode> = prefs.tunnelMode.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), TunnelMode.TUN)
    val appRoutingMode: StateFlow<AppRoutingMode> = prefs.appRoutingMode.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), AppRoutingMode.ALL_EXCEPT_SELECTED)

    val installedApps: List<InstalledAppInfo> by lazy { AppRoutingManager.listInstalledApps(application) }

    val selectedPackages: StateFlow<Set<String>> = db.appRoutingRuleDao().observeAll()
        .map { list -> list.map { it.packageName }.toSet() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptySet())

    val lanProxyAddress: String get() = "${LanAddress.current() ?: "?.?.?.?"}:${LcVpnService.LAN_PROXY_PORT}"

    private val _lanProxyPassword = MutableStateFlow("")
    val lanProxyPassword: StateFlow<String> = _lanProxyPassword

    init {
        viewModelScope.launch { _lanProxyPassword.value = prefs.lanProxyPassword() }
    }

    fun setLanguage(value: String) = viewModelScope.launch { prefs.setLanguage(value) }
    fun setDarkTheme(value: Boolean) = viewModelScope.launch { prefs.setDarkTheme(value) }
    fun setSortOrder(value: ServerListSort) = viewModelScope.launch { prefs.setSortOrder(value) }
    fun setConnectOnLaunch(value: Boolean) = viewModelScope.launch { prefs.setConnectOnLaunch(value) }
    fun setUpdateOnLaunch(value: Boolean) = viewModelScope.launch { prefs.setUpdateOnLaunch(value) }
    fun setTunnelMode(value: TunnelMode) = viewModelScope.launch { prefs.setTunnelMode(value) }
    fun setAppRoutingMode(value: AppRoutingMode) = viewModelScope.launch { prefs.setAppRoutingMode(value) }

    fun toggleAppSelected(packageName: String, selected: Boolean) {
        viewModelScope.launch {
            if (selected) {
                db.appRoutingRuleDao().insert(AppRoutingRuleEntity(packageName))
            } else {
                db.appRoutingRuleDao().delete(AppRoutingRuleEntity(packageName))
            }
        }
    }

    fun shareLogsIntent() = LogSharing.shareLogsIntent(getApplication())
}

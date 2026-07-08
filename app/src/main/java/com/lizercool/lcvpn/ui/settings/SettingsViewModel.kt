package com.lizercool.lcvpn.ui.settings

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.lizercool.lcvpn.data.db.AppDatabase
import com.lizercool.lcvpn.data.db.entity.AppRoutingRuleEntity
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.IpStackMode
import com.lizercool.lcvpn.data.model.PingMode
import com.lizercool.lcvpn.data.model.RoutingMode
import com.lizercool.lcvpn.data.model.ServerListSort
import com.lizercool.lcvpn.data.model.TunnelMode
import com.lizercool.lcvpn.util.LanAddress
import com.lizercool.lcvpn.util.LogSharing
import com.lizercool.lcvpn.util.Prefs
import com.lizercool.lcvpn.vpn.AppRoutingManager
import com.lizercool.lcvpn.vpn.InstalledAppInfo
import com.lizercool.lcvpn.vpn.LcVpnService
import kotlinx.coroutines.Dispatchers
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
    val killSwitch: StateFlow<Boolean> = prefs.killSwitch.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)
    val pingMode: StateFlow<PingMode> = prefs.pingMode.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), PingMode.PROXY_GET)
    val ipStackMode: StateFlow<IpStackMode> = prefs.ipStackMode.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), IpStackMode.BOTH)
    val sniffing: StateFlow<Boolean> = prefs.sniffing.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), true)
    val idleTimeoutSec: StateFlow<Int> = prefs.idleTimeoutSec.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 300)
    val blockUdp: StateFlow<Boolean> = prefs.blockUdp.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)
    val keepAwake: StateFlow<Boolean> = prefs.keepAwake.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)
    val logRetentionHours: StateFlow<Int> = prefs.logRetentionHours.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 1)
    val routingEnabled: StateFlow<Boolean> = prefs.routingEnabled.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), true)
    val routingMode: StateFlow<RoutingMode> = prefs.routingMode.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), RoutingMode.SMART)
    val directDomains: StateFlow<String> = prefs.directDomains.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), "")
    val proxyDomains: StateFlow<String> = prefs.proxyDomains.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), "")
    val fragmentEnabled: StateFlow<Boolean> = prefs.fragmentEnabled.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)
    val fragmentPackets: StateFlow<String> = prefs.fragmentPackets.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), "tlshello")
    val fragmentLength: StateFlow<String> = prefs.fragmentLength.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), "100-200")
    val fragmentInterval: StateFlow<String> = prefs.fragmentInterval.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), "10-20")
    val muxEnabled: StateFlow<Boolean> = prefs.muxEnabled.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)
    val muxConcurrency: StateFlow<Int> = prefs.muxConcurrency.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 8)
    val memoryLimitMb: StateFlow<Int> = prefs.memoryLimitMb.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 100)
    val memoryUnlimited: StateFlow<Boolean> = prefs.memoryUnlimited.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)

    // Enumerating installed apps + loading each one's label is a real PackageManager cost (can
    // take a noticeable moment with 100+ apps installed) - loading it eagerly/synchronously on
    // the main thread the first time the Connection tab reads it is what was freezing the UI on
    // entry. Loaded lazily in the background instead; starts empty and fills in once ready.
    private val _installedApps = MutableStateFlow<List<InstalledAppInfo>>(emptyList())
    val installedApps: StateFlow<List<InstalledAppInfo>> = _installedApps
    private val _installedAppsLoading = MutableStateFlow(true)
    val installedAppsLoading: StateFlow<Boolean> = _installedAppsLoading

    val selectedPackages: StateFlow<Set<String>> = db.appRoutingRuleDao().observeAll()
        .map { list -> list.map { it.packageName }.toSet() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptySet())

    val lanProxyAddress: String get() = "${LanAddress.current() ?: "?.?.?.?"}:${LcVpnService.LAN_PROXY_PORT}"

    private val _lanProxyPassword = MutableStateFlow("")
    val lanProxyPassword: StateFlow<String> = _lanProxyPassword

    init {
        viewModelScope.launch { _lanProxyPassword.value = prefs.lanProxyPassword() }
        viewModelScope.launch(Dispatchers.Default) {
            val apps = AppRoutingManager.listInstalledApps(getApplication())
            _installedApps.value = apps
            _installedAppsLoading.value = false
        }
    }

    fun setLanguage(value: String) = viewModelScope.launch { prefs.setLanguage(value) }
    fun setDarkTheme(value: Boolean) = viewModelScope.launch { prefs.setDarkTheme(value) }
    fun setSortOrder(value: ServerListSort) = viewModelScope.launch { prefs.setSortOrder(value) }
    fun setConnectOnLaunch(value: Boolean) = viewModelScope.launch { prefs.setConnectOnLaunch(value) }
    fun setUpdateOnLaunch(value: Boolean) = viewModelScope.launch { prefs.setUpdateOnLaunch(value) }
    fun setTunnelMode(value: TunnelMode) = viewModelScope.launch { prefs.setTunnelMode(value) }
    fun setAppRoutingMode(value: AppRoutingMode) = viewModelScope.launch { prefs.setAppRoutingMode(value) }
    fun setKillSwitch(value: Boolean) = viewModelScope.launch { prefs.setKillSwitch(value) }
    fun setPingMode(value: PingMode) = viewModelScope.launch { prefs.setPingMode(value) }
    fun setIpStackMode(value: IpStackMode) = viewModelScope.launch { prefs.setIpStackMode(value) }
    fun setSniffing(value: Boolean) = viewModelScope.launch { prefs.setSniffing(value) }
    fun setIdleTimeoutSec(value: Int) = viewModelScope.launch { prefs.setIdleTimeoutSec(value.coerceIn(30, 3600)) }
    fun setBlockUdp(value: Boolean) = viewModelScope.launch { prefs.setBlockUdp(value) }
    fun setKeepAwake(value: Boolean) = viewModelScope.launch { prefs.setKeepAwake(value) }
    fun setLogRetentionHours(value: Int) = viewModelScope.launch { prefs.setLogRetentionHours(value) }
    fun setRoutingEnabled(value: Boolean) = viewModelScope.launch { prefs.setRoutingEnabled(value) }
    fun setRoutingMode(value: RoutingMode) = viewModelScope.launch { prefs.setRoutingMode(value) }
    fun setDirectDomains(value: String) = viewModelScope.launch { prefs.setDirectDomains(value) }
    fun setProxyDomains(value: String) = viewModelScope.launch { prefs.setProxyDomains(value) }
    fun setFragmentEnabled(value: Boolean) = viewModelScope.launch { prefs.setFragmentEnabled(value) }
    fun setFragmentPackets(value: String) = viewModelScope.launch { prefs.setFragmentPackets(value) }
    fun setFragmentLength(value: String) = viewModelScope.launch { prefs.setFragmentLength(value) }
    fun setFragmentInterval(value: String) = viewModelScope.launch { prefs.setFragmentInterval(value) }
    fun setMuxEnabled(value: Boolean) = viewModelScope.launch { prefs.setMuxEnabled(value) }
    fun setMuxConcurrency(value: Int) = viewModelScope.launch { prefs.setMuxConcurrency(value.coerceIn(1, 128)) }
    fun setMemoryLimitMb(value: Int) = viewModelScope.launch { prefs.setMemoryLimitMb(value) }
    fun setMemoryUnlimited(value: Boolean) = viewModelScope.launch { prefs.setMemoryUnlimited(value) }

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
    fun readLogs(): String = LogSharing.readLogs(getApplication())
    fun clearLogs() = LogSharing.clearLogs(getApplication())
}

package com.lizercool.lcvpn.vpn

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import timber.log.Timber

/**
 * Placeholder engine used until the native Xray-core binding is linked in (see task tracker /
 * commit history for status). It validates and logs the config it was asked to run, reports a
 * "running" state so the rest of the app (timer, UI) can be exercised end-to-end, but does not
 * actually forward any packets yet - no fake traffic numbers are reported, they stay at zero so
 * this is never mistaken for a real connection.
 */
class StubProxyEngine : ProxyEngine {
    private val _stats = MutableStateFlow(ProxyStats())
    override val stats: StateFlow<ProxyStats> = _stats

    private var running = false

    override suspend fun start(configJson: String, tunFd: Int?): Boolean {
        Timber.w("StubProxyEngine.start() called - native Xray-core is not linked in yet, no traffic will actually be tunneled")
        Timber.d("Config that would have been passed to the core: %s", configJson)
        running = true
        return true
    }

    override suspend fun stop() {
        running = false
        _stats.value = ProxyStats()
    }

    override fun isRunning(): Boolean = running
}

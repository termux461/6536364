package com.lizercool.lcvpn.vpn

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import libv2ray.CoreCallbackHandler
import libv2ray.CoreController
import libv2ray.Libv2ray
import timber.log.Timber

/**
 * Wraps the real AndroidLibXrayLite `CoreController` API (github.com/2dust/AndroidLibXrayLite,
 * confirmed against its actual source at tag v26.6.27 - not guessed from memory).
 *
 * Only powers Proxy mode for now: `StartLoop` just needs the config's own SOCKS inbound (see
 * ConfigBuilder), no tun fd or socket-protect callback required since Proxy mode never creates a
 * system VpnService tunnel. TUN mode still needs a tun2socks bridge - not wired yet.
 */
class XrayEngine : ProxyEngine {

    private val _stats = MutableStateFlow(ProxyStats())
    override val stats: StateFlow<ProxyStats> = _stats

    private var controller: CoreController? = null
    private var statsJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.Main)

    override suspend fun start(configJson: String, tunFd: Int?): Boolean = withContext(Dispatchers.IO) {
        // A previous start() may have thrown after Xray-core already bound its inbound ports
        // internally; without releasing that leaked controller first, every retry fails with
        // "address already in use" for the rest of the process's life.
        runCatching { controller?.stopLoop() }
        controller = null

        for (attempt in 1..START_ATTEMPTS) {
            val result = runCatching { startOnce(configJson, tunFd) }
            if (result.isSuccess) return@withContext true

            val error = result.exceptionOrNull()
            if (attempt == START_ATTEMPTS) {
                Timber.e(error, "Failed to start Xray-core after %d attempts", START_ATTEMPTS)
            } else {
                // A port bind failure is often transient (e.g. the previous socket is still in
                // TCP TIME_WAIT after a prior disconnect) and clears up within a couple of
                // seconds, so it's worth a few retries before giving up outright.
                Timber.w(error, "Xray-core start attempt %d/%d failed, retrying", attempt, START_ATTEMPTS)
                delay(RETRY_DELAY_MS)
            }
        }
        false
    }

    private fun startOnce(configJson: String, tunFd: Int?) {
        val callback = object : CoreCallbackHandler {
            override fun startup(): Long {
                Timber.d("Xray-core startup callback")
                return 0
            }
            override fun shutdown(): Long {
                Timber.d("Xray-core shutdown callback")
                return 0
            }
            override fun onEmitStatus(code: Long, message: String?): Long {
                Timber.d("Xray-core status %d: %s", code, message)
                return 0
            }
        }

        val coreController = Libv2ray.newCoreController(callback)
        try {
            coreController.startLoop(configJson, tunFd ?: 0)
        } catch (e: Throwable) {
            // startLoop() can partially bind ports before failing; release them so the
            // next attempt doesn't hit "address already in use" forever.
            runCatching { coreController.stopLoop() }
            throw e
        }
        controller = coreController
        startStatsJob(coreController)
        Timber.i("Xray-core started via CoreController.startLoop")
    }

    private fun startStatsJob(coreController: CoreController) {
        var totalUplink = 0L
        var totalDownlink = 0L
        statsJob = scope.launch {
            while (true) {
                delay(1000)
                runCatching {
                    // Sums every outbound's counters rather than querying a single hardcoded tag,
                    // so this keeps working regardless of how many outbounds a config ends up
                    // with. QueryAllOutboundTrafficStats resets each counter on read, so this
                    // already returns the delta transferred since the previous call.
                    var uplinkDelta = 0L
                    var downlinkDelta = 0L
                    coreController.queryAllOutboundTrafficStats().split(';').forEach { entry ->
                        if (entry.isBlank()) return@forEach
                        val parts = entry.split(',', limit = 3)
                        if (parts.size != 3) return@forEach
                        val value = parts[2].toLongOrNull() ?: return@forEach
                        when (parts[1]) {
                            "uplink" -> uplinkDelta += value
                            "downlink" -> downlinkDelta += value
                        }
                    }
                    totalUplink += uplinkDelta
                    totalDownlink += downlinkDelta
                    _stats.value = ProxyStats(
                        downlinkBytesPerSec = downlinkDelta,
                        uplinkBytesPerSec = uplinkDelta,
                        totalDownlinkBytes = totalDownlink,
                        totalUplinkBytes = totalUplink,
                    )
                }.onFailure { Timber.w(it, "Failed to query Xray-core stats") }
            }
        }
    }

    override suspend fun stop() = withContext(Dispatchers.IO) {
        statsJob?.cancel()
        statsJob = null
        runCatching { controller?.stopLoop() }.onFailure { Timber.w(it, "Failed to stop Xray-core cleanly") }
        controller = null
        _stats.value = ProxyStats()
        Unit
    }

    override fun isRunning(): Boolean = controller?.isRunning ?: false

    companion object {
        private const val START_ATTEMPTS = 4
        private const val RETRY_DELAY_MS = 1500L
    }
}

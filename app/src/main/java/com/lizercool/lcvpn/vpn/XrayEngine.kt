package com.lizercool.lcvpn.vpn

import android.net.VpnService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import libv2ray.Libv2ray
import libv2ray.V2RayPoint
import libv2ray.V2RayVPNServiceSupportsSet
import timber.log.Timber

/**
 * Wraps AndroidLibXrayLite's gomobile-generated `V2RayPoint` (github.com/2dust/AndroidLibXrayLite).
 *
 * This is written from memory of that library's public API without access to a real device or
 * the actual generated bindings to compile-check against - the exact method/field names
 * (runLoop/stopLoop/queryStats, the SupportSet callback signatures) are a best effort and may
 * need correcting once the CI build reports the real symbols.
 *
 * Only powers Proxy mode for now: RunLoop starts the core with a local SOCKS inbound
 * (see ConfigBuilder), which is enough for Proxy mode with no TUN interface involved. TUN mode
 * still needs a tun2socks bridge between the VpnService fd and this SOCKS port - not wired yet.
 */
class XrayEngine(private val vpnService: VpnService) : ProxyEngine {

    private val _stats = MutableStateFlow(ProxyStats())
    override val stats: StateFlow<ProxyStats> = _stats

    private var point: V2RayPoint? = null
    private var statsJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.Main)

    private var lastUplinkTotal = 0L
    private var lastDownlinkTotal = 0L

    override suspend fun start(configJson: String, tunFd: Int?): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            val supportSet = object : V2RayVPNServiceSupportsSet {
                override fun shutdown(): Long = 0
                override fun prepare(): Long = 0
                override fun protect(fd: Long): Boolean = vpnService.protect(fd.toInt())
                override fun onEmitStatus(code: Long, message: String?): Long {
                    Timber.d("Xray status %d: %s", code, message)
                    return 0
                }
                override fun setup(config: String?): Long = 0
            }

            val v2rayPoint = Libv2ray.newV2RayPoint(supportSet, false)
            v2rayPoint.configureFileContent = configJson
            v2rayPoint.domainName = "127.0.0.1:0"
            v2rayPoint.runLoop(false)
            point = v2rayPoint

            statsJob = scope.launch {
                lastUplinkTotal = 0
                lastDownlinkTotal = 0
                while (true) {
                    delay(1000)
                    pollStats(v2rayPoint)
                }
            }

            Timber.i("Xray-core started (proxy mode, SOCKS inbound)")
            true
        }.onFailure {
            Timber.e(it, "Failed to start Xray-core")
        }.getOrDefault(false)
    }

    private fun pollStats(v2rayPoint: V2RayPoint) {
        runCatching {
            val uplinkTotal = v2rayPoint.queryStats("proxy", "uplink")
            val downlinkTotal = v2rayPoint.queryStats("proxy", "downlink")
            val uplinkDelta = (uplinkTotal - lastUplinkTotal).coerceAtLeast(0)
            val downlinkDelta = (downlinkTotal - lastDownlinkTotal).coerceAtLeast(0)
            lastUplinkTotal = uplinkTotal
            lastDownlinkTotal = downlinkTotal
            _stats.value = ProxyStats(
                downlinkBytesPerSec = downlinkDelta,
                uplinkBytesPerSec = uplinkDelta,
                totalDownlinkBytes = downlinkTotal,
                totalUplinkBytes = uplinkTotal,
            )
        }.onFailure { Timber.w(it, "Failed to query Xray-core stats") }
    }

    override suspend fun stop() = withContext(Dispatchers.IO) {
        statsJob?.cancel()
        statsJob = null
        runCatching { point?.stopLoop() }.onFailure { Timber.w(it, "Failed to stop Xray-core cleanly") }
        point = null
        _stats.value = ProxyStats()
        Unit
    }

    override fun isRunning(): Boolean = runCatching { point?.isRunning == true }.getOrDefault(false)
}

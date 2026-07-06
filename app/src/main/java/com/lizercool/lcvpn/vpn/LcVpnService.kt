package com.lizercool.lcvpn.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.VpnService
import android.os.Build
import androidx.core.app.NotificationCompat
import com.lizercool.lcvpn.R
import com.lizercool.lcvpn.data.db.AppDatabase
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.IpStackMode
import com.lizercool.lcvpn.data.model.TunnelMode
import com.lizercool.lcvpn.ui.MainActivity
import com.lizercool.lcvpn.util.Formatting
import com.lizercool.lcvpn.util.GeoAssets
import com.lizercool.lcvpn.util.Prefs
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import timber.log.Timber
import java.util.concurrent.atomic.AtomicBoolean

class LcVpnService : VpnService() {

    private val serviceJob = Job()

    // The notification ticker loop (below) runs unguarded every second for as long as the VPN
    // is connected; without this handler, any exception it throws (e.g. from
    // NotificationManager) is uncaught and kills the whole app process, which then just
    // restarts and repeats - looks like the app "just crashes on launch" with no stack trace
    // anywhere in the Timber-based log, since the crash happens before Timber's own
    // uncaught-exception hook can log it.
    private val exceptionHandler = CoroutineExceptionHandler { _, throwable ->
        Timber.e(throwable, "Unhandled exception in LcVpnService coroutine scope")
    }
    private val scope = CoroutineScope(Dispatchers.Main + serviceJob + exceptionHandler)
    private val engine: ProxyEngine by lazy { XrayEngine() }
    private var parcelFileDescriptor: android.os.ParcelFileDescriptor? = null
    private val isStarting = AtomicBoolean(false)
    private var notificationTickerJob: Job? = null
    private var killSwitchRetryJob: Job? = null
    private var tun2SocksRunning = false
    private var wakeLock: android.os.PowerManager.WakeLock? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_DISCONNECT -> {
                disconnect()
                return START_NOT_STICKY
            }
            else -> connect()
        }
        return START_STICKY
    }

    private fun connect() {
        if (isStarting.getAndSet(true)) return
        state.value = ConnectionState.Connecting
        killSwitchRetryJob?.cancel()
        killSwitchRetryJob = null

        // Android kills the process with ForegroundServiceDidNotStartInTimeException if
        // startForeground() isn't called within a few seconds of Context.startForegroundService()
        // - and killing it mid-connection leaves Xray-core's socket in TIME_WAIT, which is why
        // every retry after that failed with "address already in use". So this must happen
        // synchronously, immediately, before any of the slower async setup below.
        startForeground(NOTIFICATION_ID, buildConnectingNotification())

        scope.launch {
            var usesTunForThisAttempt = false
            var killSwitchEnabled = false
            runCatching {
                val db = AppDatabase.get(this@LcVpnService)
                val prefs = Prefs(this@LcVpnService)
                killSwitchEnabled = prefs.killSwitch.first()

                val server = db.serverDao().observeSelected().first() ?: error("No server selected")

                val tunnelMode = prefs.tunnelMode.first()
                // Not hardcoded to the conventional 10808: that's the default local SOCKS port
                // for many v2ray/xray-based apps, so if another one is also running it can
                // squat that exact port with nothing we can do about it (we can't stop another
                // app's process). This port is purely internal - hev-socks5-tunnel is the only
                // other thing that needs to know it - so a fresh free port each connect avoids
                // that collision entirely.
                val socksPort = findFreeLoopbackPort()
                val usesTun = tunnelMode == TunnelMode.TUN || tunnelMode == TunnelMode.TUN_AND_PROXY
                usesTunForThisAttempt = usesTun
                val lanProxyPassword = if (tunnelMode == TunnelMode.TUN_AND_PROXY) prefs.lanProxyPassword() else null
                val geoRouting = GeoAssets.available
                val sniffing = prefs.sniffing.first()
                val blockUdp = prefs.blockUdp.first()
                val idleTimeoutSec = prefs.idleTimeoutSec.first()
                if (prefs.keepAwake.first()) acquireWakeLock()
                val configJson = ConfigBuilder.build(
                    server, tunnelMode, socksPort, LAN_PROXY_PORT, lanProxyPassword,
                    geoRouting = geoRouting, sniffing = sniffing, blockUdp = blockUdp,
                )

                var tun: TunResult? = null
                if (usesTun) {
                    tun = establishTun(prefs)
                }

                // Xray-core is only ever used here for its own local SOCKS inbound (see
                // ConfigBuilder) - hev-socks5-tunnel is what bridges the raw tun fd separately,
                // below. Handing the same tunFd to CoreController.startLoop() too makes
                // AndroidLibXrayLite set the "xray.tun.fd" env var, which tells Xray-core's own
                // dialer to also attach to that fd - two different native runtimes (Go's
                // xray-core and hev-socks5-tunnel's C code) then fight over the same file
                // descriptor, which is what was crashing the process a few seconds after every
                // successful TUN connect with no catchable Kotlin exception.
                var started = engine.start(configJson, null)
                if (!started && geoRouting) {
                    // The geo-enabled config couldn't start the core (most often because the
                    // geoip/geosite .dat files aren't resolvable on this device). Rather than fail
                    // the whole connection - as happened in the field, where every retry re-used
                    // the same broken config - rebuild without geo routing and try once more so
                    // the user still gets a working (proxy-everything) tunnel.
                    Timber.w("Connect with geo routing failed; retrying without geosite/geoip rules")
                    val fallbackConfig = ConfigBuilder.build(
                        server, tunnelMode, socksPort, LAN_PROXY_PORT, lanProxyPassword,
                        geoRouting = false, sniffing = sniffing, blockUdp = blockUdp,
                    )
                    started = engine.start(fallbackConfig, null)
                }
                if (!started) error("Proxy engine failed to start")

                if (usesTun && tun != null) {
                    val v6 = if (tun.hasIpv6) TUN_ADDRESS_V6 else null
                    HevSocks5Tunnel.start(this@LcVpnService, tun.fd, socksPort, TUN_MTU, TUN_ADDRESS, v6, idleTimeoutSec)
                    tun2SocksRunning = true
                    Timber.i("hev-socks5-tunnel bridging tun fd %d to 127.0.0.1:%d", tun.fd, socksPort)
                }
                if (tunnelMode == TunnelMode.TUN_AND_PROXY) {
                    Timber.i("LAN proxy listening on 0.0.0.0:%d (user=lcvpn)", LAN_PROXY_PORT)
                }

                val connectedAt = System.currentTimeMillis()
                startForeground(NOTIFICATION_ID, buildNotification(server.name, connectedAt, engine.stats.value))
                state.value = ConnectionState.Connected(connectedAt, server.name)
                startNotificationTicker(server.name, connectedAt)
                Timber.i("VPN connected to %s (%s mode)", server.name, tunnelMode)
            }.onFailure { e ->
                Timber.e(e, "Failed to connect")
                val message = describeConnectError(e)
                state.value = ConnectionState.Error(message)

                if (killSwitchEnabled && usesTunForThisAttempt && parcelFileDescriptor != null) {
                    // Kill switch: the TUN interface is already routing all device traffic and
                    // stays up - so instead of tearing it down (which would fall back to the
                    // raw, unprotected network), leave it blocking everything and keep retrying
                    // in the background until the proxy comes back.
                    Timber.w("Kill switch active - keeping traffic blocked and retrying instead of disconnecting")
                    startForeground(NOTIFICATION_ID, buildBlockedNotification(message))
                    killSwitchRetryJob = scope.launch {
                        delay(KILL_SWITCH_RETRY_DELAY_MS)
                        connect()
                    }
                } else {
                    showErrorNotification(message)
                    stopForeground(STOP_FOREGROUND_REMOVE)
                    stopSelf()
                }
            }
            isStarting.set(false)
        }
    }

    private fun findFreeLoopbackPort(): Int =
        java.net.ServerSocket(0, 1, java.net.InetAddress.getByName("127.0.0.1")).use { it.localPort }

    /** Optional partial wakelock - keeps the tunnel alive under aggressive OEM dozing (Xiaomi/HyperOS). */
    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        runCatching {
            val pm = getSystemService(android.os.PowerManager::class.java)
            wakeLock = pm.newWakeLock(android.os.PowerManager.PARTIAL_WAKE_LOCK, "lcvpn:tunnel").apply {
                setReferenceCounted(false)
                acquire()
            }
        }.onFailure { Timber.w(it, "Failed to acquire wakelock") }
    }

    private fun releaseWakeLock() {
        runCatching { wakeLock?.takeIf { it.isHeld }?.release() }
        wakeLock = null
    }

    private data class TunResult(val fd: Int, val hasIpv6: Boolean)

    private suspend fun establishTun(prefs: Prefs): TunResult {
        // User-selectable IP stack (Настройки → Подключение → «IP-стек»):
        //   BOTH (default) captures IPv4 + IPv6, IPV4_ONLY / IPV6_ONLY capture just the one.
        val ipStackMode = prefs.ipStackMode.first()
        val useV4 = ipStackMode != IpStackMode.IPV6_ONLY
        val useV6 = ipStackMode != IpStackMode.IPV4_ONLY

        val builder = Builder()
            .setSession(getString(R.string.app_name))
            .addDnsServer("1.1.1.1")
            .addDnsServer("8.8.8.8")
            .setMtu(TUN_MTU)

        if (useV4) {
            builder.addAddress(TUN_ADDRESS, 32)
            builder.addRoute("0.0.0.0", 0)
        }
        // Capturing IPv6 matters because without an IPv6 address+route every IPv6-capable app
        // (YouTube, Google, Instagram, ...) reaches its destination over IPv6 straight past the
        // tun - so "all traffic goes through the VPN" silently becomes "only the IPv4 half does".
        // hev-socks5-tunnel is told about the same v6 client address so it forwards those packets
        // into the SOCKS proxy.
        var hasIpv6 = false
        if (useV6) {
            runCatching {
                builder.addAddress(TUN_ADDRESS_V6, 128)
                builder.addRoute("::", 0)
                hasIpv6 = true
            }.onFailure { Timber.w(it, "Failed to add IPv6 tun address/route; IPv6 may leak") }
        }

        applyAppRouting(builder, prefs)

        val pfd = builder.establish() ?: error("VpnService.Builder.establish() returned null (permission not granted?)")
        // Close the previous fd only after the new one is up (relevant for kill-switch retries):
        // establish() atomically replaces this app's active tun interface, so there's no gap
        // where traffic could leak out unprotected between the old and new one.
        val previous = parcelFileDescriptor
        parcelFileDescriptor = pfd
        previous?.close()
        return TunResult(pfd.fd, hasIpv6)
    }

    private suspend fun applyAppRouting(builder: Builder, prefs: Prefs) {
        val db = AppDatabase.get(this)
        val selectedPackages = db.appRoutingRuleDao().observeAll().first().map { it.packageName }
        val mode = prefs.appRoutingMode.first()

        if (selectedPackages.isNotEmpty() && mode == AppRoutingMode.ONLY_SELECTED) {
            // Only-selected: just these apps' traffic enters the tunnel. Our own package isn't in
            // the list, so Xray-core's own sockets stay off-tunnel automatically - and Android
            // forbids mixing addAllowed* with addDisallowed*, so we can't also exclude ourselves
            // explicitly here (we don't need to).
            runCatching {
                selectedPackages.forEach { builder.addAllowedApplication(it) }
            }.onFailure { Timber.w(it, "Failed applying per-app allow rule") }
            return
        }

        // Default (nothing selected) and all-except-selected: everything is tunnelled except the
        // excluded apps. Our OWN package must always be excluded: Xray-core and hev-socks5-tunnel
        // both run inside this process, and if Xray's outbound sockets to the VPN server were
        // themselves routed back into the tun they'd loop forever - which is why hardly any
        // traffic actually made it out. Excluding ourselves is the standard tun2socks fix.
        runCatching {
            builder.addDisallowedApplication(packageName)
            if (mode == AppRoutingMode.ALL_EXCEPT_SELECTED) {
                selectedPackages.forEach { pkg ->
                    if (pkg != packageName) builder.addDisallowedApplication(pkg)
                }
            }
        }.onFailure { Timber.w(it, "Failed applying per-app routing rule") }
    }

    private fun startNotificationTicker(serverName: String, connectedAt: Long) {
        notificationTickerJob?.cancel()
        notificationTickerJob = scope.launch {
            val manager = getSystemService(NotificationManager::class.java)
            while (isActive) {
                runCatching {
                    val stats = engine.stats.value
                    _stats.value = stats
                    manager.notify(NOTIFICATION_ID, buildNotification(serverName, connectedAt, stats))
                }.onFailure { Timber.w(it, "Failed to update connection notification") }
                delay(1000)
            }
        }
    }

    private fun disconnect() {
        killSwitchRetryJob?.cancel()
        killSwitchRetryJob = null
        notificationTickerJob?.cancel()
        notificationTickerJob = null
        stopTun2Socks()
        releaseWakeLock()
        scope.launch {
            engine.stop()
            parcelFileDescriptor?.close()
            parcelFileDescriptor = null
            state.value = ConnectionState.Disconnected
            _stats.value = ProxyStats()
            Timber.i("VPN disconnected")
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun stopTun2Socks() {
        if (!tun2SocksRunning) return
        runCatching { HevSocks5Tunnel.stop() }.onFailure { Timber.w(it, "Failed to stop hev-socks5-tunnel cleanly") }
        tun2SocksRunning = false
    }

    override fun onDestroy() {
        killSwitchRetryJob?.cancel()
        notificationTickerJob?.cancel()
        stopTun2Socks()
        releaseWakeLock()
        serviceJob.cancel()
        parcelFileDescriptor?.close()
        super.onDestroy()
    }

    override fun onRevoke() {
        disconnect()
        super.onRevoke()
    }

    /** Turns a raw exception into a short message the user can actually act on. */
    private fun describeConnectError(e: Throwable): String = when {
        e.message?.contains("address already in use", ignoreCase = true) == true ->
            "Порт занят другим приложением. Попробуй закрыть другие VPN/прокси и подключиться снова."
        else -> e.message ?: "Неизвестная ошибка"
    }

    /** A one-shot, dismissible alert - separate from the ongoing connection notification - so a
     *  failed connect is visible even if the user isn't looking at the app right now. */
    private fun showErrorNotification(message: String) {
        ensureNotificationChannel()
        val notification = baseNotificationBuilder()
            .setContentTitle("LC VPN: не удалось подключиться")
            .setContentText(message)
            .setOngoing(false)
            .setAutoCancel(true)
            .build()
        runCatching {
            getSystemService(NotificationManager::class.java).notify(ERROR_NOTIFICATION_ID, notification)
        }.onFailure { Timber.w(it, "Failed to show connect-error notification") }
    }

    private fun buildConnectingNotification(): Notification {
        ensureNotificationChannel()
        return baseNotificationBuilder()
            .setContentTitle("LC VPN")
            .setContentText("Подключение...")
            .build()
    }

    /** Shown while the kill switch is holding traffic blocked between reconnect attempts. */
    private fun buildBlockedNotification(message: String): Notification {
        ensureNotificationChannel()
        return baseNotificationBuilder()
            .setContentTitle("LC VPN: трафик заблокирован (Kill Switch)")
            .setContentText("$message Переподключение...")
            .build()
    }

    private fun buildNotification(serverName: String, connectedAt: Long, stats: ProxyStats): Notification {
        ensureNotificationChannel()
        val elapsed = Formatting.elapsed(connectedAt)
        val speedLine = "↓ ${Formatting.speed(stats.downlinkBytesPerSec)}   ↑ ${Formatting.speed(stats.uplinkBytesPerSec)}"

        return baseNotificationBuilder()
            .setContentTitle("$serverName · $elapsed")
            .setContentText(speedLine)
            .build()
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "LC VPN", NotificationManager.IMPORTANCE_LOW))
        }
    }

    private fun baseNotificationBuilder(): NotificationCompat.Builder {
        val contentIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(contentIntent)
    }

    companion object {
        const val ACTION_CONNECT = "com.lizercool.lcvpn.CONNECT"
        const val ACTION_DISCONNECT = "com.lizercool.lcvpn.DISCONNECT"
        private const val CHANNEL_ID = "lcvpn_status"
        private const val NOTIFICATION_ID = 1
        private const val ERROR_NOTIFICATION_ID = 2
        private const val KILL_SWITCH_RETRY_DELAY_MS = 5000L
        private const val TUN_ADDRESS = "10.10.10.1"
        private const val TUN_ADDRESS_V6 = "fd00:1:2:3::1"
        private const val TUN_MTU = 1500
        const val LAN_PROXY_PORT = 10809

        val state = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
        val stateFlow: StateFlow<ConnectionState> = state

        private val _stats = MutableStateFlow(ProxyStats())
        val statsFlow: StateFlow<ProxyStats> = _stats
    }
}

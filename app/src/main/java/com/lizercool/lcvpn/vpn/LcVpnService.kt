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
import com.lizercool.lcvpn.data.db.entity.ServerEntity
import com.lizercool.lcvpn.data.model.AppRoutingMode
import com.lizercool.lcvpn.data.model.TunnelMode
import com.lizercool.lcvpn.ui.MainActivity
import com.lizercool.lcvpn.util.Formatting
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
    private var tun2SocksRunning = false

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

        // Android kills the process with ForegroundServiceDidNotStartInTimeException if
        // startForeground() isn't called within a few seconds of Context.startForegroundService()
        // - and killing it mid-connection leaves Xray-core's socket in TIME_WAIT, which is why
        // every retry after that failed with "address already in use". So this must happen
        // synchronously, immediately, before any of the slower async setup below.
        startForeground(NOTIFICATION_ID, buildConnectingNotification())

        scope.launch {
            runCatching {
                val db = AppDatabase.get(this@LcVpnService)
                val prefs = Prefs(this@LcVpnService)
                val server = db.serverDao().observeSelected().first()
                    ?: error("No server selected")

                val tunnelMode = prefs.tunnelMode.first()
                val socksPort = 10808
                val usesTun = tunnelMode == TunnelMode.TUN || tunnelMode == TunnelMode.TUN_AND_PROXY
                val lanProxyPassword = if (tunnelMode == TunnelMode.TUN_AND_PROXY) prefs.lanProxyPassword() else null
                val configJson = ConfigBuilder.build(server, tunnelMode, socksPort, LAN_PROXY_PORT, lanProxyPassword)

                var tunFd: Int? = null
                if (usesTun) {
                    tunFd = establishTun(prefs)
                }

                val started = engine.start(configJson, tunFd)
                if (!started) error("Proxy engine failed to start")

                if (usesTun && tunFd != null) {
                    HevSocks5Tunnel.start(this@LcVpnService, tunFd, socksPort, TUN_MTU, TUN_ADDRESS)
                    tun2SocksRunning = true
                    Timber.i("hev-socks5-tunnel bridging tun fd %d to 127.0.0.1:%d", tunFd, socksPort)
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
                state.value = ConnectionState.Error(e.message ?: "Unknown error")
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
            isStarting.set(false)
        }
    }

    private suspend fun establishTun(prefs: Prefs): Int {
        val builder = Builder()
            .setSession(getString(R.string.app_name))
            .addAddress(TUN_ADDRESS, 32)
            .addRoute("0.0.0.0", 0)
            .addDnsServer("1.1.1.1")
            .addDnsServer("8.8.8.8")
            .setMtu(TUN_MTU)

        applyAppRouting(builder, prefs)

        val pfd = builder.establish() ?: error("VpnService.Builder.establish() returned null (permission not granted?)")
        parcelFileDescriptor = pfd
        return pfd.fd
    }

    private suspend fun applyAppRouting(builder: Builder, prefs: Prefs) {
        val db = AppDatabase.get(this)
        val selectedPackages = db.appRoutingRuleDao().observeAll().first().map { it.packageName }
        if (selectedPackages.isEmpty()) return

        val mode = prefs.appRoutingMode.first()
        runCatching {
            when (mode) {
                AppRoutingMode.ONLY_SELECTED -> selectedPackages.forEach { builder.addAllowedApplication(it) }
                AppRoutingMode.ALL_EXCEPT_SELECTED -> selectedPackages.forEach { builder.addDisallowedApplication(it) }
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
        notificationTickerJob?.cancel()
        notificationTickerJob = null
        stopTun2Socks()
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
        notificationTickerJob?.cancel()
        stopTun2Socks()
        serviceJob.cancel()
        parcelFileDescriptor?.close()
        super.onDestroy()
    }

    override fun onRevoke() {
        disconnect()
        super.onRevoke()
    }

    private fun buildConnectingNotification(): Notification {
        ensureNotificationChannel()
        return baseNotificationBuilder()
            .setContentTitle("LC VPN")
            .setContentText("Подключение...")
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
        private const val TUN_ADDRESS = "10.10.10.1"
        private const val TUN_MTU = 1500
        const val LAN_PROXY_PORT = 10809

        val state = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
        val stateFlow: StateFlow<ConnectionState> = state

        private val _stats = MutableStateFlow(ProxyStats())
        val statsFlow: StateFlow<ProxyStats> = _stats
    }
}

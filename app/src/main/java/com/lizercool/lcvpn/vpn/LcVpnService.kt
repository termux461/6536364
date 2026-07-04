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
    private val scope = CoroutineScope(Dispatchers.Main + serviceJob)
    private val engine: ProxyEngine by lazy { XrayEngine() }
    private var parcelFileDescriptor: android.os.ParcelFileDescriptor? = null
    private val isStarting = AtomicBoolean(false)
    private var notificationTickerJob: Job? = null

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

        scope.launch {
            runCatching {
                val db = AppDatabase.get(this@LcVpnService)
                val prefs = Prefs(this@LcVpnService)
                val server = db.serverDao().observeSelected().first()
                    ?: error("No server selected")

                val tunnelMode = prefs.tunnelMode.first()
                val socksPort = 10808
                val configJson = ConfigBuilder.build(server, tunnelMode, socksPort)

                var tunFd: Int? = null
                if (tunnelMode == TunnelMode.TUN) {
                    Timber.w(
                        "TUN mode captures all device traffic into a tun fd, but no " +
                            "tun2socks bridge is wired in yet - captured packets go nowhere " +
                            "and the device will appear to lose internet access while connected.",
                    )
                    tunFd = establishTun(prefs)
                }

                val started = engine.start(configJson, tunFd)
                if (!started) error("Proxy engine failed to start")

                val connectedAt = System.currentTimeMillis()
                startForeground(NOTIFICATION_ID, buildNotification(server.name, connectedAt, engine.stats.value))
                state.value = ConnectionState.Connected(connectedAt, server.name)
                startNotificationTicker(server.name, connectedAt)
                Timber.i("VPN connected to %s (%s mode)", server.name, tunnelMode)
            }.onFailure { e ->
                Timber.e(e, "Failed to connect")
                state.value = ConnectionState.Error(e.message ?: "Unknown error")
                stopSelf()
            }
            isStarting.set(false)
        }
    }

    private suspend fun establishTun(prefs: Prefs): Int {
        val builder = Builder()
            .setSession(getString(R.string.app_name))
            .addAddress("10.10.10.1", 32)
            .addRoute("0.0.0.0", 0)
            .addDnsServer("1.1.1.1")
            .addDnsServer("8.8.8.8")
            .setMtu(1500)

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
                val stats = engine.stats.value
                _stats.value = stats
                manager.notify(NOTIFICATION_ID, buildNotification(serverName, connectedAt, stats))
                delay(1000)
            }
        }
    }

    private fun disconnect() {
        notificationTickerJob?.cancel()
        notificationTickerJob = null
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

    override fun onDestroy() {
        notificationTickerJob?.cancel()
        serviceJob.cancel()
        parcelFileDescriptor?.close()
        super.onDestroy()
    }

    override fun onRevoke() {
        disconnect()
        super.onRevoke()
    }

    private fun buildNotification(serverName: String, connectedAt: Long, stats: ProxyStats): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "LC VPN", NotificationManager.IMPORTANCE_LOW)
            manager.createNotificationChannel(channel)
        }

        val contentIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )

        val elapsed = Formatting.elapsed(connectedAt)
        val speedLine = "↓ ${Formatting.speed(stats.downlinkBytesPerSec)}   ↑ ${Formatting.speed(stats.uplinkBytesPerSec)}"

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle("$serverName · $elapsed")
            .setContentText(speedLine)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(contentIntent)
            .build()
    }

    companion object {
        const val ACTION_CONNECT = "com.lizercool.lcvpn.CONNECT"
        const val ACTION_DISCONNECT = "com.lizercool.lcvpn.DISCONNECT"
        private const val CHANNEL_ID = "lcvpn_status"
        private const val NOTIFICATION_ID = 1

        val state = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
        val stateFlow: StateFlow<ConnectionState> = state

        private val _stats = MutableStateFlow(ProxyStats())
        val statsFlow: StateFlow<ProxyStats> = _stats
    }
}

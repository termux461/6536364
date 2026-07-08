package com.lizercool.lcvpn

import android.app.Application
import com.lizercool.lcvpn.util.FileLogTree
import com.lizercool.lcvpn.util.GeoAssets
import com.lizercool.lcvpn.util.Prefs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import libv2ray.Libv2ray
import timber.log.Timber

class LcVpnApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // Verbose logcat only in debug builds; release keeps just the on-device file log (used by
        // the in-app viewer / share-logs) - no logcat spam or info leakage in production.
        if (BuildConfig.DEBUG) Timber.plant(Timber.DebugTree())
        Timber.plant(FileLogTree(this))
        Timber.i("LC VPN started, versionName=%s", BuildConfig.VERSION_NAME)

        // Trim old logs per the user's retention setting (Расширенные → «Хранение логов»).
        CoroutineScope(Dispatchers.IO).launch {
            runCatching { FileLogTree.pruneOldLogs(this@LcVpnApp, Prefs(this@LcVpnApp).logRetentionHours.first()) }
        }

        // Cap / tune the Go (Xray-core) runtime's memory BEFORE the native lib loads. Read from
        // the process env at Go runtime init, so this must run before any libv2ray call.
        //  - GODEBUG=madvdontneed=1: hand freed pages back to the OS promptly (much lower RSS).
        //  - GOGC=40: collect sooner (target 40% heap growth instead of 100%) - trades a little
        //    CPU for a noticeably smaller peak, which is what we want on a phone.
        //  - GOMEMLIMIT: soft cap the GC aims to stay under.
        runCatching {
            val prefs = Prefs(this)
            val unlimited = kotlinx.coroutines.runBlocking { prefs.memoryUnlimitedOnce() }
            android.system.Os.setenv("GODEBUG", "madvdontneed=1", true)
            android.system.Os.setenv("GOGC", if (unlimited) "80" else "40", true)
            if (!unlimited) {
                val mb = kotlinx.coroutines.runBlocking { prefs.memoryLimitMbOnce() }
                android.system.Os.setenv("GOMEMLIMIT", "${mb}MiB", true)
            }
        }.onFailure { Timber.w(it, "Failed to apply Go memory limit env") }

        // Xray-core resolves "geosite:"/"geoip:" routing rule prefixes by opening geoip.dat/
        // geosite.dat as plain files on disk - it can't read them straight out of the APK's
        // assets/, so they're extracted to real storage first and that real directory is what
        // gets handed to initCoreEnv().
        val assetsDir = GeoAssets.extractTo(this)
        runCatching { Libv2ray.initCoreEnv(assetsDir.absolutePath, "") }
            .onFailure { Timber.w(it, "Failed to init Xray-core env (geoip/geosite routing may not work)") }

        // Without this, an uncaught exception (JVM-level - not a native Xray-core crash) kills
        // the process before Timber ever sees it, leaving the log file silent about why the app
        // died. Log it, then hand off to the default handler so the crash still surfaces/reports
        // normally.
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            Timber.e(throwable, "FATAL uncaught exception on thread %s", thread.name)
            defaultHandler?.uncaughtException(thread, throwable)
        }
    }
}

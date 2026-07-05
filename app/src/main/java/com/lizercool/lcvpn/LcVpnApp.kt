package com.lizercool.lcvpn

import android.app.Application
import com.lizercool.lcvpn.util.FileLogTree
import libv2ray.Libv2ray
import timber.log.Timber

class LcVpnApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Timber.plant(Timber.DebugTree())
        Timber.plant(FileLogTree(this))
        Timber.i("LC VPN started, versionName=%s", BuildConfig.VERSION_NAME)

        // Installs Xray-core's asset-fallback file reader (falls back to reading straight out
        // of the APK's assets/ by filename when a literal filesystem path doesn't exist) -
        // without calling this once, "geosite:"/"geoip:" entries in ConfigBuilder's routing
        // rules can never resolve geoip.dat/geosite.dat at all.
        runCatching { Libv2ray.initCoreEnv("", "") }
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

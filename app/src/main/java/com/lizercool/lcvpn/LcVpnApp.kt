package com.lizercool.lcvpn

import android.app.Application
import com.lizercool.lcvpn.util.FileLogTree
import timber.log.Timber

class LcVpnApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Timber.plant(Timber.DebugTree())
        Timber.plant(FileLogTree(this))
        Timber.i("LC VPN started, versionName=%s", BuildConfig.VERSION_NAME)
    }
}

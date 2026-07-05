package com.lizercool.lcvpn.util

import android.content.Context
import timber.log.Timber
import java.io.File

/**
 * Xray-core's geodata loader (the thing that resolves "geosite:"/"geoip:" routing rule prefixes)
 * opens geoip.dat/geosite.dat via a plain Go `os.Open` on the directory passed to
 * `Libv2ray.initCoreEnv()` - it has no notion of Android's APK assets, so pointing it at ""
 * (or at the assets/ path directly) just makes it fall through to some unrelated default path
 * (observed on-device: it tried "/system/bin/geosite.dat"). The .dat files have to be copied out
 * to real on-disk storage once, and that real directory handed to initCoreEnv().
 */
object GeoAssets {
    private const val GEOIP_NAME = "geoip.dat"
    private const val GEOSITE_NAME = "geosite.dat"

    /**
     * Whether both .dat files actually made it to disk. ConfigBuilder checks this and drops the
     * "geosite:"/"geoip:" routing rules when false, because Xray-core refuses to start at all on
     * a config whose geo rules can't resolve - a degraded config that connects beats a perfect
     * one that doesn't.
     */
    @Volatile
    var available: Boolean = false
        private set

    fun extractTo(context: Context): File {
        val dir = File(context.filesDir, "xray-assets").apply { mkdirs() }
        copyAsset(context, GEOIP_NAME, File(dir, GEOIP_NAME))
        copyAsset(context, GEOSITE_NAME, File(dir, GEOSITE_NAME))
        available = File(dir, GEOIP_NAME).length() > 0 && File(dir, GEOSITE_NAME).length() > 0
        if (!available) Timber.w("geoip/geosite data unavailable - geo routing rules will be skipped")
        return dir
    }

    private fun copyAsset(context: Context, assetName: String, target: File) {
        runCatching {
            context.assets.open(assetName).use { input ->
                target.outputStream().use { output -> input.copyTo(output) }
            }
        }.onFailure { Timber.w(it, "Failed to extract %s from assets", assetName) }
    }
}

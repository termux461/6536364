package com.lizercool.lcvpn.util

import android.annotation.SuppressLint
import android.content.Context
import android.os.Build
import android.provider.Settings

/**
 * Stable per-device identity sent to the subscription panel so Remnawave's HWID device-limit /
 * device-binding feature can recognize this install. The panel reads these as request headers
 * (x-hwid, x-device-os, x-ver-os, x-device-model) plus a Happ-style User-Agent, exactly like the
 * Happ client does.
 */
object DeviceInfo {
    private const val PREFS = "lcvpn_device"
    private const val KEY_HWID = "hwid"
    private const val KEY_INSTALL_ID = "install_id"
    private const val HEX = "0123456789abcdef"

    private fun sp(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /**
     * 16-hex-char hardware id. Seeded from ANDROID_ID (which is exactly this shape) and then
     * cached, so it stays stable even if ANDROID_ID later changes (e.g. across some updates).
     */
    @SuppressLint("HardwareIds")
    fun hwid(context: Context): String {
        sp(context).getString(KEY_HWID, null)?.let { return it }
        val androidId = runCatching {
            Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        }.getOrNull()
        // "9774d56d682e549c" is the well-known buggy emulator/pre-8.0 constant - don't trust it.
        val hwid = if (!androidId.isNullOrBlank() && androidId != "9774d56d682e549c") {
            androidId
        } else {
            (0 until 16).joinToString("") { HEX[HEX.indices.random()].toString() }
        }
        sp(context).edit().putString(KEY_HWID, hwid).apply()
        return hwid
    }

    /** 20-digit numeric install id, like Happ's, generated once and reused. */
    fun installId(context: Context): String {
        sp(context).getString(KEY_INSTALL_ID, null)?.let { return it }
        val id = buildString {
            append(('1'..'9').random())
            repeat(19) { append(('0'..'9').random()) }
        }
        sp(context).edit().putString(KEY_INSTALL_ID, id).apply()
        return id
    }

    private const val OS_NAME = "Android"
    private val osVersion: String get() = Build.VERSION.RELEASE ?: Build.VERSION.SDK_INT.toString()
    private val deviceModel: String get() = Build.MODEL ?: "Android"

    /** Happ-style UA so the panel serves the xray-json subscription format. */
    fun happUserAgent(context: Context): String = "Happ/1.8.0/Android/${installId(context)}"

    /** HWID headers Remnawave reads for device binding / device-limit. */
    fun subscriptionHeaders(context: Context): Map<String, String> = mapOf(
        "x-hwid" to hwid(context),
        "x-device-os" to OS_NAME,
        "x-ver-os" to osVersion,
        "x-device-model" to deviceModel,
    )
}

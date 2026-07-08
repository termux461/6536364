package com.lizercool.lcvpn.vpn

import android.content.Context
import android.content.pm.PackageManager

data class InstalledAppInfo(
    val packageName: String,
    val label: String,
)

object AppRoutingManager {
    fun listInstalledApps(context: Context): List<InstalledAppInfo> {
        val pm = context.packageManager
        val apps = pm.getInstalledApplications(PackageManager.GET_META_DATA)
        return apps
            .filter { it.packageName != context.packageName }
            .map { InstalledAppInfo(it.packageName, it.loadLabel(pm).toString()) }
            .sortedBy { it.label.lowercase() }
    }
}

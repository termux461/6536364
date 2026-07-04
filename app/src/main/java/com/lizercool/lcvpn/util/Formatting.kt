package com.lizercool.lcvpn.util

import java.util.Locale

/** Shared formatting for the connection timer and traffic speed shown in the notification and Home screen. */
object Formatting {

    fun elapsed(sinceEpochMs: Long, nowEpochMs: Long = System.currentTimeMillis()): String {
        val totalSeconds = ((nowEpochMs - sinceEpochMs) / 1000).coerceAtLeast(0)
        val hours = totalSeconds / 3600
        val minutes = (totalSeconds % 3600) / 60
        val seconds = totalSeconds % 60
        return if (hours > 0) {
            "%02d:%02d:%02d".format(hours, minutes, seconds)
        } else {
            "%02d:%02d".format(minutes, seconds)
        }
    }

    fun speed(bytesPerSec: Long): String {
        if (bytesPerSec < 1024) return "$bytesPerSec Б/s"
        val units = arrayOf("КБ/s", "МБ/s", "ГБ/s")
        var value = bytesPerSec / 1024.0
        var unitIndex = 0
        while (value >= 1024 && unitIndex < units.lastIndex) {
            value /= 1024
            unitIndex++
        }
        return "%.1f %s".format(Locale.US, value, units[unitIndex])
    }

    fun bytes(total: Long): String {
        if (total <= 0) return "0 Б"
        val units = arrayOf("Б", "КБ", "МБ", "ГБ", "ТБ")
        var value = total.toDouble()
        var unitIndex = 0
        while (value >= 1024 && unitIndex < units.lastIndex) {
            value /= 1024
            unitIndex++
        }
        return "%.1f %s".format(Locale.US, value, units[unitIndex])
    }
}

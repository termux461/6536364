package com.lizercool.lcvpn.util

import android.content.Context
import android.util.Log
import timber.log.Timber
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Writes every log line to a rotating file under filesDir/logs so the user can export it
 * (Settings -> About -> "Поделиться логами") and send it back for debugging.
 */
class FileLogTree(context: Context) : Timber.Tree() {

    private val logsDir = File(context.filesDir, "logs").apply { mkdirs() }
    private val currentFile: File
        get() = File(logsDir, "lcvpn.log")

    private val maxFileBytes = 2L * 1024 * 1024
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)

    override fun log(priority: Int, tag: String?, message: String, t: Throwable?) {
        rotateIfNeeded()
        val level = priorityToLabel(priority)
        val line = buildString {
            append(dateFormat.format(Date()))
            append(' ')
            append(level)
            append(' ')
            append(tag ?: "LcVpn")
            append(": ")
            append(message)
            if (t != null) {
                append('\n')
                append(Log.getStackTraceString(t))
            }
            append('\n')
        }
        runCatching {
            currentFile.appendText(line)
        }
    }

    private fun rotateIfNeeded() {
        if (currentFile.exists() && currentFile.length() > maxFileBytes) {
            val rolled = File(logsDir, "lcvpn.old.log")
            rolled.delete()
            currentFile.renameTo(rolled)
        }
    }

    private fun priorityToLabel(priority: Int): String = when (priority) {
        Log.VERBOSE -> "V"
        Log.DEBUG -> "D"
        Log.INFO -> "I"
        Log.WARN -> "W"
        Log.ERROR -> "E"
        Log.ASSERT -> "A"
        else -> "?"
    }

    companion object {
        fun logsDirectory(context: Context): File = File(context.filesDir, "logs")
    }
}

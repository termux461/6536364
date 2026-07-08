package com.lizercool.lcvpn.util

import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import java.io.File

object LogSharing {

    /** Reads the current + rolled log files, oldest first, for the in-app console viewer. */
    fun readLogs(context: Context): String {
        val dir = FileLogTree.logsDirectory(context)
        val old = File(dir, "lcvpn.old.log")
        val current = File(dir, "lcvpn.log")
        return buildString {
            if (old.exists()) runCatching { append(old.readText()) }
            if (current.exists()) runCatching { append(current.readText()) }
        }
    }

    fun clearLogs(context: Context) {
        FileLogTree.logsDirectory(context).listFiles()?.forEach { runCatching { it.delete() } }
    }

    fun shareLogsIntent(context: Context): Intent? {
        val dir = FileLogTree.logsDirectory(context)
        val files = dir.listFiles()?.filter { it.isFile } ?: emptyList()
        if (files.isEmpty()) return null

        val uris = files.map { file: File ->
            FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        }

        val intent = Intent(Intent.ACTION_SEND_MULTIPLE).apply {
            type = "text/plain"
            putParcelableArrayListExtra(Intent.EXTRA_STREAM, ArrayList(uris))
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        return Intent.createChooser(intent, "Отправить логи LC VPN")
    }
}

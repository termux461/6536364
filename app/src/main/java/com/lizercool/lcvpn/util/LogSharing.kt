package com.lizercool.lcvpn.util

import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import java.io.File

object LogSharing {

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

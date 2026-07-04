package com.lizercool.lcvpn.work

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.VpnService
import com.lizercool.lcvpn.util.Prefs
import com.lizercool.lcvpn.vpn.LcVpnService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class BootConnectReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return

        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val connectOnLaunch = Prefs(context).connectOnLaunch.first()
                // VpnService.prepare() must have already been granted in a previous foreground
                // session; if it returns non-null here we can't silently show a system prompt
                // from a receiver, so we simply skip auto-connect for that case.
                if (connectOnLaunch && VpnService.prepare(context) == null) {
                    val serviceIntent = Intent(context, LcVpnService::class.java)
                        .setAction(LcVpnService.ACTION_CONNECT)
                    context.startForegroundService(serviceIntent)
                }
            } finally {
                pendingResult.finish()
            }
        }
    }
}

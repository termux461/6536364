package com.lizercool.lcvpn.util

import android.os.Debug

/**
 * Reports the app process's real memory footprint. Uses PSS (proportional set size), which
 * includes the native Go/Xray-core + hev-socks5-tunnel allocations - not just the JVM heap - so
 * it matches what the OS actually attributes to us.
 */
object MemoryMonitor {

    /** Current process memory in bytes (PSS). Cheap enough to poll once a second. */
    fun usedBytes(): Long = Debug.getPss() * 1024L

    fun usedMb(): Int = (usedBytes() / (1024 * 1024)).toInt()
}

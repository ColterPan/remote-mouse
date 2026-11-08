package io.github.colterpan.remotemouse

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build

/**
 * LowLatencyWifi — keeps the phone's Wi-Fi radio fully awake while you use the remote.
 *
 * To save battery, phones put Wi-Fi into a power-saving mode between packets
 * and then send queued packets in bursts. For a mouse that means jerky,
 * "laggy" movement. A Wi-Fi lock tells Android not to do that:
 *  - Android 10+: WIFI_MODE_FULL_LOW_LATENCY (designed for exactly this:
 *    games and remote controls; only active while the app is on screen)
 *  - older:       WIFI_MODE_FULL_HIGH_PERF
 *
 * Held only between onResume and onPause, so there's no battery cost when the
 * app is in the background.
 */
class LowLatencyWifi(context: Context) {
    private val lock: WifiManager.WifiLock = run {
        val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            WifiManager.WIFI_MODE_FULL_LOW_LATENCY
        } else {
            @Suppress("DEPRECATION")
            WifiManager.WIFI_MODE_FULL_HIGH_PERF
        }
        wifi.createWifiLock(mode, "RemoteMouse:remote").apply { setReferenceCounted(false) }
    }

    fun acquire() {
        if (!lock.isHeld) lock.acquire()
    }

    fun release() {
        if (lock.isHeld) lock.release()
    }
}

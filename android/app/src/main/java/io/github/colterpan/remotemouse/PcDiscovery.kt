package io.github.colterpan.remotemouse

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import android.util.Log

/**
 * PcDiscovery — finds a paired PC on the Wi-Fi when its IP address changed.
 *
 * The PC announces "_remotemouse._tcp" via mDNS (see pc/remote_mouse/discovery.py)
 * with its certificate fingerprint in the announcement. We browse for that
 * service and pick the PC whose fingerprint matches the one we paired with.
 * (The fingerprint is public; the connection itself is still verified by
 * certificate pinning, so a fake announcement gets nowhere.)
 *
 * Android only resolves one service at a time on older versions, so found
 * services are resolved one after another from a queue.
 */
class PcDiscovery(context: Context) {
    private val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val main = Handler(Looper.getMainLooper())

    /** Look for the PC with `fingerprint`; calls back once with its address, or null. */
    fun find(fingerprint: String, timeoutMs: Long, callback: (host: String, port: Int) -> Unit, notFound: () -> Unit) {
        Search(fingerprint, timeoutMs, callback, notFound).start()
    }

    private inner class Search(
        private val fingerprint: String,
        private val timeoutMs: Long,
        private val onFound: (String, Int) -> Unit,
        private val onNotFound: () -> Unit,
    ) : NsdManager.DiscoveryListener {
        private val queue = ArrayDeque<NsdServiceInfo>()
        private var resolving = false
        private var done = false
        private val multicastLock = wifi.createMulticastLock("RemoteMouseDiscovery").apply {
            setReferenceCounted(false)
        }

        fun start() {
            multicastLock.acquire()
            runCatching {
                nsd.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, this)
            }.onFailure { finish(null) }
            main.postDelayed({ finish(null) }, timeoutMs)
        }

        @Synchronized
        private fun finish(result: Pair<String, Int>?) {
            if (done) return
            done = true
            runCatching { nsd.stopServiceDiscovery(this) }
            if (multicastLock.isHeld) multicastLock.release()
            main.post { if (result != null) onFound(result.first, result.second) else onNotFound() }
        }

        override fun onServiceFound(info: NsdServiceInfo) {
            synchronized(this) {
                queue.addLast(info)
                if (!resolving) resolveNext()
            }
        }

        private fun resolveNext() {
            if (done) return // already found (or timed out): stop resolving
            val next = queue.removeFirstOrNull() ?: run { resolving = false; return }
            resolving = true
            @Suppress("DEPRECATION") // resolveService is fine on all supported versions
            nsd.resolveService(next, object : NsdManager.ResolveListener {
                override fun onServiceResolved(info: NsdServiceInfo) {
                    val fp = info.attributes["fp"]?.toString(Charsets.UTF_8)
                    @Suppress("DEPRECATION")
                    val host = info.host?.hostAddress
                    if (fp.equals(fingerprint, ignoreCase = true) && PairingLink.isLocalAddress(host)) {
                        finish(host!! to info.port)
                    } else {
                        synchronized(this@Search) { resolveNext() }
                    }
                }

                override fun onResolveFailed(info: NsdServiceInfo, errorCode: Int) {
                    synchronized(this@Search) { resolveNext() }
                }
            })
        }

        override fun onDiscoveryStarted(serviceType: String) = Unit
        override fun onDiscoveryStopped(serviceType: String) = Unit
        override fun onServiceLost(info: NsdServiceInfo) = Unit
        override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.w(TAG, "Discovery failed to start: $errorCode")
            finish(null)
        }
        override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) = Unit
    }

    private companion object {
        const val SERVICE_TYPE = "_remotemouse._tcp"
        const val TAG = "PcDiscovery"
    }
}

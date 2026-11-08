package io.github.colterpan.remotemouse

import org.json.JSONObject

/**
 * RemoteSession — "connect me to my PC, wherever it is now".
 *
 * One connection attempt:
 *   1. try the PC's last known address;
 *   2. if that address doesn't answer (the router gave the PC a new IP), search
 *      the network for the PC by its certificate fingerprint (PcDiscovery),
 *      save the new address, and connect there;
 *   3. if the PC isn't found, report "closed" — the web UI retries with
 *      increasing pauses (connection.js), so it reconnects as soon as the PC
 *      is back.
 *
 * Every event carries the connection id (`cid`) the web UI asked for, so a
 * late event from an old attempt can never confuse a newer one.
 */
class RemoteSession(
    private val store: PcStore,
    private val discovery: PcDiscovery,
    private val listener: Listener,
) {
    interface Listener {
        fun onStatus(cid: Int, state: String, pcName: String)
        fun onOpen(cid: Int, helloJson: String)
        fun onMessage(cid: Int, text: String)
        fun onClosed(cid: Int, code: Int)
        fun onPcsChanged()
    }

    private var current: PinnedSocket? = null

    /**
     * Native attempt counter. The page's `cid` restarts at 1 when the page
     * reloads, so it can't tell an old attempt from a new one by itself; this
     * counter only ever increases. Events are delivered only for the current
     * generation, and carry the page's cid back to it.
     */
    private var generation = 0L

    /** The PC we're connected or connecting to (null when idle). */
    @Volatile var currentPcId: String? = null
        private set

    @Synchronized
    fun connect(pcId: String, cid: Int) {
        disconnect()
        val gen = generation
        val pc = store.get(pcId) ?: return listener.onClosed(cid, CLOSE_UNKNOWN_PC)
        currentPcId = pc.id
        store.markUsed(pc.id)
        attempt(pc, cid, gen, allowDiscovery = true)
    }

    private fun attempt(pc: SavedPc, cid: Int, gen: Long, allowDiscovery: Boolean) {
        listener.onStatus(cid, "connecting", pc.name)
        val socket = PinnedSocket(pc, object : PinnedSocket.Events {
            override fun onHello(helloJson: String) {
                if (!isCurrent(gen)) return
                // Only now — after the pinned TLS check and the PC accepting our
                // token — do we trust this address enough to save it.
                remember(pc, helloJson)
                listener.onOpen(cid, helloJson)
            }

            override fun onMessage(text: String) {
                if (isCurrent(gen)) listener.onMessage(cid, text)
            }

            override fun onClosed(code: Int) {
                if (isCurrent(gen)) listener.onClosed(cid, code)
            }

            override fun onUnreachable() {
                if (!isCurrent(gen)) return
                if (allowDiscovery) rediscover(pc, cid, gen) else listener.onClosed(cid, ABNORMAL)
            }
        })
        synchronized(this) {
            if (!isCurrent(gen)) return
            current = socket
        }
        socket.open()
    }

    private fun rediscover(pc: SavedPc, cid: Int, gen: Long) {
        listener.onStatus(cid, "searching", pc.name)
        discovery.find(
            pc.fingerprint,
            DISCOVERY_TIMEOUT_MS,
            callback = { host, port ->
                // Not saved yet: an announcement can be faked. remember() saves
                // the new address only once the PC has proven who it is.
                if (isCurrent(gen)) attempt(pc.copy(host = host, port = port), cid, gen, allowDiscovery = false)
            },
            notFound = { if (isCurrent(gen)) listener.onClosed(cid, ABNORMAL) },
        )
    }

    /** Save the verified address (it may have changed) and the PC's name. */
    private fun remember(pc: SavedPc, helloJson: String) {
        val stored = store.get(pc.id) ?: return
        val name = runCatching { JSONObject(helloJson).optString("name") }.getOrDefault("")
        val updated = stored.copy(
            host = pc.host,
            port = pc.port,
            name = name.takeIf { it.isNotBlank() }?.take(MAX_NAME) ?: stored.name,
        )
        if (updated != stored) {
            store.save(updated)
            listener.onPcsChanged()
        }
    }

    fun send(text: String): Boolean = current?.send(text) == true

    @Synchronized
    fun disconnect() {
        generation += 1 // invalidates every callback of the previous attempt
        currentPcId = null
        current?.close()
        current = null
    }

    @Synchronized
    private fun isCurrent(gen: Long) = gen == generation

    companion object {
        const val ABNORMAL = 1006
        const val CLOSE_UNKNOWN_PC = 4404
        private const val DISCOVERY_TIMEOUT_MS = 5000L
        private const val MAX_NAME = 64
    }
}

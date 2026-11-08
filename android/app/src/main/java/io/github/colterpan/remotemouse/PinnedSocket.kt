package io.github.colterpan.remotemouse

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.net.InetAddress
import java.net.Socket
import java.util.concurrent.TimeUnit
import javax.net.SocketFactory
import javax.net.ssl.SSLContext

/**
 * PinnedSocket — one encrypted WebSocket connection to a paired PC.
 *
 *  1. TLS with the PC's certificate PINNED (FingerprintTrustManager).
 *  2. TCP_NODELAY: send each tiny mouse message immediately instead of letting
 *     the OS bundle them (Nagle's algorithm adds up to ~40 ms of lag).
 *  3. Immediately sends {"t":"auth", token} — the web UI never sees the token.
 *  4. Reports: connected (after the PC's "hello"), each message, closed/failed.
 */
class PinnedSocket(
    private val pc: SavedPc,
    private val events: Events,
) {
    interface Events {
        fun onHello(helloJson: String)
        fun onMessage(text: String)
        fun onClosed(code: Int)
        /** Could not connect at all (wrong address, PC off…): try discovery. */
        fun onUnreachable()
    }

    @Volatile private var socket: WebSocket? = null
    @Volatile private var greeted = false
    @Volatile private var finished = false

    fun open() {
        val request = Request.Builder().url("wss://${hostForUrl(pc.host)}:${pc.port}/ws").build()
        socket = clientFor(pc.fingerprint).newWebSocket(request, Listener())
    }

    fun send(text: String): Boolean = greeted && socket?.send(text) == true

    fun close() {
        finished = true
        val s = socket ?: return
        // Still connecting? Cancel outright instead of finishing TLS first.
        if (greeted) s.close(NORMAL_CLOSURE, null) else s.cancel()
        socket = null
    }

    private inner class Listener : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            val auth = JSONObject().put("t", "auth").put("token", pc.token).put("v", PROTOCOL_VERSION)
            webSocket.send(auth.toString())
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            if (!greeted) {
                val type = runCatching { JSONObject(text).optString("t") }.getOrDefault("")
                if (type == "hello") {
                    greeted = true
                    events.onHello(text)
                    return
                }
            }
            events.onMessage(text)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(code, null)
            finish(code)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = finish(code)

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (finished) return
            finished = true
            if (greeted) events.onClosed(ABNORMAL_CLOSURE) else events.onUnreachable()
        }

        private fun finish(code: Int) {
            if (finished) return
            finished = true
            events.onClosed(code)
        }
    }

    companion object {
        const val PROTOCOL_VERSION = 1
        const val NORMAL_CLOSURE = 1000
        const val ABNORMAL_CLOSURE = 1006
        private const val CONNECT_TIMEOUT_SECONDS = 4L

        private fun hostForUrl(host: String) = if (host.contains(':')) "[$host]" else host

        /** OkHttp client that trusts exactly one certificate fingerprint. */
        fun clientFor(fingerprint: String): OkHttpClient {
            val trustManager = FingerprintTrustManager(fingerprint)
            val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf(trustManager), null) }
            return OkHttpClient.Builder()
                .sslSocketFactory(ssl.socketFactory, trustManager)
                // The pinned fingerprint already proves identity; the PC's IP
                // can change, so don't also require the name in the cert to match.
                .hostnameVerifier { _, _ -> true }
                .socketFactory(NoDelaySocketFactory)
                .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.MILLISECONDS) // the web UI pings; no idle timeout
                .build()
        }
    }
}

/** Creates sockets with TCP_NODELAY on, for the lowest possible latency. */
private object NoDelaySocketFactory : SocketFactory() {
    private val base = getDefault()
    private fun Socket.tuned() = apply { tcpNoDelay = true }

    override fun createSocket(): Socket = base.createSocket().tuned()
    override fun createSocket(host: String?, port: Int): Socket = base.createSocket(host, port).tuned()
    override fun createSocket(host: String?, port: Int, localHost: InetAddress?, localPort: Int): Socket =
        base.createSocket(host, port, localHost, localPort).tuned()
    override fun createSocket(host: InetAddress?, port: Int): Socket = base.createSocket(host, port).tuned()
    override fun createSocket(address: InetAddress?, port: Int, localAddress: InetAddress?, localPort: Int): Socket =
        base.createSocket(address, port, localAddress, localPort).tuned()
}

package io.github.colterpan.remotemouse

import android.os.Handler
import android.os.Looper
import androidx.webkit.JavaScriptReplyProxy
import org.json.JSONArray
import org.json.JSONObject

/**
 * NativeBridge — the ONLY channel between the web UI and the native app.
 *
 * Security: it's registered with WebViewCompat.addWebMessageListener for the
 * bundled page's origin only (https://appassets.androidplatform.net), so no
 * other page could ever talk to it. Messages are small JSON objects:
 *
 *   web → native   {"op":"init"} {"op":"connect","id","cid"} {"op":"send","msg"}
 *                  {"op":"disconnect"} {"op":"scan"} {"op":"forget","id"}
 *                  {"op":"keepAwake","on"}
 *   native → web   {"ev":"pcs","pcs":[…],"lastId"} {"ev":"status","cid","state","name"}
 *                  {"ev":"open","cid","data"} {"ev":"message","cid","data"}
 *                  {"ev":"close","cid","code"} {"ev":"paired","id"} {"ev":"scanError"}
 *
 * The web UI never receives pairing tokens (SavedPc.toPublicJson).
 */
class NativeBridge(
    private val store: PcStore,
    private val actions: Actions,
) : RemoteSession.Listener {

    interface Actions {
        fun startScan()
        fun setKeepAwake(on: Boolean)
    }

    lateinit var session: RemoteSession
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var reply: JavaScriptReplyProxy? = null

    /** Called (on the main thread) for every message from the page. */
    fun onPageMessage(data: String?, replyProxy: JavaScriptReplyProxy) {
        reply = replyProxy
        val msg = runCatching { JSONObject(data ?: return) }.getOrNull() ?: return
        when (msg.optString("op")) {
            "init" -> sendPcs()
            "send" -> session.send(msg.optString("msg"))
            "connect" -> session.connect(msg.optString("id"), msg.optInt("cid"))
            "disconnect" -> session.disconnect()
            "scan" -> actions.startScan()
            "forget" -> {
                val id = msg.optString("id")
                // Only drop the live connection if it's the PC being forgotten.
                if (session.currentPcId == id) session.disconnect()
                store.remove(id)
                sendPcs()
            }
            "keepAwake" -> actions.setKeepAwake(msg.optBoolean("on", true))
        }
    }

    /** A QR code was scanned (or a debug pairing link was injected). */
    fun onScanned(text: String?) {
        if (text == null) return // scanner cancelled: not an error
        val link = PairingLink.parse(text)
        if (link == null) {
            emit(JSONObject().put("ev", "scanError"))
            return
        }
        val pc = SavedPc.fromLink(link)
        val existing = store.get(pc.id)
        store.save(if (existing != null) existing.copy(host = pc.host, port = pc.port, token = pc.token) else pc)
        sendPcs()
        emit(JSONObject().put("ev", "paired").put("id", pc.id))
    }

    fun sendPcs() {
        val list = JSONArray().apply { store.all().forEach { put(it.toPublicJson()) } }
        emit(JSONObject().put("ev", "pcs").put("pcs", list).put("lastId", store.lastId() ?: JSONObject.NULL))
    }

    // --- RemoteSession.Listener (called from network threads) --------------

    override fun onStatus(cid: Int, state: String, pcName: String) =
        emit(JSONObject().put("ev", "status").put("cid", cid).put("state", state).put("name", pcName))

    override fun onOpen(cid: Int, helloJson: String) =
        emit(JSONObject().put("ev", "open").put("cid", cid).put("data", helloJson))

    override fun onMessage(cid: Int, text: String) =
        emit(JSONObject().put("ev", "message").put("cid", cid).put("data", text))

    override fun onClosed(cid: Int, code: Int) =
        emit(JSONObject().put("ev", "close").put("cid", cid).put("code", code))

    override fun onPcsChanged() = sendPcs()

    private fun emit(event: JSONObject) {
        val text = event.toString()
        // JavaScriptReplyProxy must be used on the main thread.
        main.post { reply?.postMessage(text) }
    }
}

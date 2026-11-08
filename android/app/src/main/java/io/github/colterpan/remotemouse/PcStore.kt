package io.github.colterpan.remotemouse

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * SavedPc — one PC this phone has been paired with.
 * `id` is the certificate fingerprint: it identifies the PC even when its
 * IP address changes.
 */
data class SavedPc(
    val id: String,
    val name: String,
    val host: String,
    val port: Int,
    val token: String,
) {
    val fingerprint: String get() = id

    /** What the web UI may see — deliberately WITHOUT the token. */
    fun toPublicJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("name", name)
        .put("host", host)
        .put("port", port)

    fun toJson(): JSONObject = toPublicJson().put("token", token)

    companion object {
        fun fromJson(obj: JSONObject): SavedPc? = runCatching {
            SavedPc(
                id = obj.getString("id"),
                name = obj.getString("name"),
                host = obj.getString("host"),
                port = obj.getInt("port"),
                token = obj.getString("token"),
            )
        }.getOrNull()

        fun fromLink(link: PairingLink): SavedPc =
            SavedPc(link.fingerprint, link.host, link.host, link.port, link.token)
    }
}

/** Pure encode/decode helpers (unit-tested without Android). */
object PcCodec {
    fun encode(pcs: List<SavedPc>): String =
        JSONArray().apply { pcs.forEach { put(it.toJson()) } }.toString()

    fun decode(text: String?): List<SavedPc> {
        if (text.isNullOrBlank()) return emptyList()
        val array = runCatching { JSONArray(text) }.getOrNull() ?: return emptyList()
        return (0 until array.length()).mapNotNull { i ->
            array.optJSONObject(i)?.let(SavedPc::fromJson)
        }
    }

    /** Insert or replace by id (re-pairing the same PC updates its token/address). */
    fun upsert(pcs: List<SavedPc>, pc: SavedPc): List<SavedPc> =
        pcs.filterNot { it.id == pc.id } + pc
}

/**
 * PcStore — saved PCs in the app's private storage.
 *
 * SharedPreferences live in /data/data/<app>/ which no other app can read.
 * Backups are disabled in the manifest, so tokens never leave the phone.
 */
class PcStore(context: Context) {
    private val prefs = context.getSharedPreferences("pcs", Context.MODE_PRIVATE)

    fun all(): List<SavedPc> = PcCodec.decode(prefs.getString(KEY_PCS, null))

    fun get(id: String): SavedPc? = all().firstOrNull { it.id == id }

    fun lastId(): String? = prefs.getString(KEY_LAST, null)?.takeIf { id -> get(id) != null }

    fun save(pc: SavedPc) {
        prefs.edit()
            .putString(KEY_PCS, PcCodec.encode(PcCodec.upsert(all(), pc)))
            .putString(KEY_LAST, pc.id)
            .apply()
    }

    fun markUsed(id: String) {
        prefs.edit().putString(KEY_LAST, id).apply()
    }

    fun remove(id: String) {
        val remaining = all().filterNot { it.id == id }
        val editor = prefs.edit().putString(KEY_PCS, PcCodec.encode(remaining))
        if (prefs.getString(KEY_LAST, null) == id) editor.remove(KEY_LAST)
        editor.apply()
    }

    private companion object {
        const val KEY_PCS = "pcs"
        const val KEY_LAST = "last"
    }
}

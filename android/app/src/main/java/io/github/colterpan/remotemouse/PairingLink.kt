package io.github.colterpan.remotemouse

import java.net.URI
import java.net.URLDecoder

/**
 * PairingLink — the information inside the PC's QR code.
 *
 * The QR code holds a link like:
 *     https://192.168.1.20:8765/#t=<token>&fp=<certificate fingerprint>
 *
 *  - host + port: where the PC is right now
 *  - t (token):   the secret that proves this phone was paired
 *  - fp:          SHA-256 of the PC's certificate; we only ever talk to a PC
 *                 presenting exactly this certificate (see FingerprintTrustManager)
 *
 * `parse` is strict: anything that isn't a well-formed Remote Mouse link is
 * rejected (returns null), so scanning a random QR code can't do anything.
 * Uses java.net.URI (not android.net.Uri) so it runs in plain JVM unit tests.
 */
data class PairingLink(
    val host: String,
    val port: Int,
    val token: String,
    val fingerprint: String,
) {
    companion object {
        private val TOKEN = Regex("^[A-Za-z0-9_-]{22,128}$")
        private val FINGERPRINT = Regex("^[0-9a-f]{64}$")
        private val IPV4 = Regex("^(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})$")

        /**
         * True only for private/link-local IPv4 addresses (10.x, 172.16–31.x,
         * 192.168.x, 169.254.x) — where a Remote Mouse PC can actually be.
         * A QR code pointing anywhere else (an internet server) is refused,
         * so a malicious QR code can't make the app send your typing away.
         */
        fun isLocalAddress(host: String?): Boolean {
            val parts = IPV4.matchEntire(host ?: return false)?.groupValues?.drop(1)
                ?.map { it.toInt() } ?: return false
            if (parts.any { it > 255 }) return false
            val (a, b) = parts
            return a == 10 || (a == 172 && b in 16..31) || (a == 192 && b == 168) || (a == 169 && b == 254)
        }

        fun parse(text: String?): PairingLink? {
            if (text == null || text.length > 1024) return null
            val uri = runCatching { URI(text.trim()) }.getOrNull() ?: return null
            if (!uri.scheme.equals("https", ignoreCase = true)) return null
            val host = uri.host ?: return null
            if (!isLocalAddress(host)) return null
            val port = uri.port
            if (port !in 1..65535) return null

            val params = parseFragment(uri.rawFragment ?: return null)
            val token = params["t"] ?: return null
            val fingerprint = params["fp"]?.lowercase() ?: return null
            if (!TOKEN.matches(token) || !FINGERPRINT.matches(fingerprint)) return null
            return PairingLink(host, port, token, fingerprint)
        }

        private fun parseFragment(fragment: String): Map<String, String> =
            fragment.split("&")
                .mapNotNull { part ->
                    val eq = part.indexOf('=')
                    if (eq <= 0) {
                        null
                    } else {
                        val key = URLDecoder.decode(part.substring(0, eq), "UTF-8")
                        val value = URLDecoder.decode(part.substring(eq + 1), "UTF-8")
                        key to value
                    }
                }
                .toMap()
    }
}

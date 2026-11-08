package io.github.colterpan.remotemouse

import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.X509TrustManager

/**
 * FingerprintTrustManager — "certificate pinning" for the PC connection.
 *
 * Your PC uses its own (self-signed) certificate. A browser can't verify it,
 * which is why Chrome shows a warning. The app does better: during pairing it
 * learned the certificate's exact SHA-256 fingerprint from the QR code, and
 * from then on it accepts ONLY that certificate.
 *
 * Result: no warnings, and an impostor on the network (even one that copies
 * the PC's name and address) cannot get the app to connect, because it can't
 * present the PC's certificate without the PC's private key.
 *
 * The comparison uses MessageDigest.isEqual, which runs in constant time.
 */
class FingerprintTrustManager(expectedFingerprintHex: String) : X509TrustManager {

    private val expected: ByteArray = hexToBytes(expectedFingerprintHex)

    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        val leaf = chain?.firstOrNull() ?: throw CertificateException("No certificate presented")
        val actual = MessageDigest.getInstance("SHA-256").digest(leaf.encoded)
        if (!MessageDigest.isEqual(actual, expected)) {
            throw CertificateException("Certificate does not match the paired PC")
        }
    }

    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        throw CertificateException("Client certificates are not used")
    }

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()

    companion object {
        fun hexToBytes(hex: String): ByteArray {
            require(hex.length == 64 && hex.all { it in "0123456789abcdefABCDEF" }) {
                "Fingerprint must be 64 hex characters"
            }
            return ByteArray(32) { i -> hex.substring(i * 2, i * 2 + 2).toInt(16).toByte() }
        }
    }
}

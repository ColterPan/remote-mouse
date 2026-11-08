package io.github.colterpan.remotemouse

import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import java.security.MessageDigest
import java.security.cert.CertificateException
import javax.net.ssl.SSLException

/**
 * Proves certificate pinning works over a REAL TLS connection:
 * the app connects to the PC whose certificate it paired with, and refuses an
 * impostor — even one listening on the same address.
 */
class PinningTest {
    private val pcCert = HeldCertificate.Builder().commonName("Remote Mouse").addSubjectAlternativeName("localhost").build()
    private val impostorCert = HeldCertificate.Builder().commonName("Remote Mouse").addSubjectAlternativeName("localhost").build()
    private lateinit var server: MockWebServer

    private fun fingerprintOf(cert: HeldCertificate): String =
        MessageDigest.getInstance("SHA-256").digest(cert.certificate.encoded)
            .joinToString("") { "%02x".format(it) }

    private fun serve(cert: HeldCertificate) {
        server = MockWebServer()
        val certs = HandshakeCertificates.Builder().heldCertificate(cert).build()
        server.useHttps(certs.sslSocketFactory(), false)
        server.enqueue(MockResponse().setBody("hello"))
        server.start()
    }

    @After
    fun tearDown() = server.shutdown()

    @Test
    fun `connects to the paired PC`() {
        serve(pcCert)
        val client = PinnedSocket.clientFor(fingerprintOf(pcCert))
        client.newCall(Request.Builder().url(server.url("/")).build()).execute().use {
            assertEquals("hello", it.body?.string())
        }
    }

    @Test
    fun `refuses an impostor with a different certificate`() {
        serve(impostorCert)
        val client = PinnedSocket.clientFor(fingerprintOf(pcCert))
        assertThrows(SSLException::class.java) {
            client.newCall(Request.Builder().url(server.url("/")).build()).execute()
        }
    }
}

class FingerprintTrustManagerTest {
    @Test
    fun `rejects an empty chain`() {
        val tm = FingerprintTrustManager("00".repeat(32))
        assertThrows(CertificateException::class.java) { tm.checkServerTrusted(emptyArray(), "RSA") }
    }

    @Test
    fun `rejects malformed fingerprints`() {
        assertThrows(IllegalArgumentException::class.java) { FingerprintTrustManager("nothex") }
    }

    @Test
    fun `client certificates are never accepted`() {
        val tm = FingerprintTrustManager("00".repeat(32))
        assertThrows(CertificateException::class.java) { tm.checkClientTrusted(emptyArray(), "RSA") }
    }
}

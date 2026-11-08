package io.github.colterpan.remotemouse

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PairingLinkTest {
    private val token = "AbCdEfGhIjKlMnOpQrStUv"
    private val fp = "ab".repeat(32)

    @Test
    fun `parses a real pairing link`() {
        val link = PairingLink.parse("https://192.168.1.20:8765/#t=$token&fp=$fp")
        assertEquals(PairingLink("192.168.1.20", 8765, token, fp), link)
    }

    @Test
    fun `fingerprint is normalised to lowercase`() {
        val link = PairingLink.parse("https://10.0.0.2:9000/#t=$token&fp=${fp.uppercase()}")
        assertEquals(fp, link?.fingerprint)
    }

    @Test
    fun `accepts every private range`() {
        listOf("10.1.2.3", "172.20.0.9", "169.254.10.10").forEach {
            assertEquals(it, PairingLink.parse("https://$it:8765/#t=$token&fp=$fp")?.host)
        }
    }

    @Test
    fun `parameter order does not matter`() {
        val link = PairingLink.parse("https://10.0.0.2:9000/#fp=$fp&t=$token")
        assertEquals(token, link?.token)
    }

    @Test
    fun `rejects anything that is not a valid Remote Mouse link`() {
        val bad = listOf(
            null,
            "",
            "hello world",
            "http://192.168.1.20:8765/#t=$token&fp=$fp", // not https
            "https://192.168.1.20/#t=$token&fp=$fp", // no port
            "https://192.168.1.20:8765/", // no fragment
            "https://192.168.1.20:8765/#t=short&fp=$fp", // token too short
            "https://192.168.1.20:8765/#t=$token&fp=1234", // bad fingerprint
            "https://192.168.1.20:8765/#t=$token", // missing fingerprint
            "https://192.168.1.20:8765/#t=<script>xxxxxxxxxxxxxxxxx&fp=$fp",
            "javascript:alert(1)",
            "https://evil.example:8765/#t=$token&fp=$fp".padEnd(2000, 'x'),
            // Not on the local network: refused so a planted QR can't send typing away.
            "https://evil.example:8765/#t=$token&fp=$fp",
            "https://8.8.8.8:8765/#t=$token&fp=$fp",
            "https://172.32.0.1:8765/#t=$token&fp=$fp",
            "https://192.168.1.300:8765/#t=$token&fp=$fp",
        )
        bad.forEach { assertNull("should reject: $it", PairingLink.parse(it)) }
    }

    @Test
    fun `only local network addresses count as local`() {
        listOf("10.0.0.1", "172.16.5.5", "172.31.255.255", "192.168.50.20", "169.254.1.1")
            .forEach { assertEquals(it, true, PairingLink.isLocalAddress(it)) }
        listOf("8.8.8.8", "172.15.0.1", "172.32.0.1", "192.169.0.1", "localhost", "evil.example", "", null, "1.2.3")
            .forEach { assertEquals("$it", false, PairingLink.isLocalAddress(it)) }
    }
}

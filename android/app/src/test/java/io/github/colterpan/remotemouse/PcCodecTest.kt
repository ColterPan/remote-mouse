package io.github.colterpan.remotemouse

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PcCodecTest {
    private val pc = SavedPc("ab".repeat(32), "MY-PC", "192.168.1.20", 8765, "AbCdEfGhIjKlMnOpQrStUv")

    @Test
    fun `round trip`() {
        assertEquals(listOf(pc), PcCodec.decode(PcCodec.encode(listOf(pc))))
    }

    @Test
    fun `corrupt storage gives an empty list instead of crashing`() {
        assertEquals(emptyList<SavedPc>(), PcCodec.decode("{not json"))
        assertEquals(emptyList<SavedPc>(), PcCodec.decode(null))
        assertEquals(emptyList<SavedPc>(), PcCodec.decode("[{\"id\":1}]"))
    }

    @Test
    fun `upsert replaces the same PC instead of duplicating it`() {
        val moved = pc.copy(host = "192.168.1.99")
        assertEquals(listOf(moved), PcCodec.upsert(listOf(pc), moved))
    }

    @Test
    fun `the web UI never receives the token`() {
        val json = pc.toPublicJson()
        assertFalse(json.has("token"))
        assertTrue(pc.toJson().has("token"))
    }

    @Test
    fun `a pairing link becomes a saved PC keyed by fingerprint`() {
        val link = PairingLink("10.0.0.5", 8765, "AbCdEfGhIjKlMnOpQrStUv", "cd".repeat(32))
        val saved = SavedPc.fromLink(link)
        assertEquals("cd".repeat(32), saved.id)
        assertEquals("10.0.0.5", saved.host)
    }
}

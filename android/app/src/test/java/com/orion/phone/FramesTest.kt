package com.orion.phone

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class FramesTest {
    @Test
    fun chatFrameCarriesTheId() {
        val raw = Frames.chat("7", "what time is it")
        val parsed = Frames.parse(raw)
        assertEquals("chat", parsed.getString("type"))
        assertEquals("7", parsed.getString("id"))
    }

    @Test
    fun pairLinkKeepsTheToken() {
        val pairing = Frames.pairFromLink("orion://pair?token=abc123&account=acct&relay=wss://relay.orion.test/ws")
        assertNotNull(pairing)
        assertEquals("abc123", pairing!!.token)
        assertEquals("acct", pairing.account)
    }

    @Test
    fun pairLinkFromThePcIsUrlEncoded() {
        // Exactly what service/api.py phone_pair_link() produces.
        val pairing = Frames.pairFromLink("orion://pair?relay=wss%3A%2F%2Frelay.test%2Fws&account=acct_1&token=tok")
        assertEquals("wss://relay.test/ws", pairing!!.relay)
        assertEquals("acct_1", pairing.account)
    }

    @Test
    fun incompleteOrForeignLinksAreRejected() {
        assertNull(Frames.pairFromLink("http://127.0.0.1:8765/#token=abc"))
        assertNull(Frames.pairFromLink("orion://pair?token=abc"))
        assertNull(Frames.pairFromLink("orion://pair?token=abc&account=a&relay=https://evil.test"))
    }

    @Test
    fun shutdownCarriesThePin() {
        val parsed = Frames.parse(Frames.command("9", "shutdown", mapOf("pin" to "1234")))
        assertEquals("1234", parsed.getJSONObject("arguments").getString("pin"))
    }
}

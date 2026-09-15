package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class PairingTest {
    private fun invitation() = JSONObject().put("type", "suzent.mobile").put("pairing_protocol", 1)
        .put("origin", "https://desktop.example").put("pairing_id", "a".repeat(32))
        .put("invitation", "b".repeat(43)).put("expires_at", 2000)

    @Test fun validatesOriginProtocolAndExpiryBeforeConnection() {
        assertEquals("https://desktop.example", PairingInvitation.parse(invitation().toString(), now = 1000.0).origin)
        listOf("type" to "other", "pairing_protocol" to 1.5, "pairing_protocol" to "1", "expires_at" to 999,
            "pairing_id" to "../admin", "origin" to "https://user:secret@desktop.example",
            "origin" to "http://desktop.example").forEach { (key, value) ->
            assertTrue(runCatching { PairingInvitation.parse(invitation().put(key, value).toString(), now = 1000.0) }.isFailure)
        }
        assertEquals("http://desktop.example", PairingInvitation.parse(invitation().put("origin", "http://desktop.example").toString(),
            allowHttp = true, now = 1000.0).origin)
    }

    @Test fun rejectsUnsupportedCapabilities() {
        val data = JSONObject().put("client_protocol", 1).put("pairing_protocol", 1).put("stream_protocols", JSONArray().put(1))
        validateMobileCapabilities(data, pairing = true)
        assertTrue(runCatching { validateMobileCapabilities(data.put("stream_protocols", JSONArray().put(2)), pairing = true) }.isFailure)
    }

    @Test fun validatesAllCandidatesAndKeepsHttpsForRelease() {
        val value = invitation().put("origin", "http://192.168.1.2")
            .put("origins", JSONArray().put("http://192.168.1.2").put("https://desktop.example"))
        assertEquals(listOf("https://desktop.example"), PairingInvitation.parse(value.toString(), now = 1000.0).origins)
        assertEquals(2, PairingInvitation.parse(value.toString(), allowHttp = true, now = 1000.0).origins.size)
        value.put("origins", JSONArray().put("https://user:secret@other.example"))
        assertTrue(runCatching { PairingInvitation.parse(value.toString(), allowHttp = true, now = 1000.0) }.isFailure)
    }

    @Test fun resolvesReachableCandidateWithoutClaimingOrRetryingMutation() = kotlinx.coroutines.runBlocking {
        val value = invitation().put("expires_at", System.currentTimeMillis() / 1000.0 + 300)
            .put("origins", JSONArray().put("https://desktop.example").put("https://tailnet.example"))
        val calls = mutableListOf<String>()
        val selected = resolvePairingInvitation(PairingInvitation.parse(value.toString())) { origin ->
            calls.add(origin)
            if (origin == "https://desktop.example") throw java.io.IOException()
        }
        assertEquals("https://tailnet.example", selected.origin)
        assertEquals(listOf("https://desktop.example", "https://tailnet.example"), calls)
        val failure = runCatching {
            resolvePairingInvitation(selected) { throw java.io.IOException() }
        }.exceptionOrNull() as PairingFailure
        assertEquals(PairingFailure.Reason.UNREACHABLE, failure.reason)
    }
}

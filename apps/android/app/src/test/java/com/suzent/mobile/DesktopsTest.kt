package com.suzent.mobile

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class DesktopsTest {
    private fun connection(origin: String, origins: List<String> = emptyList(), tls: DeviceTrust? = null) =
        Connection(origin, "token-$origin", clientProtocol = 1, origins = origins, tls = tls)

    private fun invitation(origin: String, origins: List<String> = listOf(origin), tls: DeviceTrust? = null) =
        PairingInvitation(origin, "a".repeat(32), "b".repeat(43), 2000.0, origins, tls = tls)

    private fun trust(fingerprint: String) = DeviceTrust(1, "", fingerprint)

    @Test fun legacySingleConnectionBecomesOneActiveDesktop() {
        val legacy = connection("https://desk.example:25314/", listOf("https://10.0.0.2:25314/")).json()
        val desktops = SavedDesktops.parse(legacy)
        assertEquals(1, desktops.desktops.size)
        assertEquals(desktops.desktops[0].id, desktops.activeId)
        assertEquals("desk.example", desktops.active?.name)
        assertEquals(parseConnection(legacy), desktops.active?.connection)
    }

    @Test fun roundTripsThroughJson() {
        val first = SavedDesktop.create("Home", connection("https://home.example/"))
        val second = SavedDesktop.create("Work", connection("https://work.example/", listOf("https://10.0.0.3/")))
        val saved = SavedDesktops(second.id, listOf(first, second))
        assertEquals(saved, SavedDesktops.parse(JSONObject(saved.json().toString())))
    }

    @Test fun unknownActiveIdFallsBackToFirstDesktop() {
        val desktop = SavedDesktop.create("Home", connection("https://home.example/"))
        val json = SavedDesktops("gone", listOf(desktop)).json()
        assertEquals(desktop.id, SavedDesktops.parse(json).activeId)
    }

    @Test fun matchesByDeviceTrustBeforeAddress() {
        val desktop = SavedDesktop.create("Home", connection("https://192.168.1.4:25314/", tls = trust("aa")))
        assertTrue(desktop.matches(invitation("https://10.0.0.9:25314", tls = trust("aa"))))
        // Same address, different identity: a different machine took over the IP.
        assertFalse(desktop.matches(invitation("https://192.168.1.4:25314", tls = trust("bb"))))
    }

    @Test fun matchesByAnySharedAddressWithoutDeviceTrust() {
        val desktop = SavedDesktop.create("Home", connection("http://192.168.1.4:25314/", listOf("http://home.tail.ts.net:25314/")))
        assertTrue(desktop.matches(invitation("http://10.0.0.9:25314", listOf("http://10.0.0.9:25314", "http://home.tail.ts.net:25314"))))
        assertFalse(desktop.matches(invitation("http://10.0.0.9:25314")))
    }

    @Test fun removingActiveHandsOverToFirstRemaining() {
        val a = SavedDesktop.create("A", connection("https://a.example/"))
        val b = SavedDesktop.create("B", connection("https://b.example/"))
        val c = SavedDesktop.create("C", connection("https://c.example/"))
        val saved = SavedDesktops(b.id, listOf(a, b, c))
        assertEquals(a.id, saved.removing(b.id).activeId)
        assertEquals(b.id, saved.removing(c.id).activeId)
        assertNull(SavedDesktops(a.id, listOf(a)).removing(a.id).activeId)
    }

    @Test fun upsertReplacesInPlaceOrAppends() {
        val a = SavedDesktop.create("A", connection("https://a.example/"))
        val b = SavedDesktop.create("B", connection("https://b.example/"))
        val saved = SavedDesktops(a.id, listOf(a, b))
        val renamed = saved.upserting(a.copy(name = "A2"))
        assertEquals(listOf("A2", "B"), renamed.desktops.map { it.name })
        val c = SavedDesktop.create("C", connection("https://c.example/"))
        assertEquals(listOf("A", "B", "C"), saved.upserting(c).desktops.map { it.name })
        assertEquals(a.id, saved.upserting(c).activeId)
    }

    @Test fun colourIsStablePerDesktop() {
        assertEquals(desktopColor("same-id"), desktopColor("same-id"))
    }
}

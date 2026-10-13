package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Test

class DeviceNameTest {
    @Test fun prefersUserAssignedNameOverModelCode() {
        assertEquals("My phone", pairingDeviceName("24031PN0DC") { "  My phone  " })
    }

    @Test fun fallsBackWhenNameIsMissingOrUnavailable() {
        assertEquals("24031PN0DC", pairingDeviceName("24031PN0DC") { null })
        assertEquals("Pixel 7 Pro", pairingDeviceName("Pixel 7 Pro") { "  " })
        assertEquals("Pixel 7 Pro", pairingDeviceName("Pixel 7 Pro") { throw SecurityException() })
        assertEquals("Android", pairingDeviceName(" ") { null })
    }

    @Test fun respectsPairingNameLimit() {
        assertEquals("a".repeat(100), pairingDeviceName("model") { "a".repeat(101) })
    }
}

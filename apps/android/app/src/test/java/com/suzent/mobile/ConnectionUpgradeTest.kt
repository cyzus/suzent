package com.suzent.mobile

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.*
import org.junit.Test

class ConnectionUpgradeTest {
    @Test fun waitsUntilIdle() = runBlocking {
        var idle = false
        val installed = CompletableDeferred<Int>()
        val upgrade = ConnectionUpgrade<Int>(this)
        upgrade.start({ 1 }, { true }, { idle }, { }, { installed.complete(it) }, { fail("Installed client must stay open") })
        delay(50)
        assertFalse(installed.isCompleted)
        idle = true
        assertEquals(1, withTimeout(2000) { installed.await() })
        upgrade.cancel()
    }

    @Test fun staleSessionCannotInstallPreparedClient() = runBlocking {
        var current = true
        val discarded = CompletableDeferred<Int>()
        val upgrade = ConnectionUpgrade<Int>(this)
        upgrade.start({ 1 }, { current }, { false }, { }, { fail("Stale session") }, { discarded.complete(it) })
        delay(50)
        current = false
        assertEquals(1, withTimeout(2000) { discarded.await() })
        upgrade.cancel()
    }

    @Test fun cancellationDiscardsWaitingClient() = runBlocking {
        val prepared = CompletableDeferred<Unit>()
        val discarded = CompletableDeferred<Int>()
        val upgrade = ConnectionUpgrade<Int>(this)
        upgrade.start({ prepared.complete(Unit); 1 }, { true }, { false }, { }, { fail("Cancelled upgrade") }, { discarded.complete(it) })
        prepared.await()
        upgrade.cancel()
        assertEquals(1, withTimeout(2000) { discarded.await() })
    }

    @Test fun failedProbeDoesNotReplaceCurrentClient() = runBlocking {
        val upgrade = ConnectionUpgrade<Int>(this)
        upgrade.start({ throw java.io.IOException() }, { true }, { true }, { }, { fail("Failed probe") }, { fail("No candidate") })
        delay(50)
        upgrade.cancel()
    }

    @Test fun replacementCancelsOldPreparedCandidate() = runBlocking {
        val prepared = CompletableDeferred<Unit>()
        val discarded = CompletableDeferred<Int>()
        val installed = CompletableDeferred<Int>()
        val upgrade = ConnectionUpgrade<Int>(this)
        upgrade.start({ prepared.complete(Unit); 1 }, { true }, { false }, { }, { fail("Old candidate") }, { discarded.complete(it) })
        prepared.await()
        upgrade.start({ 2 }, { true }, { true }, { }, { installed.complete(it) }, { fail("New candidate") })
        assertEquals(1, withTimeout(2000) { discarded.await() })
        assertEquals(2, withTimeout(2000) { installed.await() })
        upgrade.cancel()
    }

    @Test fun lostDirectRouteAfterIdleWaitKeepsRelay() = runBlocking {
        var idle = false
        var validated = false
        val discarded = CompletableDeferred<Int>()
        val upgrade = ConnectionUpgrade<Int>(this)
        upgrade.start({ 1 }, { true }, { idle }, {
            validated = true
            throw java.io.IOException("LAN no longer reachable")
        }, { fail("Unreachable direct client must not replace relay") }, { discarded.complete(it) })
        delay(50)
        assertFalse(validated)
        idle = true
        assertEquals(1, withTimeout(2000) { discarded.await() })
        assertTrue(validated)
        upgrade.cancel()
    }

    @Test fun sessionChangeDuringValidationDiscardsCandidate() = runBlocking {
        var current = true
        val discarded = CompletableDeferred<Int>()
        val upgrade = ConnectionUpgrade<Int>(this)
        upgrade.start({ 1 }, { current }, { true }, {
            kotlinx.coroutines.yield()
            current = false
        }, { fail("Stale session must not install") }, { discarded.complete(it) })
        assertEquals(1, withTimeout(2000) { discarded.await() })
        upgrade.cancel()
    }

    @Test fun workStartingDuringValidationDefersInstallation() = runBlocking {
        var idle = true
        var validations = 0
        val validated = CompletableDeferred<Unit>()
        val installed = CompletableDeferred<Int>()
        val upgrade = ConnectionUpgrade<Int>(this)
        upgrade.start({ 1 }, { true }, { idle }, {
            validations++
            if (validations == 1) {
                idle = false
                validated.complete(Unit)
            }
        }, { installed.complete(it) }, { fail("Candidate should be installed") })
        withTimeout(2000) { validated.await() }
        assertFalse(installed.isCompleted)
        idle = true
        assertEquals(1, withTimeout(2000) { installed.await() })
        assertEquals(2, validations)
        upgrade.cancel()
    }
}

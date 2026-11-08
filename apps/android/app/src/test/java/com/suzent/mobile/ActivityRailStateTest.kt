package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ActivityRailStateTest {
    @Test fun aCollapsedStreamingRailStaysClosedAcrossRemountAndTokenUpdates() {
        val choices = RailChoices()
        val key = "${railScope("chat", "live1")}:${railChunkKey(listOf(MessagePart("reasoning", text = "Looking")), 0)}"
        assertTrue(railExpanded(choices.choice(key), live = true, current = true, waiting = false))
        choices.set(key, false)
        // A recycled row has no local choice and reads the same conversation store.
        assertFalse(railExpanded(choices.choice(key), live = true, current = true, waiting = false))
        val updated = listOf(MessagePart("reasoning", text = "Looking further"), MessagePart("tool", toolName = "read_file", toolCallId = "t1", state = "running"))
        val sameKey = "${railScope("chat", "live1")}:${railChunkKey(updated, 0)}"
        assertEquals(key, sameKey)
        assertFalse(railExpanded(choices.choice(sameKey), live = true, current = true, waiting = false))
    }

    @Test fun reopeningAndANewStreamAreSeparateFromTheCollapsedRail() {
        val choices = RailChoices()
        val key = "${railScope("chat", "live1")}:i0"
        choices.set(key, false)
        choices.set(key, true)
        assertTrue(railExpanded(choices.choice(key), live = true, current = true, waiting = false))
        val first = nextStreamGeneration(0, wasStreaming = false, streaming = true)
        val held = nextStreamGeneration(first.first, first.second, streaming = true)
        val stopped = nextStreamGeneration(held.first, held.second, streaming = false)
        val second = nextStreamGeneration(stopped.first, stopped.second, streaming = true)
        assertEquals(1, held.first)
        assertEquals(2, second.first)
        val nextKey = "${railScope("chat", "live${second.first}")}:i0"
        assertNull(choices.choice(nextKey))
        assertTrue(railExpanded(choices.choice(nextKey), live = true, current = true, waiting = false))
    }

    @Test fun aNewChatDoesNotReuseChoices() {
        val previous = RailChoices()
        previous.set("${railScope("a", "m0")}:i0", false)
        val next = RailChoices()
        assertNull(next.choice("${railScope("b", "m0")}:i0"))
        assertTrue(railExpanded(next.choice("${railScope("b", "m0")}:i0"), live = true, current = true, waiting = false))
    }

    @Test fun approvalKeepsTheRailOpenAndAFinishedUntouchedRailCloses() {
        assertTrue(railExpanded(false, live = true, current = true, waiting = true))
        assertFalse(railExpanded(null, live = false, current = false, waiting = false))
    }

    @Test fun streamingStaysInkWhenAnEarlierToolFailed() {
        val parts = listOf(
            MessagePart("tool", toolName = "read_file", toolCallId = "a", state = "error"),
            MessagePart("tool", toolName = "grep_search", toolCallId = "b", state = "running"),
        )
        assertEquals(ActivityTone.Streaming, activityHeaderTone(parts, live = true, current = true))
        assertEquals("text", activityToneToken(ActivityTone.Streaming))
        assertFalse(activityToneToken(ActivityTone.Streaming) == "blue")
        assertEquals(ActivityTone.Failed, activityItemTone(failed = true, pending = false, active = false))
        assertEquals(ActivityTone.Streaming, activityItemTone(failed = false, pending = false, active = true))
        assertEquals("danger", activityToneToken(ActivityTone.Failed))
    }

    @Test fun aMixOfSuccessAndFailureDoesNotPaintTheWholeHeaderAsFailed() {
        val parts = listOf(
            MessagePart("tool", toolName = "read_file", toolCallId = "a", state = "completed"),
            MessagePart("tool", toolName = "write_file", toolCallId = "b", state = "error"),
        )
        assertEquals(ActivityTone.Idle, activityHeaderTone(parts, live = false, current = false))
        assertEquals("muted", activityToneToken(ActivityTone.Idle))
    }

    @Test fun everyToolFailingIsStillAFailedHeaderOnceTheStreamEnds() {
        val parts = listOf(
            MessagePart("tool", toolName = "read_file", toolCallId = "a", state = "error"),
            MessagePart("tool", toolName = "grep_search", toolCallId = "b", state = "denied"),
        )
        assertEquals(ActivityTone.Failed, activityHeaderTone(parts, live = false, current = false))
    }
}

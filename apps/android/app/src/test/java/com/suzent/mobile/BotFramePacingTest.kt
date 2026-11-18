package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BotFramePacingTest {
    @Test fun followsDisplayAndCapsAt120() {
        val pacing = BotFramePacing()
        assertEquals(60f, pacing.framesPerSecond(60f))
        assertEquals(90f, pacing.framesPerSecond(90f))
        assertEquals(120f, pacing.framesPerSecond(144f))
    }

    @Test fun sustainedOverloadFallsBackAndRecoversWithoutFlapping() {
        val pacing = BotFramePacing()
        repeat(7) { pacing.record(8_000_000, 120f) }
        assertFalse(pacing.limited)
        pacing.record(8_000_000, 120f)
        assertTrue(pacing.limited)
        assertEquals(60f, pacing.framesPerSecond(120f))
        repeat(239) { pacing.record(2_000_000, 120f) }
        assertTrue(pacing.limited)
        pacing.record(2_000_000, 120f)
        assertFalse(pacing.limited)
        assertEquals(120f, pacing.framesPerSecond(120f))
    }
}

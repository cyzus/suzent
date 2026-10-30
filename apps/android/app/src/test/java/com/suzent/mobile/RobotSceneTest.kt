package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RobotSceneTest {
    @Test fun everyVariantDrawsFiniteMarks() {
        for (variant in RobotVariant.entries) for (seconds in listOf(0.0, .37, 1.9, 7.25)) {
            val marks = RobotScene.frame(variant, seconds)
            assertTrue("$variant", marks.isNotEmpty())
            marks.filterIsInstance<RobotMark.Shape>().flatMap { it.points }.forEach { assertTrue("$variant", it.x.isFinite() && it.y.isFinite()) }
        }
    }

    @Test fun idleRobotSitsInTheMiddleOfItsSlot() {
        val body = RobotScene.frame(RobotVariant.IDLE, 0.0).first() as RobotMark.Shape
        assertEquals(4.0, body.points.minOf { it.x }, 1e-9)
        assertEquals(28.0, body.points.maxOf { it.y }, 1e-9)
    }

    @Test fun peekerStartsHiddenBelowItsSlot() {
        val body = RobotScene.frame(RobotVariant.PEEKER, 0.0).first() as RobotMark.Shape
        assertTrue(body.points.minOf { it.y } > RobotScene.SLOT)
        assertTrue(RobotScene.clips(RobotVariant.PEEKER))
    }

    @Test fun reducedMotionHoldsAVisibleFrameForEveryFace() {
        for (variant in RobotVariant.entries) {
            val body = RobotScene.frame(variant, 0.0, reduced = true).filterIsInstance<RobotMark.Shape>()
                .first { it.role == RobotRole.BODY && it.alpha > .9 && it.points.size > 8 }
            assertTrue("$variant", body.points.any { it.y in 0.0..RobotScene.SLOT })
        }
    }

    @Test fun badgeMoodFollowsDesktop() {
        assertEquals(RobotVariant.IDLE, robotPersonality(0.0))
        assertEquals(RobotVariant.OBSERVER, robotPersonality(.4))
        assertEquals(RobotVariant.DJ, robotPersonality(1.0))
        assertEquals(RobotVariant.SHAKER, robotBadgeVariant(RobotVariant.IDLE, startled = true, pending = true, streaming = true, tool = "Read"))
        assertEquals(RobotVariant.SKEPTIC, robotBadgeVariant(RobotVariant.IDLE, startled = false, pending = true, streaming = true, tool = "Read"))
        assertEquals(RobotVariant.EATER, robotBadgeVariant(RobotVariant.IDLE, startled = false, pending = false, streaming = true, tool = "Read"))
        assertEquals(RobotVariant.WORKOUT, robotBadgeVariant(RobotVariant.IDLE, startled = false, pending = false, streaming = true, tool = "Bash"))
        assertEquals(RobotVariant.OBSERVER, robotBadgeVariant(RobotVariant.LOVE, startled = false, pending = false, streaming = true, tool = null))
        assertEquals(RobotVariant.LOVE, robotBadgeVariant(RobotVariant.LOVE, startled = false, pending = false, streaming = false, tool = null))
        val parts = listOf(MessagePart("tool", toolName = "grep_search", output = "done"), MessagePart("tool", toolName = "web_search"), MessagePart("text", text = "Hi"))
        assertEquals("web_search", robotCurrentTool(parts))
        assertEquals(null, robotCurrentTool(listOf(MessagePart("tool", toolName = "grep_search", output = "done"), MessagePart("text", text = "Hi"))))
        assertTrue(!toolCallFailed(MessagePart("tool", toolName = "Bash", state = "error")))
    }
}

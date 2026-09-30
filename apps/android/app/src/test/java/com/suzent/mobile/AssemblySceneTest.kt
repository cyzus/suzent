package com.suzent.mobile

import org.junit.Assert.*
import org.junit.Test

class AssemblySceneTest {
    @Test fun badgeCollapsesAsSoonAsActivityOrTextAppears() {
        assertTrue(showAssemblyBadge(emptyList(), true))
        assertTrue(showAssemblyBadge(listOf(MessagePart("text", text = " ")), true))
        assertFalse(showAssemblyBadge(emptyList(), false))
        assertFalse(showAssemblyBadge(listOf(MessagePart("text", text = "hello")), true))
        assertFalse(showAssemblyBadge(listOf(MessagePart("reasoning")), true))
        assertFalse(showAssemblyBadge(listOf(MessagePart("tool")), true))
        assertFalse(showAssemblyBadge(listOf(MessagePart("tool"), MessagePart("text")), true))
    }

    @Test fun scanOnlyRunsAfterAssemblyAndHasProjectedDepth() {
        assertTrue(AssemblyScene.frame(.2).none { it.color == 0xFF408DFF })
        val scan = AssemblyScene.frame(2.2 / 1.45).filter { it.color == 0xFF408DFF }
        assertEquals(6, scan.size)
        assertTrue(scan.all { it.points.first().y != it.points.last().y })
        assertTrue(AssemblyScene.frame(3.2 / 1.45).none { it.color == 0xFF408DFF })
    }
    @Test fun reducedMotionKeepsAStableCompletedScene() {
        assertEquals(AssemblyScene.frame(0.0, true), AssemblyScene.frame(100.0, true))
    }
    @Test fun framesStayFiniteAcrossSeveralRandomizedCycles() {
        for (i in 0..400) for (mark in AssemblyScene.frame(i / 30.0)) {
            assertTrue(mark.alpha in 0.0..1.0)
            assertTrue(mark.points.all { it.x.isFinite() && it.y.isFinite() })
        }
    }
    @Test fun caretOnlyAppearsOnNonemptyLiveTextAndDoesNotBreakClosingFence() {
        assertEquals("", streamingMarkdown("", true))
        assertEquals("hello", streamingMarkdown("hello", false))
        assertEquals("hello ▍", streamingMarkdown("hello", true))
        assertEquals("```\nx\n```\n\n▍", streamingMarkdown("```\nx\n```", true))
    }
}

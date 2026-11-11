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
        assertTrue(AssemblyScene.frame(.2).none { it.color in listOf(0xFF737980, 0xFFc4c7ca, 0xFFa8adb3, 0xFFe0e2e4) })
        val scan = AssemblyScene.frame(2.2 / 1.45).filter { it.color in listOf(0xFF737980, 0xFFc4c7ca, 0xFFa8adb3, 0xFFe0e2e4) }
        assertEquals(10, scan.size)
        assertTrue(scan.all { it.points.first().y != it.points.last().y })
        assertTrue(AssemblyScene.frame(3.2 / 1.45).none { it.color in listOf(0xFF737980, 0xFFc4c7ca, 0xFFa8adb3, 0xFFe0e2e4) })
    }
    @Test fun reducedMotionMovesOnlyFinishedRobotsOneSlotAtATime() {
        fun shadows(seconds: Double) = AssemblyScene.frame(seconds, true).filter { it.color == 0xFF000000 }
        for (seconds in listOf(0.0, 1.0, 2.2, 2.5)) {
            val marks = AssemblyScene.frame(seconds, true)
            assertEquals(shadows(seconds).size * 2, marks.count { it.color == 0xFFE8ECEB })
            assertTrue(marks.all { it.width == .65 })
        }
        assertEquals(AssemblyScene.frame(0.0, true), AssemblyScene.frame(1.7, true))
        assertTrue(shadows(2.2).last().points[0].x > shadows(0.0).last().points[0].x)
        assertEquals(AssemblyScene.frame(0.0, true), AssemblyScene.frame(2.6, true))
    }
    @Test fun framesStayFiniteAcrossSeveralRandomizedCycles() {
        for (i in 0..400) for (mark in AssemblyScene.frame(i / 30.0)) {
            assertTrue(mark.alpha in 0.0..1.0)
            assertTrue(mark.points.all { it.x.isFinite() && it.y.isFinite() })
        }
    }

}

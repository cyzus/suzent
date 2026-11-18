package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SwipeAxisLockTest {
    @Test fun horizontalLockNeedsThirtyDegreesAndMinimumTravel() {
        val undecided = SwipeAxisLock()
        assertEquals(SwipeAxisLock.Axis.UNDECIDED, undecided.update(23.9, 0.0))
        assertEquals(SwipeAxisLock.Axis.UNDECIDED, undecided.axis)

        assertEquals(SwipeAxisLock.Axis.HORIZONTAL, SwipeAxisLock().update(24.0, 0.0))
        assertEquals(SwipeAxisLock.Axis.HORIZONTAL, SwipeAxisLock().update(-36.0, 8.0))

        val boundary = SwipeAxisLock.MIN_TRAVEL / SwipeAxisLock.DOMINANCE
        assertEquals(SwipeAxisLock.Axis.HORIZONTAL, SwipeAxisLock().update(SwipeAxisLock.MIN_TRAVEL, boundary))
        assertEquals(SwipeAxisLock.Axis.VERTICAL, SwipeAxisLock().update(SwipeAxisLock.MIN_TRAVEL, boundary + 0.05))
        assertEquals(SwipeAxisLock.Axis.VERTICAL, SwipeAxisLock().update(40.0, 40.0))
        assertEquals(SwipeAxisLock.Axis.VERTICAL, SwipeAxisLock().update(10.0, 30.0))
    }

    @Test fun directionLockSticksAndScrollWins() {
        val lock = SwipeAxisLock()
        assertEquals(SwipeAxisLock.Axis.UNDECIDED, lock.update(10.0, 4.0))
        assertEquals(SwipeAxisLock.Axis.VERTICAL, lock.update(12.0, 30.0))
        assertEquals(SwipeAxisLock.Axis.VERTICAL, lock.update(200.0, 30.0))

        val scrolling = SwipeAxisLock()
        scrolling.noteVerticalScroll()
        assertEquals(SwipeAxisLock.Axis.VERTICAL, scrolling.update(80.0, 0.0))
        scrolling.reset()
        assertEquals(SwipeAxisLock.Axis.UNDECIDED, scrolling.axis)
        assertEquals(SwipeAxisLock.Axis.HORIZONTAL, scrolling.update(40.0, 0.0))
    }

    @Test fun commitNeedsTriggerOrAFlickInTheSameDirection() {
        assertTrue(SwipeAxisLock.commits(96.0, 0.0))
        assertFalse(SwipeAxisLock.commits(95.0, 0.0))
        assertFalse(SwipeAxisLock.commits(30.0, 900.0))
        assertTrue(SwipeAxisLock.commits(56.0, 900.0))
        assertFalse(SwipeAxisLock.commits(-30.0, -900.0))
        assertTrue(SwipeAxisLock.commits(-56.0, -900.0))
        assertFalse(SwipeAxisLock.commits(30.0, -900.0))
        assertFalse(SwipeAxisLock.commits(23.0, 2000.0))
        assertFalse(SwipeAxisLock.commits(80.0, -900.0))
        assertTrue(SwipeAxisLock.commits(-96.0, -100.0))
    }

    @Test fun earlyVerticalMovementCannotBecomeASwipe() {
        for (direction in listOf(-1.0, 1.0)) {
            val lock = SwipeAxisLock()
            assertEquals(SwipeAxisLock.Axis.VERTICAL, lock.update(direction * 6.0, 8.0))
            assertEquals(SwipeAxisLock.Axis.VERTICAL, lock.update(direction * 100.0, 10.0))
            assertFalse(SwipeAxisLock.commits(direction * 40.0, direction * 2000.0))
        }
    }

    @Test fun zoomedImageKeepsVerticalPanning() {
        assertTrue(SwipeAxisLock.imageDragYieldsToScroll(1f, false, SwipeAxisLock.Axis.VERTICAL))
        assertFalse(SwipeAxisLock.imageDragYieldsToScroll(1f, false, SwipeAxisLock.Axis.HORIZONTAL))
        assertFalse(SwipeAxisLock.imageDragYieldsToScroll(1f, false, SwipeAxisLock.Axis.UNDECIDED))
        assertFalse(SwipeAxisLock.imageDragYieldsToScroll(1f, true, SwipeAxisLock.Axis.VERTICAL))
        assertFalse(SwipeAxisLock.imageDragYieldsToScroll(2.5f, false, SwipeAxisLock.Axis.VERTICAL))
    }

    @Test fun systemRecognizerUsesTheSameAngleBeforeMinimumTravel() {
        assertTrue(SwipeAxisLock.angleIsHorizontal(12.0, 3.0))
        assertFalse(SwipeAxisLock.angleIsHorizontal(12.0, 10.0))
        assertFalse(SwipeAxisLock.angleIsHorizontal(2.0, 14.0))
        assertTrue(SwipeAxisLock.angleIsHorizontal(0.0, 0.0, vx = 400.0, vy = 40.0))
        assertFalse(SwipeAxisLock.angleIsHorizontal(0.0, 0.0, vx = 40.0, vy = 400.0))
        assertFalse(SwipeAxisLock.angleIsHorizontal(0.0, 0.0))
    }
}

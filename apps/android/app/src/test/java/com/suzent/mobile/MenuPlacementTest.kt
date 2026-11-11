package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Test

class MenuPlacementTest {
    @Test fun leavesSpaceBelowTheFinger() {
        val placed = placeMenu(100, 200, 240, 160, 400, 800, margin = 8, touchGap = 8)
        assertEquals(208, placed.y)
    }

    @Test fun flipsAboveTheFingerWhenThereIsNotEnoughRoomBelow() {
        val placed = placeMenu(100, 700, 240, 160, 400, 800, margin = 8, touchGap = 8)
        assertEquals(532, placed.y)
    }

    @Test fun clampsTallMenusWhenNeitherSideFits() {
        val placed = placeMenu(100, 400, 240, 700, 400, 800, margin = 8, touchGap = 8)
        assertEquals(92, placed.y)
    }

    @Test fun keepsAMenuBesideThePressWhenItFits() {
        val placed = placeMenu(180, 240, 200, 120, 1080, 1920, margin = 8)
        assertEquals(180, placed.x)
        assertEquals(240, placed.y)
        assertEquals(1064, placed.maxWidth)
        assertEquals(1904, placed.maxHeight)
    }

    @Test fun shiftsACornerPressBackInsideTheSafeArea() {
        val placed = placeMenu(1000, 1800, 260, 220, 1080, 1920, insetTop = 40, insetBottom = 48, margin = 8)
        assertEquals(1080 - 8 - 260, placed.x)
        assertEquals(1920 - 48 - 8 - 220, placed.y)
    }

    @Test fun keepsTheTopLeftPressBelowTheStatusBar() {
        val placed = placeMenu(0, 0, 260, 180, 1080, 1920, insetLeft = 0, insetTop = 48, margin = 8)
        assertEquals(8, placed.x)
        assertEquals(56, placed.y)
    }

    @Test fun shrinksToAShortLandscapeWindowAndScrolls() {
        val placed = placeMenu(700, 300, 260, 500, 800, 360, insetTop = 24, insetBottom = 24, margin = 8)
        assertEquals(800 - 8 - 260, placed.x)
        assertEquals(24 + 8, placed.y)
        assertEquals(800 - 16, placed.maxWidth)
        assertEquals(360 - 24 - 24 - 16, placed.maxHeight)
    }

    @Test fun anchorsToThePressedElementWhenThereIsNoFinger() {
        // TalkBack opens the menu at the row's top edge; the same clamp applies.
        val placed = placeMenu(12, 640, 260, 400, 400, 700, margin = 8)
        assertEquals(12, placed.x)
        assertEquals(700 - 8 - 400, placed.y)
    }
}

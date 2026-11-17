package com.suzent.mobile

import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Decides whether a touch is a horizontal swipe or a vertical scroll.
 *
 * The lock is taken once, at the first sample that travels [MIN_TRAVEL] (24 px in the
 * caller's space) in either axis, and it never flips. Horizontal wins only inside a
 * 30° cone: `|dx| >= |dy| * sqrt(3)`. [noteVerticalScroll] records that scrolling
 * already started, so a later sideways drift cannot claim the gesture.
 *
 * Keep the thresholds identical to `SwipeAxisLock` in SuzentCore.
 */
class SwipeAxisLock {
    enum class Axis { UNDECIDED, HORIZONTAL, VERTICAL }

    var axis: Axis = Axis.UNDECIDED
        private set

    fun noteVerticalScroll() {
        if (axis == Axis.UNDECIDED) axis = Axis.VERTICAL
    }

    fun update(dx: Double, dy: Double): Axis {
        if (axis != Axis.UNDECIDED) return axis
        val adx = abs(dx)
        val ady = abs(dy)
        if (adx < MIN_TRAVEL && ady < MIN_TRAVEL) return Axis.UNDECIDED
        axis = if (adx >= MIN_TRAVEL && adx + 1e-9 >= ady * DOMINANCE) Axis.HORIZONTAL else Axis.VERTICAL
        return axis
    }

    fun reset() {
        axis = Axis.UNDECIDED
    }

    companion object {
        const val MIN_TRAVEL = 24.0
        val DOMINANCE = sqrt(3.0)
        const val TRIGGER = 72.0
        const val VELOCITY_TRIGGER = 900.0

        /** Commit a swipe that has already locked horizontal. [velocity] is px/s, positive toward the trailing edge. */
        fun commits(offset: Double, velocity: Double): Boolean {
            val travel = abs(offset)
            if (travel < MIN_TRAVEL) return false
            val along = if (offset < 0) -velocity else velocity
            if (along <= -VELOCITY_TRIGGER) return false
            return travel >= TRIGGER || along >= VELOCITY_TRIGGER
        }

        /**
         * Angle check for a recognizer that must accept or reject at the platform touch slop,
         * before [MIN_TRAVEL]. In-app swipes use [update], which also requires that travel.
         */
        fun angleIsHorizontal(dx: Double, dy: Double, vx: Double = 0.0, vy: Double = 0.0): Boolean {
            val adx = abs(dx)
            val ady = abs(dy)
            if (adx >= 1 || ady >= 1) {
                if (ady > adx) return false
                return adx + 1e-9 >= ady * DOMINANCE
            }
            val avx = abs(vx)
            val avy = abs(vy)
            if (avx < 1 && avy < 1) return false
            return avx > avy && avx + 1e-9 >= avy * DOMINANCE
        }
    }
}

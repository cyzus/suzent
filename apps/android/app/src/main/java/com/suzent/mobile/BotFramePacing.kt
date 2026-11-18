package com.suzent.mobile

/** Keep animation work inside the display budget without oscillating between rates. */
internal class BotFramePacing {
    var limited = false
        private set
    private var slowFrames = 0
    private var fastFrames = 0

    fun framesPerSecond(displayRate: Float): Float =
        displayRate.coerceIn(1f, 120f).let { if (limited) minOf(it, 60f) else it }

    fun record(workNanos: Long, displayRate: Float) {
        if (displayRate <= 60f) return
        val budget = 1_000_000_000.0 / displayRate.coerceAtMost(120f)
        if (!limited) {
            slowFrames = if (workNanos > budget * .8) slowFrames + 1 else 0
            if (slowFrames >= 8) { limited = true; slowFrames = 0 }
        } else {
            fastFrames = if (workNanos < budget * .5) fastFrames + 1 else 0
            if (fastFrames >= 240) { limited = false; fastFrames = 0 }
        }
    }
}

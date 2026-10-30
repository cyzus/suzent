package com.suzent.mobile

import kotlin.math.floor

/** A CSS timing function, so keyframes ported from the desktop stylesheet ease the same way. */
internal data class Curve(val x1: Double, val y1: Double, val x2: Double, val y2: Double, val stepEnd: Boolean = false) {
    fun at(t: Double): Double {
        if (stepEnd) return if (t >= 1) 1.0 else 0.0
        if (t <= 0) return 0.0
        if (t >= 1) return 1.0
        fun bezier(u: Double, a: Double, b: Double) = 3 * a * u * (1 - u) * (1 - u) + 3 * b * u * u * (1 - u) + u * u * u
        var low = 0.0
        var high = 1.0
        repeat(24) {
            val mid = (low + high) / 2
            if (bezier(mid, x1, x2) < t) low = mid else high = mid
        }
        return bezier((low + high) / 2, y1, y2)
    }

    companion object {
        val linear = Curve(0.0, 0.0, 1.0, 1.0)
        val ease = Curve(.25, .1, .25, 1.0)
        val easeIn = Curve(.42, 0.0, 1.0, 1.0)
        val easeOut = Curve(0.0, 0.0, .58, 1.0)
        val easeInOut = Curve(.42, 0.0, .58, 1.0)
        val stepEnd = Curve(0.0, 0.0, 1.0, 1.0, stepEnd = true)
    }
}

/** Where an infinite CSS animation is in its cycle, 0..1; `alternate` plays every other cycle backwards. */
internal fun cycle(seconds: Double, duration: Double, delay: Double = 0.0, alternate: Boolean = false): Double {
    val elapsed = (seconds - delay) / duration
    val progress = elapsed - floor(elapsed)
    return if (alternate && floor(elapsed).toLong() % 2 != 0L) 1 - progress else progress
}

/** One property's CSS keyframes; [curves] overrides the timing function per segment, like animation-timing-function inside a keyframe. */
internal fun keyframe(progress: Double, stops: DoubleArray, values: DoubleArray, curve: Curve = Curve.ease, curves: List<Curve>? = null): Double {
    if (progress <= stops.first()) return values.first()
    for (index in 1 until stops.size) {
        if (progress <= stops[index]) {
            val span = stops[index] - stops[index - 1]
            val local = if (span <= 0) 1.0 else (progress - stops[index - 1]) / span
            val eased = (curves?.get(index - 1) ?: curve).at(local)
            return values[index - 1] + (values[index] - values[index - 1]) * eased
        }
    }
    return values.last()
}

internal fun keyframe(progress: Double, stops: List<Double>, values: List<Double>, curve: Curve = Curve.ease): Double =
    keyframe(progress, stops.toDoubleArray(), values.toDoubleArray(), curve)

/** A running tool icon's offset (desktop px on its 14px icon), turn, scale and fade, plus the scan sweep line. */
internal data class ToolIconPose(val dx: Double = 0.0, val dy: Double = 0.0, val rotation: Double = 0.0, val scale: Double = 1.0,
                                 val alpha: Double = 1.0, val sweepY: Double = 0.0, val sweepAlpha: Double = 0.0)

/** Desktop's tool-icon-* keyframes (styles.css) for each [activityToolAnimation] kind. */
internal fun toolIconPose(kind: String, seconds: Double): ToolIconPose {
    fun track(duration: Double, curve: Curve, stops: List<Double>, values: List<Double>) =
        keyframe(cycle(seconds, duration), stops, values, curve)
    val sharp = Curve(.4, 0.0, .2, 1.0)
    return when (kind) {
        "pending" -> ToolIconPose(rotation = track(1.4, sharp, listOf(0.0, .3, .7, 1.0), listOf(0.0, 12.0, -12.0, 0.0)))
        "terminal" -> ToolIconPose(alpha = track(1.0, Curve.easeInOut, listOf(0.0, .5, 1.0), listOf(1.0, .35, 1.0)),
            scale = track(1.0, Curve.easeInOut, listOf(0.0, .5, 1.0), listOf(1.0, .95, 1.0)))
        "scan" -> ToolIconPose(sweepY = track(1.25, sharp, listOf(0.0, 1.0), listOf(-7.0, 7.0)),
            sweepAlpha = track(1.25, sharp, listOf(0.0, .2, .8, 1.0), listOf(0.0, .85, .85, 0.0)))
        "typewriter" -> {
            val strike = Curve(.36, .07, .19, .97)
            val stops = listOf(0.0, .35, .7, 1.0)
            ToolIconPose(dx = track(.75, strike, stops, listOf(0.0, .75, -.5, 0.0)), dy = track(.75, strike, stops, listOf(0.0, -1.0, .25, 0.0)),
                rotation = track(.75, strike, stops, listOf(0.0, -8.0, 3.0, 0.0)))
        }
        "radar" -> {
            val stops = listOf(0.0, .33, .66, 1.0)
            ToolIconPose(dx = track(1.3, Curve.easeInOut, stops, listOf(0.0, -.75, .75, 0.0)), dy = track(1.3, Curve.easeInOut, stops, listOf(0.0, -.5, .5, 0.0)),
                scale = track(1.3, Curve.easeInOut, stops, listOf(1.0, 1.1, .96, 1.0)))
        }
        "signal" -> ToolIconPose(scale = track(1.0, Curve.easeInOut, listOf(0.0, .5, 1.0), listOf(1.0, 1.14, 1.0)),
            alpha = track(1.0, Curve.easeInOut, listOf(0.0, .5, 1.0), listOf(1.0, .65, 1.0)))
        "memory" -> ToolIconPose(alpha = track(1.2, Curve.easeInOut, listOf(0.0, .4, .75, 1.0), listOf(1.0, .45, .85, 1.0)),
            scale = track(1.2, Curve.easeInOut, listOf(0.0, .4, .75, 1.0), listOf(1.0, .93, 1.04, 1.0)))
        "snap" -> ToolIconPose(dy = track(1.0, Curve(.34, 1.56, .64, 1.0), listOf(0.0, .3, .6, 1.0), listOf(0.0, -1.25, 1.0, 0.0)))
        "cursor" -> {
            val stops = listOf(0.0, .4, .65, 1.0)
            ToolIconPose(dx = track(1.15, sharp, stops, listOf(0.0, 1.0, 1.0, 0.0)), dy = track(1.15, sharp, stops, listOf(0.0, -1.0, -1.0, 0.0)),
                scale = track(1.15, sharp, stops, listOf(1.0, 1.04, .88, 1.0)))
        }
        else -> ToolIconPose()
    }
}

/** One frame of desktop's brutal-running-* surface: where the wave's peak is (fraction of twice the width) and how far the grid has slid (px). */
internal data class RunningSurfaceFrame(val wave: Double, val gridShift: Double, val stops: List<Double>, val alphas: List<Double>)

/** Desktop's brutal-running-{mono,dots,scan} backgrounds, with the lighter inline alphas activity-turn-tool uses. */
internal fun runningSurfaceFrame(kind: String, seconds: Double): RunningSurfaceFrame {
    val duration = when (kind) { "scan" -> 1.2; "dots" -> 1.4; else -> 1.35 }
    val u = cycle(seconds, duration)
    return when (kind) {
        "scan" -> RunningSurfaceFrame(u, 0.0, listOf(0.0, .42, .48, .5, .52, .58, 1.0), listOf(0.0, 0.0, .09, .28, .09, 0.0, 0.0))
        "dots" -> RunningSurfaceFrame(u, 12 * u, listOf(0.0, .35, .5, .65, 1.0), listOf(0.0, .06, .13, .06, 0.0))
        else -> RunningSurfaceFrame(u, 12 * u, listOf(0.0, .35, .5, .65, 1.0), listOf(0.0, .05, .12, .05, 0.0))
    }
}

/** One frame of desktop's reasoning-thinking-label: the sweep image's background-position and the ink bar's span, both as fractions of the word. */
internal data class ThinkingLabelFrame(val sweep: Double, val barStart: Double, val barEnd: Double)

/**
 * Desktop's reasoning-thinking-sweep and -redact (1.8s): the bar wipes on in six steps, holds, wipes off, then the
 * sweep's pale notch, parked off the right edge until then, runs back over the word.
 */
internal fun thinkingLabelFrame(seconds: Double): ThinkingLabelFrame {
    val u = cycle(seconds, 1.8)
    val sweep = if (u < .6) .2 else .8 - (u - .6) / .4 * .6
    return when {
        u < .24 -> ThinkingLabelFrame(sweep, 0.0, floor(u / .24 * 6) / 6)
        u < .36 -> ThinkingLabelFrame(sweep, 0.0, 1.0)
        u < .56 -> ThinkingLabelFrame(sweep, floor((u - .36) / .2 * 6) / 6, 1.0)
        else -> ThinkingLabelFrame(sweep, 1.0, 1.0)
    }
}

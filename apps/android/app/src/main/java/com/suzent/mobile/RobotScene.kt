/*
 * LICENSE EXCEPTION
 * Use of this file (Robot Character Design and Animation Choreography) is governed by the terms in LICENSE-ASSETS.
 * It is NOT covered by the project's standard Apache 2.0 license.
 */
package com.suzent.mobile

import kotlin.math.cos
import kotlin.math.sin

/** Desktop's RobotAvatar variants (RobotAvatar.tsx), named the same. */
enum class RobotVariant { IDLE, OBSERVER, JUMPER, SNOOZER, PEEKER, SHAKER, SKEPTIC, LOVE, PARTY, EATER, DJ, WORKOUT, PORTAL, SCANNER }

/** Fixed robot colours, plus [INK] for the floating marks that must read on the card in either theme. */
enum class RobotRole { BODY, EYE, INK, GRAY, DARK }

internal data class RobotPoint(val x: Double, val y: Double)

internal sealed interface RobotMark {
    val role: RobotRole
    val alpha: Double

    data class Shape(val points: List<RobotPoint>, override val role: RobotRole, override val alpha: Double = 1.0, val stroke: Double = 0.0) : RobotMark

    /** Text at ([x], [y]) baseline in robot units, drawn through [matrix] into the slot. */
    data class Glyph(val text: String, val x: Double, val y: Double, val size: Double, val matrix: Affine,
                     override val role: RobotRole, override val alpha: Double = 1.0) : RobotMark
}

/** A 2D affine transform: x' = a·x + c·y + e, y' = b·x + d·y + f. */
internal data class Affine(val a: Double = 1.0, val b: Double = 0.0, val c: Double = 0.0, val d: Double = 1.0, val e: Double = 0.0, val f: Double = 0.0) {
    operator fun times(o: Affine) = Affine(a * o.a + c * o.b, b * o.a + d * o.b, a * o.c + c * o.d, b * o.c + d * o.d, a * o.e + c * o.f + e, b * o.e + d * o.f + f)
    fun apply(p: RobotPoint) = RobotPoint(a * p.x + c * p.y + e, b * p.x + d * p.y + f)

    companion object {
        fun translate(x: Double, y: Double) = Affine(e = x, f = y)
        fun scale(x: Double, y: Double = x) = Affine(a = x, d = y)
        fun rotate(degrees: Double): Affine {
            val r = Math.toRadians(degrees)
            return Affine(cos(r), sin(r), -sin(r), cos(r))
        }
        /** A CSS transform applied around transform-origin ([x], [y]). */
        fun about(x: Double, y: Double, transform: Affine) = translate(x, y) * transform * translate(-x, -y)
    }
}

/**
 * Desktop's robot (RobotAvatar.tsx with robot-animations.css) as flat marks in a 32-unit slot. The desktop
 * badge draws the 24-unit robot at 0.75 scale in a 32px box, so one robot unit is one slot unit, offset by 4.
 */
internal object RobotScene {
    const val SLOT = 32.0
    private val toSlot = Affine.translate(4.0, 4.0)
    private val center = 12.0 to 12.0
    private val bottom = 12.0 to 28.0

    /** Peeker hides below its slot, so its marks are clipped to it. */
    fun clips(variant: RobotVariant) = variant == RobotVariant.PEEKER

    fun frame(variant: RobotVariant, seconds: Double, reduced: Boolean = false): List<RobotMark> {
        // Reduced motion holds one frame; the peeker and the portal start hidden, so they hold a moment they are in view.
        val t = if (!reduced) seconds else when (variant) {
            RobotVariant.PEEKER -> 1.8
            RobotVariant.PORTAL -> .7
            else -> 0.0
        }
        val marks = mutableListOf<RobotMark>()
        fun about(origin: Pair<Double, Double>, transform: Affine) = Affine.about(origin.first, origin.second, transform)
        fun rect(x: Double, y: Double, w: Double, h: Double, r: Double, m: Affine, role: RobotRole, alpha: Double = 1.0) {
            marks += RobotMark.Shape(roundedRect(x, y, w, h, r).map { (toSlot * m).apply(it) }, role, alpha)
        }
        fun ellipse(cx: Double, cy: Double, rx: Double, ry: Double, m: Affine, role: RobotRole, alpha: Double = 1.0) {
            marks += RobotMark.Shape(ellipsePoints(cx, cy, rx, ry).map { (toSlot * m).apply(it) }, role, alpha)
        }
        fun path(points: List<RobotPoint>, m: Affine, role: RobotRole, stroke: Double = 0.0) {
            marks += RobotMark.Shape(points.map { (toSlot * m).apply(it) }, role, 1.0, stroke)
        }
        fun glyph(text: String, x: Double, y: Double, size: Double, m: Affine, role: RobotRole, alpha: Double = 1.0) {
            marks += RobotMark.Glyph(text, x, y, size, toSlot * m, role, alpha)
        }
        fun body(m: Affine) = rect(0.0, 0.0, 24.0, 24.0, 4.0, m, RobotRole.BODY)
        fun eyes(m: Affine, left: Affine = Affine(), right: Affine = Affine()) {
            rect(5.0, 8.0, 5.0, 5.0, 1.5, m * left, RobotRole.EYE)
            rect(14.0, 8.0, 5.0, 5.0, 1.5, m * right, RobotRole.EYE)
        }
        fun face(m: Affine, eyes: Affine = Affine()) { body(m); eyes(m, eyes, eyes) }
        fun track(duration: Double, stops: List<Double>, values: List<Double>, curve: Curve = Curve.ease, delay: Double = 0.0, alternate: Boolean = false) =
            keyframe(cycle(t, duration, delay, alternate), stops, values, curve)

        when (variant) {
            RobotVariant.IDLE -> {
                val blink = listOf(0.0, .94, .96, .98, 1.0) to listOf(1.0, 1.0, .25, 1.0, 1.0)
                val squeeze = track(6.5, blink.first, blink.second, Curve(.4, 0.0, .2, 1.0))
                body(Affine())
                rect(5.0, 8.0, 5.0, 5.0, 1.5, Affine.about(7.5, 10.5, Affine.scale(1.0, squeeze)), RobotRole.EYE)
                rect(14.0, 8.0, 5.0, 5.0, 1.5, Affine.about(16.5, 10.5, Affine.scale(1.0, squeeze)), RobotRole.EYE)
            }
            RobotVariant.OBSERVER -> {
                val stops = listOf(0.0, .1, .2, .25, .4, .5, .6, .75, .8, 1.0)
                val x = track(4.0, stops, listOf(0.0, -2.0, -2.0, 2.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0), Curve.stepEnd)
                val y = track(4.0, stops, listOf(0.0, 0.0, 0.0, 0.0, 0.0, -2.0, 0.0, 0.0, 0.0, 0.0), Curve.stepEnd)
                val squeeze = track(4.0, stops, listOf(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, .1, 1.0, 1.0), Curve.stepEnd)
                body(Affine())
                eyes(Affine.translate(x, y) * about(center, Affine.scale(1.0, squeeze)))
            }
            RobotVariant.JUMPER -> {
                val stops = listOf(0.0, .1, .45, .55, .9, 1.0)
                val curves = listOf(Curve.easeOut, Curve.easeOut, Curve(.2, 0.0, .4, 1.0), Curve.easeIn, Curve.easeOut)
                val p = cycle(t, 1.2)
                val y = keyframe(p, stops.toDoubleArray(), doubleArrayOf(0.0, 0.0, -6.0, -6.0, 0.0, 0.0), curves = curves)
                val sx = keyframe(p, stops.toDoubleArray(), doubleArrayOf(1.15, .9, 1.0, 1.0, .9, 1.15), curves = curves)
                val sy = keyframe(p, stops.toDoubleArray(), doubleArrayOf(.85, 1.1, 1.0, 1.0, 1.1, .85), curves = curves)
                face(Affine.about(12.0, 24.0, Affine.translate(0.0, y) * Affine.scale(sx, sy)))
            }
            RobotVariant.SNOOZER -> {
                val breathe = about(center, Affine.scale(track(4.0, listOf(0.0, .5, 1.0), listOf(1.0, 1.02, 1.0), Curve.easeInOut)))
                val eyes = about(center, Affine.scale(1.0, track(4.0, listOf(0.0, .5, 1.0), listOf(.1, .15, .1), Curve.easeInOut)))
                face(breathe, eyes)
                listOf(Triple("Z", 26.0 to 4.0, 5.0), Triple("z", 28.0 to 8.0, 4.0), Triple(".", 27.0 to 12.0, 3.0)).forEachIndexed { index, (text, at, size) ->
                    val p = cycle(t, 3.0, index.toDouble())
                    val float = Affine.translate(0.0, keyframe(p, listOf(0.0, 1.0), listOf(0.0, -7.2), Curve.linear)) *
                        Affine.rotate(keyframe(p, listOf(0.0, 1.0), listOf(-10.0, 10.0), Curve.linear))
                    glyph(text, at.first, at.second, size, breathe * float, RobotRole.INK, keyframe(p, listOf(0.0, .2, .8, 1.0), listOf(0.0, 1.0, 1.0, 0.0), Curve.linear))
                }
            }
            RobotVariant.PEEKER -> {
                val stops = listOf(0.0, .1, .2, .4, .6, .7, .8, 1.0)
                val y = track(3.0, stops, listOf(35.2, 0.0, 0.0, 0.0, 0.0, 12.8, 0.0, 35.2), Curve.easeInOut)
                val turn = track(3.0, stops, listOf(0.0, 0.0, -10.0, 10.0, 0.0, 0.0, 0.0, 0.0), Curve.easeInOut)
                val look = track(3.0, listOf(0.0, .1, .2, .4, .6, 1.0), listOf(0.0, 0.0, -3.0, 3.0, 0.0, 0.0), Curve.easeInOut)
                face(about(bottom, Affine.translate(0.0, y) * Affine.rotate(turn)), Affine.translate(look, 0.0))
            }
            RobotVariant.SHAKER -> {
                val stops = (0..10).map { it / 10.0 }
                val shake = about(center, Affine.translate(
                    track(.2, stops, listOf(.5, -.5, -1.5, 1.5, .5, -.5, -1.5, 1.5, -.5, .5, .5)),
                    track(.2, stops, listOf(.5, -1.0, 0.0, 1.0, -.5, 1.0, .5, .5, -.5, 1.0, -1.0))) *
                    Affine.rotate(track(.2, stops, listOf(0.0, -1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 1.0, 0.0, -1.0, 0.0))))
                face(shake, about(center, Affine.scale(track(2.0, listOf(0.0, 1.0), listOf(1.0, 1.3), alternate = true))))
                listOf(listOf(-5.0, 2.0, 1.5, 2.0, .8, 0.0), listOf(-6.0, 5.0, 1.0, 1.5, .7, .2), listOf(29.0, 2.0, 1.5, 2.0, .8, .4), listOf(30.0, 5.0, 1.0, 1.5, .7, .1)).forEach { drop ->
                    val (cx, cy, rx, ry) = drop
                    val p = cycle(t, drop[4], drop[5])
                    val fall = Affine.translate(0.0, keyframe(p, listOf(0.0, 1.0), listOf(0.0, 15.0))) * Affine.about(cx, cy, Affine.scale(keyframe(p, listOf(0.0, 1.0), listOf(1.0, .5))))
                    ellipse(cx, cy, rx, ry, shake * fall, RobotRole.INK, keyframe(p, listOf(0.0, 1.0), listOf(1.0, 0.0)))
                }
            }
            RobotVariant.SKEPTIC -> {
                val half = listOf(0.0, .5, 1.0)
                val tilt = about(bottom, Affine.rotate(track(3.0, half, listOf(0.0, -5.0, 0.0), Curve.easeInOut)) * Affine.translate(track(3.0, half, listOf(0.0, -2.0, 0.0), Curve.easeInOut), 0.0))
                body(tilt)
                eyes(tilt, about(center, Affine.scale(1.0, track(3.0, half, listOf(1.0, .6, 1.0), Curve.easeInOut))),
                    Affine.translate(0.0, track(3.0, half, listOf(0.0, -2.0, 0.0), Curve.easeInOut)))
                val q = Affine.translate(0.0, track(3.0, half, listOf(0.0, -1.0, 0.0), Curve.easeInOut)) * Affine.scale(track(3.0, half, listOf(1.0, 1.2, 1.0), Curve.easeInOut))
                glyph("?", 22.0, 4.0, 8.0, tilt * q, RobotRole.INK, track(3.0, half, listOf(0.0, 1.0, 0.0), Curve.easeInOut))
            }
            RobotVariant.LOVE -> {
                val beat = about(center, Affine.scale(track(1.0, listOf(0.0, .15, .3, .45, .6, 1.0), listOf(1.0, 1.1, 1.0, 1.1, 1.0, 1.0))))
                body(beat)
                val pulse = about(center, Affine.scale(track(1.0, listOf(0.0, 1.0), listOf(1.0, 1.3), alternate = true)))
                glyph("♥", 5.5, 12.0, 5.0, beat * pulse, RobotRole.EYE)
                glyph("♥", 14.5, 12.0, 5.0, beat * pulse, RobotRole.EYE)
                listOf(listOf(-4.0, 4.0, 4.0, 0.0), listOf(-2.0, 0.0, 3.0, .5), listOf(26.0, 6.0, 4.0, 1.0), listOf(24.0, -2.0, 3.0, 1.5)).forEach { (x, y, size, delay) ->
                    val p = cycle(t, 2.0, delay)
                    glyph("♥", x, y, size, beat * Affine.translate(0.0, keyframe(p, listOf(0.0, 1.0), listOf(10.0, -30.0), Curve.linear)), RobotRole.INK,
                        keyframe(p, listOf(0.0, .2, .8, 1.0), listOf(0.0, 1.0, 1.0, 0.0), Curve.linear))
                }
            }
            RobotVariant.PARTY -> {
                body(Affine())
                val bounce = Affine.translate(0.0, track(.5, listOf(0.0, .5, 1.0), listOf(0.0, -2.0, 0.0), Curve.easeInOut))
                rect(4.0, 8.0, 16.0, 6.0, 1.0, bounce, RobotRole.EYE)
                rect(5.0, 9.0, 14.0, 1.0, 0.0, bounce, RobotRole.EYE, .5)
            }
            RobotVariant.EATER -> {
                val stops = listOf(0.0, .1, .4, .55, .65, .9, 1.0)
                val top = Affine.about(4.0, 15.0, Affine.translate(0.0, track(1.5, stops, listOf(0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0), Curve.easeInOut)) *
                    Affine.rotate(track(1.5, stops, listOf(0.0, -30.0, 0.0, 0.0, 0.0, 0.0, 0.0), Curve.easeInOut)))
                val jaw = Affine.about(4.0, 15.0, Affine.translate(0.0, track(1.5, stops, listOf(0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0), Curve.easeInOut)) *
                    Affine.rotate(track(1.5, stops, listOf(0.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0), Curve.easeInOut)))
                path(quadPath(listOf(0.0 to 4.0), listOf(Triple(0.0 to 0.0, 4.0 to 0.0, false), Triple(20.0 to 0.0, 20.0 to 0.0, true),
                    Triple(24.0 to 0.0, 24.0 to 4.0, false), Triple(24.0 to 15.0, 24.0 to 15.0, true), Triple(0.0 to 15.0, 0.0 to 15.0, true))), top, RobotRole.BODY)
                rect(7.5, 8.0, 5.0, 5.0, 1.5, top, RobotRole.EYE)
                rect(15.5, 8.0, 5.0, 5.0, 1.5, top, RobotRole.EYE)
                path(quadPath(listOf(0.0 to 15.0), listOf(Triple(24.0 to 15.0, 24.0 to 15.0, true), Triple(24.0 to 20.0, 24.0 to 20.0, true),
                    Triple(24.0 to 24.0, 20.0 to 24.0, false), Triple(4.0 to 24.0, 4.0 to 24.0, true), Triple(0.0 to 24.0, 0.0 to 20.0, false))), jaw, RobotRole.BODY)
                val bites = listOf(listOf("0" to 0.0, "0" to 5.0, "0" to 10.0), listOf("0" to 6.0), listOf("0" to 3.0, "1" to 8.0), listOf("0" to 3.0, "0" to 8.0),
                    listOf("0" to 0.0, "0" to 5.0, "0" to 10.0), listOf("1" to 6.0), listOf("0" to 0.0, "1" to 5.0, "1" to 10.0), listOf("0" to 6.0))
                bites.forEachIndexed { index, bite ->
                    val p = cycle(t, 12.0, index * 1.5)
                    val alpha = keyframe(p, listOf(0.0, .02, .05, .051, 1.0), listOf(0.0, 1.0, 1.0, 0.0, 0.0), Curve.linear)
                    if (alpha <= 0) return@forEachIndexed
                    val feed = Affine.translate(0.0, 15.0) * Affine.translate(keyframe(p, listOf(0.0, .05, 1.0), listOf(50.0, 0.0, 0.0), Curve.linear), 0.0) *
                        Affine.scale(keyframe(p, listOf(0.0, .05, .051, 1.0), listOf(.8, .8, 0.0, 0.0), Curve.linear))
                    bite.forEach { (digit, x) -> glyph(digit, x, 2.0, 6.0, feed, RobotRole.INK, alpha) }
                }
            }
            RobotVariant.DJ -> {
                val p = cycle(t, .5, alternate = true)
                val bop = about(center, Affine.translate(0.0, keyframe(p, listOf(0.0, 1.0), listOf(0.0, 5.0), Curve.easeInOut)) *
                    Affine.rotate(keyframe(p, listOf(0.0, 1.0), listOf(-2.0, 2.0), Curve.easeInOut)))
                path(quadPath(listOf(-2.0 to 12.0, -2.0 to 8.0), listOf(Triple(-2.0 to -4.0, 12.0 to -4.0, false), Triple(26.0 to -4.0, 26.0 to 8.0, false),
                    Triple(26.0 to 12.0, 26.0 to 12.0, true))), bop, RobotRole.DARK, stroke = 3.0)
                rect(-5.0, 8.0, 5.0, 10.0, 2.0, bop, RobotRole.DARK)
                rect(24.0, 8.0, 5.0, 10.0, 2.0, bop, RobotRole.DARK)
                face(bop)
            }
            RobotVariant.WORKOUT -> {
                val half = listOf(0.0, .5, 1.0)
                val squat = about(bottom, Affine.scale(1.0, track(1.8, half, listOf(.9, 1.0, .9), Curve.easeInOut)))
                val lift = squat * Affine.translate(0.0, track(1.8, half, listOf(4.0, -8.0, 4.0), Curve.easeInOut))
                rect(-3.0, 5.0, 2.0, 7.0, .5, lift * Affine.about(-2.0, 5.0, Affine.rotate(track(1.8, half, listOf(-15.0, 0.0, -15.0), Curve.easeInOut))), RobotRole.GRAY)
                rect(25.0, 5.0, 2.0, 7.0, .5, lift * Affine.about(26.0, 5.0, Affine.rotate(track(1.8, half, listOf(15.0, 0.0, 15.0), Curve.easeInOut))), RobotRole.GRAY)
                rect(-6.0, 5.0, 36.0, 1.5, .75, lift, RobotRole.BODY)
                rect(-8.0, 0.0, 3.0, 10.0, 0.0, lift, RobotRole.BODY)
                rect(29.0, 0.0, 3.0, 10.0, 0.0, lift, RobotRole.BODY)
                body(squat)
                rect(5.5, 9.0, 5.0, 2.0, 0.0, squat, RobotRole.EYE)
                rect(13.5, 9.0, 5.0, 2.0, 0.0, squat, RobotRole.EYE)
                ellipse(23.0, 10.0, .8, 1.5, squat * Affine.translate(0.0, track(1.8, half, listOf(0.0, 0.0, 10.0))), RobotRole.GRAY, track(1.8, half, listOf(0.0, 1.0, 0.0)))
            }
            RobotVariant.PORTAL -> {
                ellipse(12.0, -4.0, 12.0, 3.0, Affine.about(12.0, -6.0, Affine.scale(track(2.0, listOf(0.0, .2, .4, 1.0), listOf(.8, 1.1, .8, .8), Curve.easeInOut))), RobotRole.BODY)
                val stops = listOf(0.0, .2, .5, .8, 1.0)
                val alpha = track(2.0, stops, listOf(0.0, 1.0, 1.0, 0.0, 0.0), Curve.easeInOut)
                if (alpha > 0) {
                    val teleport = about(center, Affine.translate(0.0, track(2.0, stops, listOf(-20.0, 0.0, 0.0, 20.0, 22.0), Curve.easeInOut)) *
                        Affine.scale(track(2.0, stops, listOf(0.0, .6, .6, 0.0, 0.0), Curve.easeInOut)) * Affine.rotate(track(2.0, stops, listOf(-90.0, 0.0, 0.0, 90.0, 0.0), Curve.easeInOut)))
                    val before = marks.size
                    face(teleport)
                    for (index in before until marks.size) marks[index] = (marks[index] as RobotMark.Shape).copy(alpha = alpha)
                }
                ellipse(12.0, 28.0, 12.0, 3.0, Affine.about(12.0, 30.0, Affine.scale(track(2.0, listOf(0.0, .6, .8, 1.0), listOf(.8, .8, 1.1, .8), Curve.easeInOut))), RobotRole.BODY)
            }
            RobotVariant.SCANNER -> {
                // The 90% box shrinks the robot to .9 of a slot unit, then it leans back under 150px perspective.
                fun tilt(point: RobotPoint): RobotPoint {
                    val x = (point.x - 12) * .9
                    val y = (point.y - 12) * .9
                    val depth = y * sin(Math.toRadians(45.0))
                    val k = 150 / (150 - depth)
                    return RobotPoint(16 + x * k, 16 + y * cos(Math.toRadians(45.0)) * k)
                }
                fun flat(x: Double, y: Double, w: Double, h: Double, r: Double, role: RobotRole) {
                    marks += RobotMark.Shape(roundedRect(x, y, w, h, r).map(::tilt), role)
                }
                flat(0.0, 0.0, 24.0, 24.0, 4.0, RobotRole.BODY)
                flat(5.0, 8.0, 5.0, 5.0, 1.5, RobotRole.EYE)
                flat(14.0, 8.0, 5.0, 5.0, 1.5, RobotRole.EYE)
                val p = cycle(t, 2.0)
                val sweep = keyframe(p, listOf(0.0, .1, .9, 1.0), listOf(0.0, 1.0, 1.0, 0.0), Curve.linear)
                val left = keyframe(p, listOf(0.0, 1.0), listOf(-SLOT, SLOT), Curve.linear)
                val strips = 8
                for (index in 0 until strips) {
                    val x = left + index * SLOT / strips
                    val glow = .5 * (1 - kotlin.math.abs((index + .5) / strips * 2 - 1))
                    marks += RobotMark.Shape(listOf(RobotPoint(x, 0.0), RobotPoint(x + SLOT / strips, 0.0), RobotPoint(x + SLOT / strips, SLOT), RobotPoint(x, SLOT)), RobotRole.EYE, glow * sweep)
                }
            }
        }
        return marks
    }

    private fun roundedRect(x: Double, y: Double, w: Double, h: Double, r: Double): List<RobotPoint> {
        if (r <= 0) return listOf(RobotPoint(x, y), RobotPoint(x + w, y), RobotPoint(x + w, y + h), RobotPoint(x, y + h))
        val corners = listOf(Triple(x + w - r, y + r, -90.0), Triple(x + w - r, y + h - r, 0.0), Triple(x + r, y + h - r, 90.0), Triple(x + r, y + r, 180.0))
        return corners.flatMap { (cx, cy, start) ->
            (0..4).map { step ->
                val angle = Math.toRadians(start + step * 22.5)
                RobotPoint(cx + r * cos(angle), cy + r * sin(angle))
            }
        }
    }

    private fun ellipsePoints(cx: Double, cy: Double, rx: Double, ry: Double): List<RobotPoint> =
        (0 until 24).map { step -> val angle = Math.PI * 2 * step / 24; RobotPoint(cx + rx * cos(angle), cy + ry * sin(angle)) }

    /** SVG M/L/Q segments flattened; each segment is (control, end, straight). */
    private fun quadPath(start: List<Pair<Double, Double>>, segments: List<Triple<Pair<Double, Double>, Pair<Double, Double>, Boolean>>): List<RobotPoint> {
        val points = start.map { RobotPoint(it.first, it.second) }.toMutableList()
        for ((control, end, straight) in segments) {
            val from = points.last()
            if (straight) { points += RobotPoint(end.first, end.second); continue }
            for (step in 1..8) {
                val u = step / 8.0
                points += RobotPoint((1 - u) * (1 - u) * from.x + 2 * u * (1 - u) * control.first + u * u * end.first,
                    (1 - u) * (1 - u) * from.y + 2 * u * (1 - u) * control.second + u * u * end.second)
            }
        }
        return points
    }
}

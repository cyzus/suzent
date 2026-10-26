package com.suzent.mobile

import kotlin.math.*

internal data class GreetingPoint(val x: Double, val y: Double)

internal data class GreetingMark(
    val points: List<GreetingPoint>,
    val color: Long,
    val alpha: Double = 1.0,
    val stroke: Boolean = false,
    val width: Double = 0.65,
)

/**
 * The empty-chat "greeting" cube, ported from the desktop web UI's
 * `GreetingCube`. Draws a floating 3-D cube (front face = Suzent logo eyes),
 * a slowly rotating sigil behind it, and a soft shadow, on a 160x160 canvas.
 *
 * `frame` is a pure, deterministic function of time so the Kotlin and Swift
 * ports stay equivalent and unit-testable.
 */
internal object GreetingCubeScene {
    private const val CX = 80.0
    private const val CUBE_HALF = 34.0
    private const val CUBE_CY = 64.0
    private const val SIGIL_CY = 76.0
    private const val SHADOW_CY = 118.0

    private val FACE_FRONT = 0xFF000000L
    private val FACE_BACK = 0xFF050505L
    private val FACE_RIGHT = 0xFF181818L
    private val FACE_LEFT = 0xFF070707L
    private val FACE_TOP = 0xFF303030L
    private val FACE_BOTTOM = 0xFF030303L
    private val EYE = 0xFFFFFFFFL
    private val EDGE = 0xFFFFFFFFL

    fun frame(seconds: Double, engaged: Boolean, reduced: Boolean, inkColor: Long): List<GreetingMark> {
        val t = if (reduced) 0.0 else max(0.0, seconds)
        val marks = mutableListOf<GreetingMark>()

        val floatY = if (reduced) 0.0 else -1.5 + 3.5 * cos(2 * PI * t / 5.4)
        val baseX = if (engaged) 27.0 else 22.0
        val turnX = if (reduced) 0.0 else 4.0 * sin(2 * PI * t / 8.0)
        val turnY = if (reduced) 0.0 else 4.0 + 10.0 * (0.5 + 0.5 * sin(2 * PI * t / 8.0 + 1.2))
        val turnZ = if (reduced) 0.0 else sin(2 * PI * t / 4.0)
        val rotX = Math.toRadians(baseX + turnX)
        val rotY = Math.toRadians(-30.0 - turnY)
        val rotZ = Math.toRadians(turnZ)

        val squint = if (engaged || reduced) 1.0 else 0.08
        val sigilAlpha = if (engaged) 0.5 else 0.1

        addSigil(marks, t, reduced, inkColor, sigilAlpha)
        addShadow(marks, t, reduced, inkColor)
        addCube(marks, rotX, rotY, rotZ, CUBE_CY + floatY, squint)
        return marks
    }

    private fun rotate(x: Double, y: Double, z: Double, rx: Double, ry: Double, rz: Double): Triple<Double, Double, Double> {
        val cy = cos(ry); val sy = sin(ry)
        val x1 = x * cy + z * sy
        val z1 = -x * sy + z * cy
        val cx = cos(rx); val sx = sin(rx)
        val y2 = y * cx - z1 * sx
        val z2 = y * sx + z1 * cx
        val cz = cos(rz); val sz = sin(rz)
        return Triple(x1 * cz - y2 * sz, x1 * sz + y2 * cz, z2)
    }

    private fun project(x: Double, y: Double, cy: Double) = GreetingPoint(CX + x, cy - y)

    private fun frontProject(u: Double, v: Double, rx: Double, ry: Double, rz: Double, cy: Double): GreetingPoint {
        val (x, y, _) = rotate(u, v, CUBE_HALF, rx, ry, rz)
        return project(x, y, cy)
    }

    private fun roundRect(cx: Double, cy: Double, w: Double, h: Double, r: Double): List<Pair<Double, Double>> {
        val left = cx - w / 2; val top = cy - h / 2; val right = cx + w / 2; val bottom = cy + h / 2
        val rad = minOf(r, w / 2, h / 2)
        val pts = mutableListOf<Pair<Double, Double>>()
        fun corner(cx0: Double, cy0: Double, a0: Double, a1: Double) {
            for (i in 0 until 4) {
                val a = a0 + (a1 - a0) * i / 4
                pts += (cx0 + rad * cos(a)) to (cy0 + rad * sin(a))
            }
        }
        pts += left + rad to top
        pts += right - rad to top
        corner(right - rad, top + rad, -PI / 2, 0.0)
        pts += right to bottom - rad
        corner(right - rad, bottom - rad, 0.0, PI / 2)
        pts += left + rad to bottom
        corner(left + rad, bottom - rad, PI / 2, PI)
        pts += left to top + rad
        corner(left + rad, top + rad, PI, 3 * PI / 2)
        return pts
    }

    private fun ellipse(cx: Double, cy: Double, rx: Double, ry: Double, steps: Int = 24): List<Pair<Double, Double>> =
        (0 until steps).map { i -> val a = 2 * PI * i / steps; (cx + rx * cos(a)) to (cy + ry * sin(a)) }

    private fun scaleP(pts: List<Pair<Double, Double>>, sx: Double, sy: Double, px: Double, py: Double): List<Pair<Double, Double>> =
        pts.map { (x, y) -> px + (x - px) * sx to py + (y - py) * sy }

    private fun rotate2(pts: List<Pair<Double, Double>>, angle: Double): List<Pair<Double, Double>> {
        val c = cos(angle); val s = sin(angle)
        return pts.map { (x, y) -> x * c - y * s to x * s + y * c }
    }

    private fun addCube(marks: MutableList<GreetingMark>, rotX: Double, rotY: Double, rotZ: Double, cy: Double, squint: Double) {
        val h = CUBE_HALF
        val verts = listOf(
            Triple(-h, -h, -h), Triple(h, -h, -h), Triple(h, h, -h), Triple(-h, h, -h),
            Triple(-h, -h, h), Triple(h, -h, h), Triple(h, h, h), Triple(-h, h, h),
        ).map { (x, y, z) -> rotate(x, y, z, rotX, rotY, rotZ) }

        fun face(indices: List<Int>, color: Long, nx: Double, ny: Double, nz: Double) {
            val (_, _, zn) = rotate(nx, ny, nz, rotX, rotY, rotZ)
            if (zn <= 0) return
            val pts = indices.map { verts[it] }.map { project(it.first, it.second, cy) }
            marks += GreetingMark(pts, color)
            marks += GreetingMark(pts, EDGE, alpha = 0.3, stroke = true, width = 0.8)
        }
        face(listOf(4, 5, 6, 7), FACE_FRONT, 0.0, 0.0, 1.0)
        face(listOf(1, 0, 3, 2), FACE_BACK, 0.0, 0.0, -1.0)
        face(listOf(1, 5, 6, 2), FACE_RIGHT, 1.0, 0.0, 0.0)
        face(listOf(0, 4, 7, 3), FACE_LEFT, -1.0, 0.0, 0.0)
        face(listOf(3, 2, 6, 7), FACE_TOP, 0.0, 1.0, 0.0)
        face(listOf(0, 1, 5, 4), FACE_BOTTOM, 0.0, -1.0, 0.0)

        fun eye(sign: Double) {
            val ex = sign * 0.375 * h
            val ey = 0.125 * h
            var pts = roundRect(ex, ey, 0.4167 * h, 0.4167 * h, 0.125 * h)
            if (squint != 1.0) pts = scaleP(pts, 1.0, squint, ex, ey)
            marks += GreetingMark(pts.map { (u, v) -> frontProject(u, v, rotX, rotY, rotZ, cy) }, EYE)
        }
        eye(-1.0)
        eye(1.0)
    }

    private fun addSigil(marks: MutableList<GreetingMark>, t: Double, reduced: Boolean, color: Long, alpha: Double) {
        val outer = if (reduced) 0.0 else 2 * PI * (t / 32.0)
        val inner = if (reduced) 0.0 else -2 * PI * (t / 24.0)
        val nodePulse = if (reduced) 0.5 else 0.28 + 0.44 * (0.5 + 0.5 * sin(2 * PI * t / 4.0))

        fun shape(points: List<Pair<Double, Double>>, angle: Double, width: Double) {
            val pts = rotate2(points, angle).map { (x, y) -> GreetingPoint(CX + x, SIGIL_CY + y) }
            marks += GreetingMark(pts, color, alpha = alpha, stroke = true, width = width)
        }

        val diamond = listOf(0.0 to -70.0, 70.0 to 0.0, 0.0 to 70.0, -70.0 to 0.0)
        val square = listOf(-50.0 to -50.0, 50.0 to -50.0, 50.0 to 50.0, -50.0 to 50.0)
        shape(diamond, outer, 0.8)
        shape(square, outer, 0.8)
        for (tick in listOf(
            listOf(0.0 to -70.0, 0.0 to -58.0),
            listOf(70.0 to 0.0, 58.0 to 0.0),
            listOf(0.0 to 70.0, 0.0 to 58.0),
            listOf(-70.0 to 0.0, -58.0 to 0.0),
        )) shape(tick, outer, 0.8)

        val tri1 = listOf(0.0 to -48.0, 42.0 to 26.0, -42.0 to 26.0)
        val tri2 = listOf(0.0 to 48.0, -42.0 to -26.0, 42.0 to -26.0)
        shape(tri1, inner, 0.7)
        shape(tri2, inner, 0.7)

        addDashedLine(marks, color, alpha, 0.0, -60.0, 0.0, 60.0)
        addDashedLine(marks, color, alpha, -60.0, 0.0, 60.0, 0.0)

        for (pos in listOf(0.0 to -72.5, 72.5 to 0.0, 0.0 to 72.5, -72.5 to 0.0)) {
            val pts = roundRect(CX + pos.first, SIGIL_CY + pos.second, 5.0, 5.0, 1.0).map { GreetingPoint(it.first, it.second) }
            marks += GreetingMark(pts, color, alpha = alpha * nodePulse)
        }
    }

    private fun addDashedLine(marks: MutableList<GreetingMark>, color: Long, alpha: Double, x1: Double, y1: Double, x2: Double, y2: Double) {
        val dx = x2 - x1; val dy = y2 - y1
        val len = sqrt(dx * dx + dy * dy)
        val ux = dx / len; val uy = dy / len
        val dash = 4.0; val gap = 14.0
        var pos = 0.0
        while (pos < len) {
            val end = min(pos + dash, len)
            marks += GreetingMark(
                listOf(GreetingPoint(CX + x1 + ux * pos, SIGIL_CY + y1 + uy * pos), GreetingPoint(CX + x1 + ux * end, SIGIL_CY + y1 + uy * end)),
                color, alpha = alpha, stroke = true, width = 0.7,
            )
            pos += dash + gap
        }
    }

    private fun addShadow(marks: MutableList<GreetingMark>, t: Double, reduced: Boolean, color: Long) {
        val a = if (reduced) 0.11 else 0.11 + 0.03 * sin(2 * PI * t / 5.4)
        val sx = if (reduced) 1.0 else 0.89 + 0.11 * cos(2 * PI * t / 5.4)
        val rx = 31.0 * sx
        marks += GreetingMark(ellipse(CX, SHADOW_CY, rx, 3.5).map { GreetingPoint(it.first, it.second) }, color, alpha = a * 0.6)
        marks += GreetingMark(ellipse(CX, SHADOW_CY, rx * 0.8, 2.8).map { GreetingPoint(it.first, it.second) }, color, alpha = a * 0.8)
    }
}

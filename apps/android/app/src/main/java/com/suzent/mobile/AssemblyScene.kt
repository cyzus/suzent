package com.suzent.mobile

import kotlin.math.*

internal data class AssemblyPoint(val x: Double, val y: Double)
internal data class AssemblyMark(val points: List<AssemblyPoint>, val color: Long, val alpha: Double = 1.0, val stroke: Boolean = false, val width: Double = 0.65)

internal object AssemblyScene {
    const val duration = 5.5
    private fun ease(value: Double): Double = value.coerceIn(0.0, 1.0).let { it * it * (3 - 2 * it) }
    private fun rotate(x: Double, y: Double, z: Double): Triple<Double, Double, Double> {
        val a = x * cos(-.48) + z * sin(-.48)
        val b = -x * sin(-.48) + z * cos(-.48)
        return Triple(a, y * cos(.32) - b * sin(.32), y * sin(.32) + b * cos(.32))
    }
    private fun random(cycle: Int, block: Int, salt: Int): Double {
        val v = sin(1729.0 + cycle * 127.1 + block * 311.7 + salt * 74.7) * 43758.5453
        return v - floor(v)
    }
    fun frame(seconds: Double, reduced: Boolean = false): List<AssemblyMark> {
        val t = if (reduced) 3.2 else seconds * 1.45
        val cycle = t % duration
        val cycleId = floor(t / duration).toInt()
        val marks = mutableListOf<AssemblyMark>()
        val advance = ease((cycle - 4.3) / 1.2) * 76
        val shell = ease((cycle - 1.5) / .28)
        val awake = ease((cycle - 2.7) / .3)
        fun project(x: Double, y: Double, z: Double, center: Double): AssemblyPoint {
            val q = rotate(x, y, z)
            return AssemblyPoint(center + q.first, 56 - q.second)
        }
        fun cube(center: Double, size: Double, offset: Triple<Double, Double, Double> = Triple(0.0, 0.0, 0.0), alpha: Double = 1.0, eyes: Double = 0.0) {
            if (alpha <= 0) return
            val vertices = listOf(
                Triple(-1,-1,-1),Triple(1,-1,-1),Triple(1,1,-1),Triple(-1,1,-1),
                Triple(-1,-1,1),Triple(1,-1,1),Triple(1,1,1),Triple(-1,1,1)
            ).map { project(it.first * size + offset.first, it.second * size + offset.second, it.third * size + offset.third, center) }
            val faces = listOf(listOf(3,2,6,7) to 51, listOf(1,5,6,2) to 25, listOf(4,7,6,5) to 9)
            faces.forEach { (indices, shade) ->
                val points = indices.map { vertices[it] }
                val color = 0xFF000000L or (shade.toLong() shl 16) or ((shade + 1).toLong() shl 8) or (shade + 2).toLong()
                marks += AssemblyMark(points, color, alpha)
                marks += AssemblyMark(points, 0xFF454749, alpha, true)
            }
            if (eyes > 0) for (x in listOf(-.43,.43)) {
                marks += AssemblyMark(listOf(x-.16 to .23-eyes/2, x+.16 to .23-eyes/2, x+.16 to .23+eyes/2, x-.16 to .23+eyes/2).map { project(it.first * size, it.second * size, 1.012 * size, center) }, 0xFFE8ECEB, alpha)
            }
        }
        fun scan(back: Boolean) {
            if (cycle <= 1.85 || cycle >= 2.7) return
            val progress = ((cycle - 1.85) / .85).coerceIn(0.0, 1.0)
            val r = 15.05
            val y = (r - .3) * (1 - 2 * progress)
            val corners = listOf(Triple(-r,y,r),Triple(r,y,r),Triple(r,y,-r),Triple(-r,y,-r)).map { project(it.first,it.second,it.third,160.0) }
            for (i in 0..3) {
                if ((i < 2) == back) continue
                val points = listOf(corners[i],corners[(i+1)%4])
                val opacity = sin(progress * PI) * if (back) .24 else .95
                if (!back) marks += AssemblyMark(points, 0xFF408DFF, opacity * .15, true, 4.0)
                marks += AssemblyMark(points, 0xFF408DFF, opacity, true, if (back) .65 else 1.15)
            }
        }
        data class Part(val offset: Triple<Double,Double,Double>, val alpha: Double)
        for (slot in -3..2) {
            val center = 160 + slot * 76 + advance
            if (center < -35 || center > 355) continue
            marks += AssemblyMark((0..23).map { val angle=it*PI/12; AssemblyPoint(center+18*cos(angle),81+2*sin(angle)) },0xFF000000,.09)
            if (slot > 0) { cube(center,14.65,eyes=.22); continue }
            if (slot == 0) scan(true)
            val parts = mutableListOf<Part>()
            for (a in -1..1) for (b in -1..1) for (c in -1..1) {
                if (slot < 0 && b != -1) continue
                val block = (a + 1) * 3 + c + 1
                val start = .4 + random(cycleId,block,0)*.28 + if (b == 1) .18+random(cycleId,block,1)*.08 else 0.0
                val length = .30 + random(cycleId,block+b*9,2)*.12
                val upper = b != -1
                val fall = ((cycle-start-.08)/length).coerceIn(0.0,1.0)
                val drop = if (upper) (1-fall*fall*fall)*(22+random(cycleId,block+b*9,3)*10) else 0.0
                val alpha = (if (upper) ease((cycle-start)/.09) else 1.0) * if (slot == 0) 1-shell else 1.0
                parts += Part(Triple(a*9.85,b*9.85+drop,c*9.85),alpha)
            }
            parts.sortedBy { rotate(it.offset.first,it.offset.second,it.offset.third).third }.forEach { cube(center,4.8,it.offset,it.alpha) }
            if (slot == 0) { cube(center,14.65,alpha=shell,eyes=.22*awake); scan(false) }
        }
        return marks
    }
}

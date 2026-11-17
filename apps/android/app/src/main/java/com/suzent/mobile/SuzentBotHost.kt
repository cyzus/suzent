package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import org.mozilla.javascript.Context
import org.mozilla.javascript.Function
import org.mozilla.javascript.Scriptable
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.acos
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/** One shared Suzent bot engine, running the same bundle desktop tests lock. */
class SuzentBotHost(script: String, seed: Int = 1) : AutoCloseable {
    private val scope: Scriptable = inContext { context ->
        context.initStandardObjects().also {
            context.evaluateString(it, script, "suzent-bot-core.js", 1, null)
        }
    }
    private val api = scope.get("SuzentBot", scope) as Scriptable
    private val functions = listOf("create", "resolveStage", "step", "destroy", "toolFrame", "destroyGlyph").associateWith {
        api.get(it, api) as Function
    }
    private val botId = lazy { create(seed, "{}") }
    private val id by botId

    fun create(seed: Int, options: String): Int = Context.toNumber(call("create", seed, options)).toInt()

    fun resolveStage(hasPending: Boolean, isError: Boolean, isThinking: Boolean, tool: String?, isActive: Boolean): String {
        val payload = JSONObject()
            .put("hasPending", hasPending)
            .put("isError", isError)
            .put("isThinking", isThinking)
            .put("isActive", isActive)
        if (tool != null) payload.put("toolName", tool)
        return Context.toString(call("resolveStage", payload.toString()))
    }

    fun toolFrame(tool: String, animation: String, seconds: Double, reduced: Boolean, instance: Int = 0): SuzentBotFrame =
        SuzentBotFrame.parse(Context.toString(call("toolFrame", tool, animation, seconds, reduced, instance)))

    fun destroyGlyph(instance: Int) {
        call("destroyGlyph", instance)
    }

    fun step(json: String): String = step(id, json)

    fun step(session: Int, json: String): String = Context.toString(call("step", session, json))

    fun destroy(session: Int) {
        call("destroy", session)
    }

    private fun call(name: String, vararg args: Any): Any? = inContext { context ->
        functions.getValue(name).call(context, scope, api, args)
    }

    // Coroutine suspension must never leave a Rhino context attached to its thread.
    private fun <T> inContext(block: (Context) -> T): T {
        val context = Context.enter()
        try {
            context.optimizationLevel = -1
            return block(context)
        } finally {
            Context.exit()
        }
    }

    override fun close() {
        if (botId.isInitialized()) destroy(id)
    }
}

/**
 * The app's one engine. Evaluating the bundle per badge cost a full script load for every icon on screen.
 * Only touch it from [botDispatcher]: Rhino scopes are not thread-safe.
 */
internal object SharedBotEngine {
    private var host: SuzentBotHost? = null
    private var nextGlyph = 1

    fun host(context: android.content.Context): SuzentBotHost = host ?: SuzentBotHost(
        context.applicationContext.assets.open("suzent-bot-core.js").bufferedReader().use { it.readText() }
    ).also { host = it }

    fun newGlyph(): Int = nextGlyph++
}

data class SuzentBotNode(
    val tag: String,
    val attrs: Map<String, String>,
    val opacity: Double,
    val children: List<SuzentBotNode>,
)

data class SuzentBotFrame(
    val viewBox: List<Double>,
    val fg: String,
    val bg: String,
    val settled: Boolean,
    val nodes: List<SuzentBotNode>,
) {
    companion object {
        fun parse(json: String): SuzentBotFrame {
            val root = JSONObject(json)
            val box = root.getString("viewBox").split(' ').map { it.toDouble() }
            return SuzentBotFrame(box, root.getString("fg"), root.getString("bg"), root.getBoolean("settled"), root.getJSONArray("nodes").nodes())
        }

        private fun JSONArray.nodes(): List<SuzentBotNode> = List(length()) { index ->
            val item = getJSONObject(index)
            val attrsJson = item.optJSONObject("attrs") ?: JSONObject()
            val attrs = attrsJson.keys().asSequence().associateWith { key -> attrsJson.getString(key) }
            SuzentBotNode(item.getString("tag"), attrs, item.optDouble("opacity", 1.0), item.getJSONArray("children").nodes())
        }
    }
}

internal data class BotAffine(
    val a: Double = 1.0,
    val b: Double = 0.0,
    val c: Double = 0.0,
    val d: Double = 1.0,
    val e: Double = 0.0,
    val f: Double = 0.0,
) {
    operator fun times(other: BotAffine) = BotAffine(
        a * other.a + c * other.b,
        b * other.a + d * other.b,
        a * other.c + c * other.d,
        b * other.c + d * other.d,
        a * other.e + c * other.f + e,
        b * other.e + d * other.f + f,
    )

    fun x(px: Double, py: Double) = a * px + c * py + e
    fun y(px: Double, py: Double) = b * px + d * py + f
}

internal fun parseSvgTransform(value: String): BotAffine {
    var matrix = BotAffine()
    TRANSFORM.findAll(value).forEach { match ->
        val nums = NUMBER.findAll(match.groupValues[2]).map { it.value.toDouble() }.toList()
        val next = when (match.groupValues[1]) {
            "translate" -> BotAffine(e = nums.getOrElse(0) { 0.0 }, f = nums.getOrElse(1) { 0.0 })
            "scale" -> BotAffine(a = nums.getOrElse(0) { 1.0 }, d = nums.getOrElse(1) { nums.getOrElse(0) { 1.0 } })
            "rotate" -> {
                val rad = nums.getOrElse(0) { 0.0 } * PI / 180.0
                val rot = BotAffine(a = cos(rad), b = sin(rad), c = -sin(rad), d = cos(rad))
                if (nums.size >= 3) BotAffine(e = nums[1], f = nums[2]) * rot * BotAffine(e = -nums[1], f = -nums[2]) else rot
            }
            "matrix" -> BotAffine(nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
            else -> BotAffine()
        }
        matrix *= next
    }
    return matrix
}

internal sealed interface SvgCmd {
    data class Move(val x: Double, val y: Double) : SvgCmd
    data class Line(val x: Double, val y: Double) : SvgCmd
    data class Cubic(val x1: Double, val y1: Double, val x2: Double, val y2: Double, val x: Double, val y: Double) : SvgCmd
    data class Close(val dummy: Boolean = true) : SvgCmd
}

internal fun parseSvgPath(d: String): List<SvgCmd> {
    val commands = mutableListOf<SvgCmd>()
    var i = 0
    var cmd = ' '
    var cx = 0.0
    var cy = 0.0
    var sx = 0.0
    var sy = 0.0
        @Suppress("UNUSED_VARIABLE") var lastCubicX = 0.0
        @Suppress("UNUSED_VARIABLE") var lastCubicY = 0.0
    fun number(): Double? {
        while (i < d.length && (d[i].isWhitespace() || d[i] == ',')) i++
        if (i >= d.length) return null
        val start = i
        if (d[i] == '+' || d[i] == '-') i++
        var dot = false
        var exp = false
        while (i < d.length) {
            val ch = d[i]
            when {
                ch.isDigit() -> i++
                ch == '.' && !dot -> { dot = true; i++ }
                (ch == 'e' || ch == 'E') && !exp -> { exp = true; dot = true; i++; if (i < d.length && (d[i] == '+' || d[i] == '-')) i++ }
                else -> break
            }
        }
        if (i == start || (i == start + 1 && !d[start].isDigit())) return null
        return d.substring(start, i).toDoubleOrNull()
    }
    while (i < d.length) {
        while (i < d.length && (d[i].isWhitespace() || d[i] == ',')) i++
        if (i >= d.length) break
        if (d[i].isLetter()) cmd = d[i++]
        val relative = cmd.isLowerCase()
        when (cmd.lowercaseChar()) {
            'm' -> {
                val x = number() ?: break
                val y = number() ?: break
                cx = if (relative) cx + x else x
                cy = if (relative) cy + y else y
                sx = cx; sy = cy
                commands += SvgCmd.Move(cx, cy)
                cmd = if (relative) 'l' else 'L'
            }
            'l' -> {
                val x = number() ?: break
                val y = number() ?: break
                cx = if (relative) cx + x else x
                cy = if (relative) cy + y else y
                commands += SvgCmd.Line(cx, cy)
            }
            'h' -> {
                val x = number() ?: break
                cx = if (relative) cx + x else x
                commands += SvgCmd.Line(cx, cy)
            }
            'v' -> {
                val y = number() ?: break
                cy = if (relative) cy + y else y
                commands += SvgCmd.Line(cx, cy)
            }
            'c' -> {
                val x1 = number() ?: break
                val y1 = number() ?: break
                val x2 = number() ?: break
                val y2 = number() ?: break
                val x = number() ?: break
                val y = number() ?: break
                val ax1 = if (relative) cx + x1 else x1
                val ay1 = if (relative) cy + y1 else y1
                val ax2 = if (relative) cx + x2 else x2
                val ay2 = if (relative) cy + y2 else y2
                cx = if (relative) cx + x else x
                cy = if (relative) cy + y else y
                lastCubicX = ax2; lastCubicY = ay2
                commands += SvgCmd.Cubic(ax1, ay1, ax2, ay2, cx, cy)
            }
            'q' -> {
                val x1 = number() ?: break
                val y1 = number() ?: break
                val x = number() ?: break
                val y = number() ?: break
                val ax1 = if (relative) cx + x1 else x1
                val ay1 = if (relative) cy + y1 else y1
                val nx = if (relative) cx + x else x
                val ny = if (relative) cy + y else y
                commands += SvgCmd.Cubic(cx + 2 * (ax1 - cx) / 3, cy + 2 * (ay1 - cy) / 3, nx + 2 * (ax1 - nx) / 3, ny + 2 * (ay1 - ny) / 3, nx, ny)
                cx = nx; cy = ny
            }
            'a' -> {
                val rx = abs(number() ?: break)
                val ry = abs(number() ?: break)
                number()
                val large = (number() ?: break) != 0.0
                val sweep = (number() ?: break) != 0.0
                val x = number() ?: break
                val y = number() ?: break
                val nx = if (relative) cx + x else x
                val ny = if (relative) cy + y else y
                sampleArc(commands, cx, cy, rx, ry, large, sweep, nx, ny)
                cx = nx; cy = ny
            }
            'z' -> {
                commands += SvgCmd.Close()
                cx = sx; cy = sy
            }
        }
        if (cmd.lowercaseChar() != 'c') { lastCubicX = cx; lastCubicY = cy }
    }
    return commands
}

private fun sampleArc(out: MutableList<SvgCmd>, x1: Double, y1: Double, rxIn: Double, ryIn: Double, large: Boolean, sweep: Boolean, x2: Double, y2: Double) {
    if (rxIn == 0.0 || ryIn == 0.0) { out += SvgCmd.Line(x2, y2); return }
    val rx = abs(rxIn)
    val ry = abs(ryIn)
    val dx = (x1 - x2) / 2
    val dy = (y1 - y2) / 2
    var rx2 = rx * rx
    var ry2 = ry * ry
    val d = dx * dx / rx2 + dy * dy / ry2
    var arx = rx
    var ary = ry
    if (d > 1) { arx *= sqrt(d); ary *= sqrt(d); rx2 = arx * arx; ry2 = ary * ary }
    val sign = if (large == sweep) -1.0 else 1.0
    val coef = sign * sqrt(maxOf(0.0, (rx2 * ry2 - rx2 * dy * dy - ry2 * dx * dx) / (rx2 * dy * dy + ry2 * dx * dx)))
    val cxp = coef * arx * dy / ary
    val cyp = coef * -ary * dx / arx
    val cx = cxp + (x1 + x2) / 2
    val cy = cyp + (y1 + y2) / 2
    fun angle(ux: Double, uy: Double, vx: Double, vy: Double): Double {
        val dot = ux * vx + uy * vy
        val len = sqrt(ux * ux + uy * uy) * sqrt(vx * vx + vy * vy)
        var ang = acos((dot / len).coerceIn(-1.0, 1.0))
        if (ux * vy - uy * vx < 0) ang = -ang
        return ang
    }
    val theta1 = angle(1.0, 0.0, (x1 - cx) / arx, (y1 - cy) / ary)
    var delta = angle((x1 - cx) / arx, (y1 - cy) / ary, (x2 - cx) / arx, (y2 - cy) / ary)
    if (!sweep && delta > 0) delta -= 2 * PI
    if (sweep && delta < 0) delta += 2 * PI
    val steps = maxOf(8, (abs(delta) / (PI / 8)).toInt())
    for (step in 1..steps) {
        val t = theta1 + delta * step / steps
        out += SvgCmd.Line(cx + arx * cos(t), cy + ary * sin(t))
    }
}

private val TRANSFORM = Regex("""(matrix|translate|scale|rotate)\s*\(([^)]*)\)""")
private val NUMBER = Regex("""[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?""")

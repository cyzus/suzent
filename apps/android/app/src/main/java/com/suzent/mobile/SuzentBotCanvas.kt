package com.suzent.mobile

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import kotlin.math.abs

private const val KAPPA = 0.5522847498307936

fun DrawScope.drawSuzentBot(frame: SuzentBotFrame, foreground: Color? = null) {
    if (frame.viewBox.size < 4) return
    val minX = frame.viewBox[0].toFloat()
    val minY = frame.viewBox[1].toFloat()
    val width = frame.viewBox[2].toFloat()
    val height = frame.viewBox[3].toFloat()
    if (width == 0f || height == 0f) return
    val fg = foreground ?: parseBotColor(frame.fg) ?: Color.Black
    val bg = parseBotColor(frame.bg) ?: Color.White
    scale(size.width / width, size.height / height, pivot = Offset.Zero) {
        translate(-minX, -minY) {
            drawNodes(frame.nodes, fg, bg, BotAffine(), 1.0, frame.nodes)
        }
    }
}

private fun DrawScope.drawNodes(
    nodes: List<SuzentBotNode>,
    fg: Color,
    bg: Color,
    matrix: BotAffine,
    opacity: Double,
    root: List<SuzentBotNode>,
) {
    for (node in nodes) {
        val next = matrix * parseSvgTransform(node.attrs["transform"].orEmpty())
        val alpha = (opacity * (node.attrs["opacity"]?.toDoubleOrNull() ?: node.opacity)).coerceIn(0.0, 1.0)
        val clipId = node.attrs["clip-path"]?.let { CLIP.find(it)?.groupValues?.get(1) }
        if (clipId != null) {
            val clip = findNode(root) { it.tag == "clipPath" && it.attrs["id"] == clipId }
            val clipPath = Path()
            clip?.children?.forEach { appendPath(clipPath, it, next) }
            clipPath(clipPath) { drawNode(node, fg, bg, next, alpha, root) }
        } else {
            drawNode(node, fg, bg, next, alpha, root)
        }
    }
}

private fun DrawScope.drawNode(
    node: SuzentBotNode,
    fg: Color,
    bg: Color,
    matrix: BotAffine,
    alpha: Double,
    root: List<SuzentBotNode>,
) {
    when (node.tag) {
        "g", "defs", "clipPath", "svg" -> drawNodes(node.children, fg, bg, matrix, alpha, root)
        "linearGradient", "stop" -> Unit
        else -> {
            val path = Path()
            appendPath(path, node, matrix)
            val fill = parseBotColor(node.attrs["fill"], fg, bg)
            val stroke = parseBotColor(node.attrs["stroke"], fg, bg)
            if (fill != null) drawPath(path, fill.copy(alpha = fill.alpha * alpha.toFloat()))
            if (stroke != null) {
                val width = node.attrs["stroke-width"]?.toFloatOrNull() ?: 1f
                val dashes = node.attrs["stroke-dasharray"]?.split(Regex("[ ,]+"))?.mapNotNull { it.toFloatOrNull() }
                val effect = dashes?.takeIf { it.isNotEmpty() }?.let {
                    // SVG repeats odd dash lists; Android requires an even number of intervals.
                    val intervals = if (it.size % 2 == 0) it else it + it
                    PathEffect.dashPathEffect(intervals.toFloatArray(), node.attrs["stroke-dashoffset"]?.toFloatOrNull() ?: 0f)
                }
                drawPath(
                    path,
                    stroke.copy(alpha = stroke.alpha * alpha.toFloat()),
                    style = Stroke(width, cap = StrokeCap.Round, pathEffect = effect),
                )
            }
        }
    }
}

private fun appendPath(path: Path, node: SuzentBotNode, matrix: BotAffine) {
    when (node.tag) {
        "path" -> parseSvgPath(node.attrs["d"].orEmpty()).forEach { path.add(it, matrix) }
        "circle" -> {
            val cx = node.attrs["cx"]?.toDoubleOrNull() ?: 0.0
            val cy = node.attrs["cy"]?.toDoubleOrNull() ?: 0.0
            val r = node.attrs["r"]?.toDoubleOrNull() ?: 0.0
            oval(path, cx, cy, r, r, matrix)
        }
        "ellipse" -> oval(
            path,
            node.attrs["cx"]?.toDoubleOrNull() ?: 0.0,
            node.attrs["cy"]?.toDoubleOrNull() ?: 0.0,
            node.attrs["rx"]?.toDoubleOrNull() ?: 0.0,
            node.attrs["ry"]?.toDoubleOrNull() ?: 0.0,
            matrix,
        )
        "rect" -> roundedRect(
            path,
            node.attrs["x"]?.toDoubleOrNull() ?: 0.0,
            node.attrs["y"]?.toDoubleOrNull() ?: 0.0,
            node.attrs["width"]?.toDoubleOrNull() ?: 0.0,
            node.attrs["height"]?.toDoubleOrNull() ?: 0.0,
            node.attrs["rx"]?.toDoubleOrNull() ?: 0.0,
            matrix,
        )
        "line" -> {
            move(path, matrix, node.attrs["x1"]?.toDoubleOrNull() ?: 0.0, node.attrs["y1"]?.toDoubleOrNull() ?: 0.0)
            line(path, matrix, node.attrs["x2"]?.toDoubleOrNull() ?: 0.0, node.attrs["y2"]?.toDoubleOrNull() ?: 0.0)
        }
        "polygon" -> {
            val points = NUMBER.findAll(node.attrs["points"].orEmpty()).map { it.value.toDouble() }.toList()
            points.chunked(2).forEachIndexed { index, pair ->
                if (pair.size < 2) return@forEachIndexed
                if (index == 0) move(path, matrix, pair[0], pair[1]) else line(path, matrix, pair[0], pair[1])
            }
            path.close()
        }
    }
}

private fun oval(path: Path, cx: Double, cy: Double, rx: Double, ry: Double, matrix: BotAffine) {
    if (rx <= 0 || ry <= 0) return
    val kx = rx * KAPPA
    val ky = ry * KAPPA
    move(path, matrix, cx + rx, cy)
    cubic(path, matrix, cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry)
    cubic(path, matrix, cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy)
    cubic(path, matrix, cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry)
    cubic(path, matrix, cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy)
    path.close()
}

private fun roundedRect(path: Path, x: Double, y: Double, w: Double, h: Double, rxIn: Double, matrix: BotAffine) {
    val rx = abs(rxIn).coerceAtMost(w / 2)
    if (rx == 0.0) {
        move(path, matrix, x, y)
        line(path, matrix, x + w, y)
        line(path, matrix, x + w, y + h)
        line(path, matrix, x, y + h)
        path.close()
        return
    }
    val kx = rx * KAPPA
    move(path, matrix, x + rx, y)
    line(path, matrix, x + w - rx, y)
    cubic(path, matrix, x + w - rx + kx, y, x + w, y + rx - kx, x + w, y + rx)
    line(path, matrix, x + w, y + h - rx)
    cubic(path, matrix, x + w, y + h - rx + kx, x + w - rx + kx, y + h, x + w - rx, y + h)
    line(path, matrix, x + rx, y + h)
    cubic(path, matrix, x + rx - kx, y + h, x, y + h - rx + kx, x, y + h - rx)
    line(path, matrix, x, y + rx)
    cubic(path, matrix, x, y + rx - kx, x + rx - kx, y, x + rx, y)
    path.close()
}

private fun Path.add(cmd: SvgCmd, matrix: BotAffine) {
    when (cmd) {
        is SvgCmd.Move -> move(this, matrix, cmd.x, cmd.y)
        is SvgCmd.Line -> line(this, matrix, cmd.x, cmd.y)
        is SvgCmd.Cubic -> cubic(this, matrix, cmd.x1, cmd.y1, cmd.x2, cmd.y2, cmd.x, cmd.y)
        is SvgCmd.Close -> close()
    }
}

private fun move(path: Path, matrix: BotAffine, x: Double, y: Double) {
    path.moveTo(matrix.x(x, y).toFloat(), matrix.y(x, y).toFloat())
}

private fun line(path: Path, matrix: BotAffine, x: Double, y: Double) {
    path.lineTo(matrix.x(x, y).toFloat(), matrix.y(x, y).toFloat())
}

private fun cubic(path: Path, matrix: BotAffine, x1: Double, y1: Double, x2: Double, y2: Double, x: Double, y: Double) {
    path.cubicTo(
        matrix.x(x1, y1).toFloat(), matrix.y(x1, y1).toFloat(),
        matrix.x(x2, y2).toFloat(), matrix.y(x2, y2).toFloat(),
        matrix.x(x, y).toFloat(), matrix.y(x, y).toFloat(),
    )
}

private fun parseBotColor(value: String?, fg: Color = Color.Black, bg: Color = Color.White): Color? {
    if (value.isNullOrBlank() || value == "none" || value.startsWith("url(")) return null
    return when {
        value == "var(--fg)" -> fg
        value == "var(--bg)" -> bg
        value.startsWith("#") -> {
            val hex = value.removePrefix("#")
            val rgb = hex.toLongOrNull(16) ?: return fg
            if (hex.length == 8) Color(rgb) else Color(0xFF000000 or rgb)
        }
        value.startsWith("hsl") -> {
            val light = NUMBER.findAll(value).map { it.value.toFloat() }.toList().getOrNull(2) ?: return fg
            val channel = (light / 100f).coerceIn(0f, 1f)
            Color(channel, channel, channel)
        }
        else -> fg
    }
}

private fun findNode(nodes: List<SuzentBotNode>, match: (SuzentBotNode) -> Boolean): SuzentBotNode? {
    for (node in nodes) {
        if (match(node)) return node
        findNode(node.children, match)?.let { return it }
    }
    return null
}

private val CLIP = Regex("""url\(#([^)]+)\)""")
private val NUMBER = Regex("""[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?""")

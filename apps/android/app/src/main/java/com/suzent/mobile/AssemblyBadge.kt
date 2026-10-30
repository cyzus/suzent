package com.suzent.mobile

import android.animation.ValueAnimator
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlin.math.min
import kotlin.random.Random
import kotlinx.coroutines.delay

@Composable
fun AssemblyBadge(thinking: Boolean, parts: List<MessagePart> = emptyList(), streaming: Boolean = false) {
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val seconds = remember { mutableDoubleStateOf(0.0) }
    var expanded by remember { mutableStateOf(false) }
    LaunchedEffect(thinking, reduced) {
        if (thinking) seconds.doubleValue = 0.0
        if (thinking && !reduced) {
            // Commit the default badge before animating its first expansion.
            withFrameNanos { }
            withFrameNanos { }
        }
        expanded = thinking
    }
    LaunchedEffect(thinking, reduced, lifecycle) {
        if (thinking && !reduced) lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            var previous = 0L
            while (true) withFrameNanos { now ->
                if (previous != 0L) seconds.doubleValue += min((now - previous) / 1_000_000_000.0, .05)
                previous = now
            }
        }
    }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val width by animateDpAsState(if (expanded) minOf(320.dp, maxWidth - 3.dp) else 90.dp,
            tween(if (reduced) 0 else 650, easing = CubicBezierEasing(.22f, 1f, .36f, 1f)), label = "badge width")
        val height by animateDpAsState(if (expanded) 108.dp else 40.dp,
            tween(if (reduced) 0 else 650, easing = CubicBezierEasing(.22f, 1f, .36f, 1f)), label = "badge height")
        val reveal by animateFloatAsState(if (expanded) 1f else 0f,
            tween(if (reduced) 0 else 350), label = "assembly reveal")
        val outline = MaterialTheme.colorScheme.outline
        val shadowColor = suzentShadow
        Box(Modifier.padding(end = PresentationTokens.shadowOffsetOverlay.dp,
            bottom = PresentationTokens.shadowOffsetOverlay.dp).drawBehind {
            val offset = PresentationTokens.shadowOffsetOverlay.dp.toPx()
            // Full-size rect offset into the reserved padding; without `size` it stayed inside the face and was painted over.
            drawRect(shadowColor, topLeft = Offset(offset, offset), size = size)
        }.size(width, height).background(MaterialTheme.colorScheme.surface)
            .border(PresentationTokens.borderWidth.dp, outline).clipToBounds(), contentAlignment = Alignment.Center) {
            if (reveal > 0f) Canvas(Modifier.fillMaxSize().padding(2.dp).graphicsLayer { alpha = reveal }) {
                val marks = AssemblyScene.frame(seconds.doubleValue, reduced)
                scale(size.width / 320f, size.height / 108f, pivot = Offset.Zero) {
                    marks.forEach { mark ->
                        val path = Path().apply {
                            mark.points.forEachIndexed { i, p -> if (i == 0) moveTo(p.x.toFloat(),p.y.toFloat()) else lineTo(p.x.toFloat(),p.y.toFloat()) }
                            if (mark.points.size > 2) close()
                        }
                        val color = Color(mark.color).copy(alpha = mark.alpha.toFloat())
                        if (mark.stroke) drawPath(path, color, style = Stroke(mark.width.toFloat())) else drawPath(path,color)
                    }
                }
            }
            Box(Modifier.graphicsLayer { alpha = 1f - reveal }.semantics { contentDescription = "Suzent" }) { RobotBadge(parts, streaming) }
        }
    }
}

private val robotDrop = Curve(.175, .885, .32, 1.275)

/**
 * Desktop's AgentBadge: a robot whose mood follows the turn. It keeps a random personality at rest, dozes off
 * after ten idle seconds, is startled for a moment by each new failure, turns skeptical while approval waits,
 * and wears a face per tool. Every change drops the new face in.
 */
@Composable
fun RobotBadge(parts: List<MessagePart>, streaming: Boolean) {
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var base by remember { mutableStateOf(robotPersonality(Random.nextDouble())) }
    val pending = parts.any { it.type == "tool" && it.state == "approval-requested" && it.output.isEmpty() }
    val errors = parts.count { it.type == "tool" && toolCallFailed(it) }
    var seenErrors by remember { mutableIntStateOf(errors) }
    var flash by remember { mutableIntStateOf(0) }
    var startled by remember { mutableStateOf(false) }
    LaunchedEffect(errors) {
        if (errors > seenErrors) flash++
        seenErrors = errors
    }
    // Keyed on the flash alone: a count that drops when parts reconcile must not cancel the reset and leave it shaking.
    LaunchedEffect(flash) {
        if (flash == 0) return@LaunchedEffect
        startled = true
        delay(2600)
        startled = false
    }
    LaunchedEffect(streaming, pending, base) {
        if (streaming || pending) { if (base == RobotVariant.SNOOZER) base = RobotVariant.IDLE }
        else if (base == RobotVariant.IDLE) { delay(10_000); base = RobotVariant.SNOOZER }
    }
    val variant = robotBadgeVariant(base, startled, pending, streaming, robotCurrentTool(parts))
    var seconds by remember { mutableDoubleStateOf(0.0) }
    LaunchedEffect(reduced, lifecycle) {
        if (!reduced) lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            var previous = 0L
            while (true) withFrameNanos { now ->
                if (previous != 0L) seconds += ((now - previous) / 1_000_000_000.0).coerceAtMost(.05)
                previous = now
            }
        }
    }
    val drop = remember { Animatable(1f) }
    LaunchedEffect(variant, reduced) {
        if (reduced) return@LaunchedEffect
        drop.snapTo(0f)
        drop.animateTo(1f, tween(300, easing = LinearEasing))
    }
    val ink = MaterialTheme.colorScheme.onSurface
    val bold = remember { android.graphics.Typeface.create(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD) }
    Canvas(Modifier.size(32.dp).graphicsLayer {
        val p = drop.value.toDouble()
        val stops = doubleArrayOf(0.0, .5, 1.0)
        translationY = keyframe(p, stops, doubleArrayOf(15.0, -3.0, 0.0), robotDrop).dp.toPx()
        scaleX = keyframe(p, stops, doubleArrayOf(.5, 1.05, 1.0), robotDrop).toFloat(); scaleY = scaleX
        alpha = keyframe(p, stops, doubleArrayOf(0.0, 1.0, 1.0), robotDrop).toFloat().coerceIn(0f, 1f)
    }.then(if (RobotScene.clips(variant)) Modifier.clipToBounds() else Modifier)) {
        fun color(role: RobotRole) = when (role) {
            RobotRole.BODY -> Color.Black
            RobotRole.EYE -> Color.White
            RobotRole.INK -> ink
            RobotRole.GRAY -> Color(0xFF666666)
            RobotRole.DARK -> Color(0xFF262626)
        }
        scale(size.width / RobotScene.SLOT.toFloat(), size.height / RobotScene.SLOT.toFloat(), pivot = Offset.Zero) {
            RobotScene.frame(variant, seconds, reduced).forEach { mark ->
                when (mark) {
                    is RobotMark.Shape -> {
                        val path = Path().apply {
                            mark.points.forEachIndexed { i, p -> if (i == 0) moveTo(p.x.toFloat(), p.y.toFloat()) else lineTo(p.x.toFloat(), p.y.toFloat()) }
                            if (mark.stroke == 0.0) close()
                        }
                        if (mark.stroke > 0) drawPath(path, color(mark.role), mark.alpha.toFloat(), Stroke(mark.stroke.toFloat(), cap = StrokeCap.Round))
                        else drawPath(path, color(mark.role), mark.alpha.toFloat())
                    }
                    is RobotMark.Glyph -> drawIntoCanvas { canvas ->
                        val native = canvas.nativeCanvas
                        native.save()
                        native.concat(android.graphics.Matrix().apply {
                            setValues(floatArrayOf(mark.matrix.a.toFloat(), mark.matrix.c.toFloat(), mark.matrix.e.toFloat(),
                                mark.matrix.b.toFloat(), mark.matrix.d.toFloat(), mark.matrix.f.toFloat(), 0f, 0f, 1f))
                        })
                        native.drawText(mark.text, mark.x.toFloat(), mark.y.toFloat(), android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                            this.color = color(mark.role).copy(alpha = color(mark.role).alpha * mark.alpha.toFloat()).toArgb()
                            textSize = mark.size.toFloat()
                            typeface = bold
                        })
                        native.restore()
                    }
                }
            }
        }
    }
}

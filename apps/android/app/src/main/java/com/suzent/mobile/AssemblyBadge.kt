package com.suzent.mobile

import android.animation.ValueAnimator
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.ui.platform.LocalContext
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
        if (thinking) lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
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
 * Desktop's Suzent bot: the same stage resolver and scene the desktop mark draws, capped at 30fps and
 * paused while animations are disabled or the screen is in the background.
 */
@Composable
fun RobotBadge(parts: List<MessagePart>, streaming: Boolean) {
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val dark = isSystemInDarkTheme()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val context = LocalContext.current
    val host = remember {
        SuzentBotHost(context.assets.open("suzent-bot-core.js").bufferedReader().use { it.readText() })
    }
    DisposableEffect(host) { onDispose { host.close() } }
    val pending = parts.any { it.type == "tool" && it.state == "approval-requested" && it.output.isEmpty() }
    val errors = parts.count { it.type == "tool" && toolCallFailed(it) }
    var seenErrors by remember { mutableIntStateOf(errors) }
    var flash by remember { mutableIntStateOf(0) }
    var startled by remember { mutableStateOf(false) }
    LaunchedEffect(errors) {
        if (errors > seenErrors) flash++
        seenErrors = errors
    }
    LaunchedEffect(flash) {
        if (flash == 0) return@LaunchedEffect
        startled = true
        delay(2600)
        startled = false
    }
    val tool = robotCurrentTool(parts)
    val stage = host.resolveStage(pending, startled, streaming && tool == null, tool, streaming || pending)
    var timeMs by remember { mutableDoubleStateOf(0.0) }
    var frame by remember { mutableStateOf(host.step("""{"stage":"idle","time":0,"reducedMotion":true,"size":32}""").let(SuzentBotFrame::parse)) }
    LaunchedEffect(reduced, dark, stage, lifecycle) {
        frame = SuzentBotFrame.parse(host.step(botStep(stage, timeMs, reduced, dark)))
        if (reduced) return@LaunchedEffect
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            var previous = 0L
            var accumulator = 0.0
            while (true) withFrameNanos { now ->
                if (previous != 0L) {
                    accumulator += ((now - previous) / 1_000_000_000.0).coerceAtMost(0.05)
                    if (accumulator >= 1.0 / 30.0) {
                        timeMs += accumulator * 1000.0
                        accumulator = 0.0
                        frame = SuzentBotFrame.parse(host.step(botStep(stage, timeMs, false, dark)))
                    }
                }
                previous = now
            }
        }
    }
    val drop = remember { Animatable(1f) }
    LaunchedEffect(stage, reduced) {
        if (reduced) return@LaunchedEffect
        drop.snapTo(0f)
        drop.animateTo(1f, tween(300, easing = LinearEasing))
    }
    Canvas(Modifier.size(32.dp).graphicsLayer {
        val progress = drop.value.toDouble()
        val stops = doubleArrayOf(0.0, .5, 1.0)
        translationY = keyframe(progress, stops, doubleArrayOf(15.0, -3.0, 0.0), robotDrop).dp.toPx()
        scaleX = keyframe(progress, stops, doubleArrayOf(.5, 1.05, 1.0), robotDrop).toFloat()
        scaleY = scaleX
        alpha = keyframe(progress, stops, doubleArrayOf(0.0, 1.0, 1.0), robotDrop).toFloat().coerceIn(0f, 1f)
    }) { drawSuzentBot(frame) }
}

private fun botStep(stage: String, timeMs: Double, reduced: Boolean, dark: Boolean) =
    """{"stage":"$stage","time":$timeMs,"reducedMotion":$reduced,"dark":$dark,"size":32,"holdWhenIdle":true,"particlesEnabled":${!reduced},"autoMorphCycle":${!reduced},"isActive":true}"""

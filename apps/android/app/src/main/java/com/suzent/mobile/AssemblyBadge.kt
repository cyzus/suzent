package com.suzent.mobile

import android.animation.ValueAnimator
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.ui.platform.LocalContext
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlin.math.min
import kotlinx.coroutines.delay
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.withContext
import java.util.concurrent.Executors

@Composable
fun AssemblyBadge(thinking: Boolean, parts: List<MessagePart> = emptyList(), streaming: Boolean = false) {
    if (!thinking) { RobotBadge(parts, streaming); return }
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val seconds = remember { mutableDoubleStateOf(0.0) }
    LaunchedEffect(reduced, lifecycle) {
        if (!reduced) lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            var previous = 0L
            while (true) withFrameNanos { now ->
                if (previous != 0L) seconds.doubleValue += min((now - previous) / 1_000_000_000.0, .05)
                previous = now
            }
        }
    }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val outline = MaterialTheme.colorScheme.outline
        val shadowColor = suzentShadow
        Box(Modifier.padding(end = PresentationTokens.shadowOffsetOverlay.dp,
            bottom = PresentationTokens.shadowOffsetOverlay.dp).drawBehind {
            val offset = PresentationTokens.shadowOffsetOverlay.dp.toPx()
            // Full-size rect offset into the reserved padding; without `size` it stayed inside the face and was painted over.
            drawRect(shadowColor, topLeft = Offset(offset, offset), size = size)
        }.size(minOf(320.dp, maxWidth - 3.dp), 108.dp).background(MaterialTheme.colorScheme.surface)
            .border(PresentationTokens.borderWidth.dp, outline).clipToBounds()
            .semantics { contentDescription = "Suzent" }) {
            Canvas(Modifier.fillMaxSize().padding(2.dp)) {
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
        }
    }
}

/**
 * Desktop's Suzent bot: the same stage resolver and scene the desktop mark draws, computed off the UI thread,
 * capped at 30fps, and stopped once the scene settles, animations are disabled or the screen is in the background.
 */
@Composable
fun RobotBadge(parts: List<MessagePart>, streaming: Boolean, visible: Boolean = true, toolOverride: String? = null) {
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val dark = isSystemInDarkTheme()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val context = LocalContext.current
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
    val tool = toolOverride ?: robotCurrentTool(parts, streaming)
    val input by rememberUpdatedState(BotInput(pending, startled, streaming, tool, reduced, dark, visible))
    val frame = remember { mutableStateOf<SuzentBotFrame?>(null) }
    LaunchedEffect(context, lifecycle) {
        withContext(botDispatcher) {
            val host = SharedBotEngine.host(context)
            val session = host.create(1, "{}")
            try {
                var timeMs = 0.0
                lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
                    snapshotFlow { input }.collectLatest { current ->
                        if (!current.visible) return@collectLatest
                        val stage = host.resolveStage(current.pending, current.startled,
                            current.streaming && current.tool == null, current.tool, current.streaming || current.pending)
                        var previous = System.nanoTime()
                        while (true) {
                            val now = System.nanoTime()
                            timeMs += ((now - previous) / 1_000_000.0).coerceAtMost(50.0)
                            previous = now
                            val next = SuzentBotFrame.parse(host.step(session, botStep(stage, timeMs, current.reduced, current.dark)))
                            frame.value = next
                            if (current.reduced || next.settled) break
                            // Backpressure: never queue frames when computation exceeds the budget.
                            val remaining = 33_333_334L - (System.nanoTime() - now)
                            delay((remaining / 1_000_000L).coerceAtLeast(1))
                        }
                    }
                }
            } finally {
                host.destroy(session)
            }
        }
    }
    Canvas(Modifier.size(32.dp)) { frame.value?.let { drawSuzentBot(it) } }
}

private fun botStep(stage: String, timeMs: Double, reduced: Boolean, dark: Boolean) =
    """{"stage":"$stage","time":$timeMs,"reducedMotion":$reduced,"dark":$dark,"size":32,"holdWhenIdle":true,"particlesEnabled":${!reduced},"autoMorphCycle":${!reduced},"isActive":true}"""

private data class BotInput(
    val pending: Boolean,
    val startled: Boolean,
    val streaming: Boolean,
    val tool: String?,
    val reduced: Boolean,
    val dark: Boolean,
    val visible: Boolean,
)

// One serial worker keeps JS scopes confined without allocating a thread per badge.
internal val botDispatcher = Executors.newSingleThreadExecutor { task ->
    Thread(task, "SuzentBot").apply { isDaemon = true }
}.asCoroutineDispatcher()

package com.suzent.mobile

import android.animation.ValueAnimator
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlin.math.sin

private val crownEasing = CubicBezierEasing(.22f, 1f, .36f, 1f)
private val glintEasing = CubicBezierEasing(0f, 0f, .58f, 1f)
private val headStops = floatArrayOf(0f, .26f, .58f, .8f, 1f)
private val crownStops = floatArrayOf(0f, .28f, .58f, .8f, 1f)
private const val CROWN_MS = 620f
private const val GLINT_DELAY_MS = 220f
private const val GLINT_MS = 650f

private fun keyframe(progress: Float, stops: FloatArray, values: FloatArray): Float {
    val next = (1 until stops.size).firstOrNull { progress <= stops[it] } ?: return values.last()
    val local = (progress - stops[next - 1]) / (stops[next] - stops[next - 1])
    return values[next - 1] + (values[next] - values[next - 1]) * crownEasing.transform(local)
}

/** Desktop's sidebar coronation (regentMark*Crown in styles.css), in this mark's 24×36 units. */
private data class CrownPose(val headY: Float = 0f, val headScaleX: Float = 1f, val headScaleY: Float = 1f,
                             val eyesY: Float = 0f, val eyesScaleY: Float = 1f, val crownAlpha: Float = 1f, val crownY: Float = 0f,
                             val crownScaleX: Float = 1f, val crownScaleY: Float = 1f, val crownRotation: Float = 0f, val glint: Float = 0f) {
    fun toward(target: CrownPose, amount: Float): CrownPose {
        fun mix(from: Float, to: Float) = from + (to - from) * amount
        return CrownPose(mix(headY, target.headY), mix(headScaleX, target.headScaleX), mix(headScaleY, target.headScaleY),
            mix(eyesY, target.eyesY), mix(eyesScaleY, target.eyesScaleY), mix(crownAlpha, target.crownAlpha), mix(crownY, target.crownY),
            mix(crownScaleX, target.crownScaleX), mix(crownScaleY, target.crownScaleY), mix(crownRotation, target.crownRotation), mix(glint, target.glint))
    }

    companion object {
        // This mark's circlet floats 1 unit higher above the head than desktop's, so it travels 1 unit further.
        val rest = CrownPose(headY = -1f, crownAlpha = 0f, crownY = -5f, crownScaleX = .72f, crownScaleY = .72f, crownRotation = -10f)

        fun at(elapsedMs: Float, eyes: Boolean): CrownPose {
            val p = (elapsedMs / CROWN_MS).coerceIn(0f, 1f)
            val g = ((elapsedMs - GLINT_DELAY_MS) / GLINT_MS).coerceIn(0f, 1f)
            return CrownPose(
                headY = keyframe(p, headStops, floatArrayOf(-1f, -2.4f, 1.4f, -.2f, .4f)),
                headScaleX = keyframe(p, headStops, floatArrayOf(1f, .95f, .89f, .85f, .86f)),
                headScaleY = keyframe(p, headStops, floatArrayOf(1f, 1.03f, .81f, .87f, .86f)),
                eyesY = if (eyes) keyframe(p, crownStops, floatArrayOf(0f, -2.2f, .6f, -.5f, 0f)) else 0f,
                eyesScaleY = if (eyes) keyframe(p, crownStops, floatArrayOf(1f, 1.08f, .22f, 1.04f, 1f)) else 1f,
                crownAlpha = keyframe(p, crownStops, floatArrayOf(0f, 1f, 1f, 1f, 1f)),
                crownY = keyframe(p, crownStops, floatArrayOf(-6f, 1.4f, 7.1f, 5f, 5.7f)),
                crownScaleX = keyframe(p, crownStops, floatArrayOf(.72f, .92f, .92f, .88f, .88f)),
                crownScaleY = keyframe(p, crownStops, floatArrayOf(.72f, .92f, .85f, .88f, .88f)),
                crownRotation = keyframe(p, crownStops, floatArrayOf(-12f, 5f, -1.5f, .6f, 0f)),
                glint = if (g < .45f) glintEasing.transform(g / .45f) else 1f - glintEasing.transform((g - .45f) / .55f))
        }
    }
}

/**
 * [coronation] null keeps the circlet on. Otherwise the mark rests as the plain Suzent head, like the
 * desktop sidebar row, and true plays desktop's hover coronation (a phone has no hover, so callers pass the press).
 */
@Composable
fun RegentMark(working: Boolean = false, waiting: Boolean = false, size: Dp = 32.dp, lastMessageAt: String? = null, coronation: Boolean? = null) {
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var seconds by remember { mutableDoubleStateOf(0.0) }
    val nod = remember { androidx.compose.animation.core.Animatable(0f) }
    val crownElapsed = remember { androidx.compose.animation.core.Animatable(0f) }
    val crownBlend = remember { androidx.compose.animation.core.Animatable(0f) }
    var previousMessage by remember { mutableStateOf(lastMessageAt) }
    LaunchedEffect(lastMessageAt, reduced) {
        val changed = previousMessage != null && lastMessageAt != null && previousMessage != lastMessageAt
        previousMessage = lastMessageAt
        if (changed && !reduced) {
            nod.animateTo(-7f, androidx.compose.animation.core.tween(180))
            nod.animateTo(0f, androidx.compose.animation.core.tween(240))
        }
    }
    LaunchedEffect(coronation, reduced) {
        val end = GLINT_DELAY_MS + GLINT_MS
        if (coronation == true) {
            crownBlend.snapTo(1f)
            if (reduced) crownElapsed.snapTo(end)
            else { crownElapsed.snapTo(0f); crownElapsed.animateTo(end, androidx.compose.animation.core.tween(end.toInt(), easing = LinearEasing)) }
        } else if (coronation == false) {
            if (reduced) crownBlend.snapTo(0f) else crownBlend.animateTo(0f, androidx.compose.animation.core.tween(260, easing = LinearOutSlowInEasing))
            crownElapsed.snapTo(0f)
        }
    }
    LaunchedEffect(working, waiting, reduced, lifecycle) {
        if (!reduced && (working || waiting)) lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            var previous = 0L
            while (true) withFrameNanos { now ->
                if (previous != 0L) seconds += ((now - previous) / 1_000_000_000.0).coerceAtMost(.05)
                previous = now
            }
        }
    }
    val ink = MaterialTheme.colorScheme.onSurface
    val eyes = MaterialTheme.colorScheme.background
    val glintColor = Color(PresentationTokens.yellow)
    Canvas(Modifier.size(size, size * 1.5f).graphicsLayer {
        rotationY = if (working && !reduced) (sin(seconds * 1.4) * 12).toFloat() else 0f
        rotationZ = nod.value
    }) {
        val t = if (reduced) 0.0 else seconds
        val pose = if (coronation == null) CrownPose()
            else CrownPose.rest.toward(CrownPose.at(crownElapsed.value, eyes = !working), crownBlend.value)
        val lift = if (working && !reduced) (1 + sin(t * 2)).toFloat() * pose.crownAlpha else 0f
        val scan = if (working && !reduced) (sin(t * 2) * 1.2).toFloat() else 0f
        scale(this.size.width / 24, this.size.height / 36, pivot = Offset.Zero) {
            withTransform({ translate(0f, pose.headY); scale(pose.headScaleX, pose.headScaleY, Offset(12f, 36f)) }) {
                drawRoundRect(ink, Offset(0f, 12f), Size(24f, 24f), CornerRadius(4f))
                withTransform({ translate(0f, pose.eyesY); scale(1f, pose.eyesScaleY, Offset(12f, 22.5f)) }) {
                    listOf(5f, 14f).forEach { x -> drawRoundRect(eyes, Offset(x + scan, 20f), Size(5f, 5f), CornerRadius(1.5f)) }
                }
            }
            if (pose.crownAlpha > 0f) withTransform({
                translate(0f, pose.crownY - lift)
                scale(pose.crownScaleX, pose.crownScaleY, Offset(12f, 9.8f))
                rotate(pose.crownRotation, Offset(12f, 9.8f))
            }) {
                drawPath(Path().apply {
                    moveTo(3f, 5f); quadraticTo(12f, 1.4f, 21f, 5f)
                    lineTo(21f, 8f); quadraticTo(12f, 11.6f, 3f, 8f); close()
                }, ink, alpha = pose.crownAlpha)
                val pulse = if (waiting && !working && !reduced) (.75 + .25 * sin(t * 3)).toFloat() else 1f
                val gem = Path().apply { moveTo(12f, 5f); lineTo(14.4f, 7.4f); lineTo(12f, 9.8f); lineTo(9.6f, 7.4f); close() }
                drawPath(gem, if (waiting && !working) Color(0xFFF59E0B) else eyes, alpha = pulse * pose.crownAlpha)
                if (!waiting && pose.glint > 0f) drawPath(gem, glintColor, alpha = pose.glint * pose.crownAlpha)
            }
        }
    }
}

@Composable
fun RegentIdentity(working: Boolean = false, waiting: Int = 0, unread: Int = 0, lastMessageAt: String? = null,
                   expanded: Boolean = false, showStatus: Boolean = true, coronation: Boolean? = null) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        RegentMark(working, waiting > 0, if (expanded) 44.dp else 24.dp, lastMessageAt, coronation)
        Column(Modifier.weight(1f, fill = false), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(stringResource(R.string.regent_name), fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            if (showStatus) Text(stringResource(if (working) R.string.regent_working else if (waiting > 0) R.string.regent_waiting else R.string.regent_scope),
                fontSize = PresentationTokens.typeLabel.sp, color = if (waiting > 0 && !working) Color(0xFFF59E0B) else MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (unread > 0) {
            val label = stringResource(R.string.regent_unread, unread)
            Text("$unread", fontSize = PresentationTokens.typeLabel.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.background(suzentSelection).padding(6.dp).semantics { contentDescription = label })
        }
    }
}

@Composable
fun RegentGreeting() {
    Column(Modifier.fillMaxWidth().padding(vertical = 36.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        RegentMark(size = 64.dp)
        Text(stringResource(R.string.regent_name), fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text(stringResource(R.string.regent_greeting), textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

package com.suzent.mobile

import android.animation.ValueAnimator
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
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
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlin.math.min

@Composable
fun AssemblyBadge(thinking: Boolean) {
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
        Box(Modifier.padding(end = 3.dp, bottom = 3.dp).drawBehind {
            drawRect(shadowColor, topLeft = Offset(3.dp.toPx(), 3.dp.toPx()))
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
            Image(painterResource(R.drawable.suzent_logo), contentDescription = "Suzent",
                modifier = Modifier.size(26.dp).graphicsLayer { alpha = 1f - reveal })
        }
    }
}

package com.suzent.mobile

import android.animation.ValueAnimator
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
import androidx.compose.ui.graphics.drawscope.scale
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

@Composable
fun RegentMark(working: Boolean = false, waiting: Boolean = false, size: Dp = 32.dp, lastMessageAt: String? = null) {
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var seconds by remember { mutableDoubleStateOf(0.0) }
    val nod = remember { androidx.compose.animation.core.Animatable(0f) }
    var previousMessage by remember { mutableStateOf(lastMessageAt) }
    LaunchedEffect(lastMessageAt, reduced) {
        val changed = previousMessage != null && lastMessageAt != null && previousMessage != lastMessageAt
        previousMessage = lastMessageAt
        if (changed && !reduced) {
            nod.animateTo(-7f, androidx.compose.animation.core.tween(180))
            nod.animateTo(0f, androidx.compose.animation.core.tween(240))
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
    Canvas(Modifier.size(size, size * 1.5f).graphicsLayer {
        rotationY = if (working && !reduced) (sin(seconds * 1.4) * 12).toFloat() else 0f
        rotationZ = nod.value
    }) {
        val t = if (reduced) 0.0 else seconds
        val lift = if (working && !reduced) (1 + sin(t * 2)).toFloat() else 0f
        val scan = if (working && !reduced) (sin(t * 2) * 1.2).toFloat() else 0f
        scale(this.size.width / 24, this.size.height / 36, pivot = Offset.Zero) {
            drawRoundRect(ink, Offset(0f, 12f), Size(24f, 24f), CornerRadius(4f))
            listOf(5f, 14f).forEach { x -> drawRoundRect(eyes, Offset(x + scan, 20f), Size(5f, 5f), CornerRadius(1.5f)) }
            drawPath(Path().apply {
                moveTo(3f, 5f - lift); quadraticTo(12f, 1.4f - lift, 21f, 5f - lift)
                lineTo(21f, 8f - lift); quadraticTo(12f, 11.6f - lift, 3f, 8f - lift); close()
            }, ink)
            val pulse = if (waiting && !working && !reduced) (.75 + .25 * sin(t * 3)).toFloat() else 1f
            drawPath(Path().apply {
                moveTo(12f, 5f - lift); lineTo(14.4f, 7.4f - lift); lineTo(12f, 9.8f - lift); lineTo(9.6f, 7.4f - lift); close()
            }, (if (waiting && !working) Color(0xFFF59E0B) else eyes).copy(alpha = pulse))
        }
    }
}

@Composable
fun RegentIdentity(working: Boolean = false, waiting: Int = 0, unread: Int = 0, lastMessageAt: String? = null,
                   expanded: Boolean = false, showStatus: Boolean = true) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        RegentMark(working, waiting > 0, if (expanded) 44.dp else 24.dp, lastMessageAt)
        Column(Modifier.weight(1f, fill = false), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(stringResource(R.string.regent_name), fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            if (showStatus) Text(stringResource(if (working) R.string.regent_working else if (waiting > 0) R.string.regent_waiting else R.string.regent_scope),
                fontSize = 12.sp, color = if (waiting > 0 && !working) Color(0xFFF59E0B) else MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (unread > 0) {
            val label = stringResource(R.string.regent_unread, unread)
            Text("$unread", fontSize = 12.sp, fontWeight = FontWeight.Bold,
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

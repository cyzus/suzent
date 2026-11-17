package com.suzent.mobile

import android.animation.ValueAnimator
import androidx.compose.animation.core.animate
import androidx.compose.animation.core.spring
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import kotlin.math.abs

/**
 * Row swipe that loses to vertical scrolling.
 *
 * The finger must travel [SwipeAxisLock.MIN_TRAVEL] dp and stay inside the horizontal cone
 * before the row moves. Once the lock is vertical, or a child has already consumed the drag,
 * the gesture is abandoned and the list keeps scrolling.
 */
@Composable
fun SuzentSwipeRow(
    enableLeading: Boolean,
    enableTrailing: Boolean,
    leadingColor: Color,
    trailingColor: Color,
    onLeading: () -> Unit,
    onTrailing: () -> Unit,
    modifier: Modifier = Modifier,
    leading: @Composable BoxScope.() -> Unit,
    trailing: @Composable BoxScope.() -> Unit,
    content: @Composable () -> Unit,
) {
    var shift by remember { mutableFloatStateOf(0f) }
    val scope = rememberCoroutineScope()
    val settle = remember { mutableStateOf<Job?>(null) }
    val density = LocalDensity.current
    val rtl = LocalLayoutDirection.current == LayoutDirection.Rtl
    val view = LocalView.current
    val leadingAction by rememberUpdatedState(onLeading)
    val trailingAction by rememberUpdatedState(onTrailing)
    val pxPerDp = with(density) { 1.dp.toPx() }
    val triggerPx = SwipeAxisLock.TRIGGER.toFloat() * pxPerDp
    val maxPx = 120.dp.value * pxPerDp
    Box(modifier.fillMaxWidth().clipToBounds()) {
        if (shift != 0f) {
            Box(
                Modifier.matchParentSize().background(if (shift > 0f) leadingColor else trailingColor),
                contentAlignment = if (shift > 0f) Alignment.CenterStart else Alignment.CenterEnd,
            ) {
                Box(Modifier.padding(horizontal = 20.dp), content = if (shift > 0f) leading else trailing)
            }
        }
        Box(
            Modifier.fillMaxWidth()
                .graphicsLayer { translationX = if (rtl) -shift else shift }
                .pointerInput(enableLeading, enableTrailing, rtl) {
                    if (!enableLeading && !enableTrailing) return@pointerInput
                    fun close() {
                        val from = shift
                        if (from == 0f) return
                        val motion = ValueAnimator.areAnimatorsEnabled()
                        settle.value = scope.launch {
                            if (motion) animate(from, 0f, animationSpec = spring()) { value, _ -> shift = value }
                            else shift = 0f
                        }
                    }
                    val min = if (enableTrailing) -maxPx else 0f
                    val max = if (enableLeading) maxPx else 0f
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        settle.value?.cancel()
                        val lock = SwipeAxisLock()
                        var claimed = false
                        var armed = false
                        var velocity = 0f
                        var lastTime = down.uptimeMillis
                        while (true) {
                            val event = awaitPointerEvent()
                            val change = event.changes.firstOrNull { it.id == down.id } ?: break
                            if (!change.pressed) break
                            val total = change.position - down.position
                            val logicalX = if (rtl) -total.x else total.x
                            if (change.isConsumed && lock.axis != SwipeAxisLock.Axis.HORIZONTAL) lock.noteVerticalScroll()
                            when (lock.update((logicalX / pxPerDp).toDouble(), (total.y / pxPerDp).toDouble())) {
                                SwipeAxisLock.Axis.UNDECIDED -> Unit
                                SwipeAxisLock.Axis.VERTICAL -> {
                                    close()
                                    return@awaitEachGesture
                                }
                                SwipeAxisLock.Axis.HORIZONTAL -> {
                                    claimed = true
                                    change.consume()
                                    val next = logicalX.coerceIn(min, max)
                                    shift = next
                                    val elapsed = (change.uptimeMillis - lastTime).coerceAtLeast(1)
                                    val step = if (rtl) -change.positionChange().x else change.positionChange().x
                                    velocity = step / elapsed * 1000f
                                    lastTime = change.uptimeMillis
                                    val past = abs(next) >= triggerPx
                                    if (past && !armed) {
                                        armed = true
                                        view.suzentHaptic(SuzentHaptic.Light)
                                    } else if (!past) armed = false
                                }
                            }
                        }
                        if (!claimed) {
                            close()
                            return@awaitEachGesture
                        }
                        val end = shift
                        val commit = SwipeAxisLock.commits((end / pxPerDp).toDouble(), (velocity / pxPerDp).toDouble())
                        if (commit && end > 0f) leadingAction()
                        else if (commit && end < 0f) trailingAction()
                        close()
                    }
                },
        ) { content() }
    }
}

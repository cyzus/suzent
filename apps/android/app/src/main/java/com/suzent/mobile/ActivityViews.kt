package com.suzent.mobile

import android.animation.ValueAnimator
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlin.math.sin

@Composable
fun ActivityTurn(parts: List<MessagePart>, live: Boolean = false, regent: Boolean = false, compact: Boolean = false,
                 workedSeconds: Int? = null, citationSources: List<CitationSource> = emptyList()) {
    var expanded by remember { mutableStateOf(false) }
    LaunchedEffect(live) { if (!live) expanded = false }
    val start = activityFinalStart(parts)
    val work = parts.take(start).filterNot { it.regentBubble }
    val persistent = parts.take(start).filter { it.regentBubble }
    val pending = work.any { it.state == "approval-requested" && it.output.isEmpty() }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.weight(1f, fill = false)) {
                if (regent) RegentIdentity(working = live, showStatus = false)
                else if (live) AssemblyBadge(thinking = showAssemblyBadge(parts, live))
                else SuzentAssistantBadge(compact = compact)
            }
            if (!live && work.isNotEmpty()) {
                val visible = expanded || pending
                val label = stringResource(if (visible) R.string.reminder_expanded else R.string.reminder_collapsed)
                SuzentTextButton(onClick = { expanded = !expanded }, modifier = Modifier.semantics { stateDescription = label }, contentPadding = PaddingValues(0.dp)) {
                    Text(if (workedSeconds != null) stringResource(R.string.activity_worked_for, activityDuration(workedSeconds)) else stringResource(R.string.activity_label),
                        fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    ActivityChevron(visible)
                }
            }
        }
        if (live) ActivityContent(parts, true, citationSources, regent)
        else {
            ActivityDisclosure(expanded || pending) { ActivityContent(work, false, citationSources, regent) }
            ActivityContent(persistent + parts.drop(start), false, citationSources, regent)
        }
    }
}

@Composable
private fun ActivityDisclosure(visible: Boolean, content: @Composable () -> Unit) {
    val duration = if (ValueAnimator.areAnimatorsEnabled()) 200 else 0
    AnimatedVisibility(visible, enter = expandVertically(tween(duration), expandFrom = Alignment.Top) + fadeIn(tween(duration)),
        exit = shrinkVertically(tween(duration), shrinkTowards = Alignment.Top) + fadeOut(tween(duration))) { content() }
}

@Composable
private fun ActivityChevron(expanded: Boolean) {
    val rotation by animateFloatAsState(if (expanded) 90f else 0f, tween(if (ValueAnimator.areAnimatorsEnabled()) 150 else 0), label = "activity disclosure")
    Text("›", modifier = Modifier.padding(start = 6.dp).graphicsLayer { rotationZ = rotation }, fontSize = 16.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
fun ActivityRail(parts: List<MessagePart>, live: Boolean, current: Boolean) {
    var userExpanded by remember { mutableStateOf<Boolean?>(null) }
    val waiting = parts.any { it.state == "approval-requested" && it.output.isEmpty() }
    val expanded = waiting || (userExpanded ?: (live && current))
    val running = live && current && parts.any { it.state == "running" || it.type == "reasoning" }
    val failed = parts.any(::activityFailed)
    val ink = MaterialTheme.colorScheme.onSurface
    val accent = if (waiting) Color(0xFFF59E0B) else if (failed) MaterialTheme.colorScheme.error else if (running) suzentLink else MaterialTheme.colorScheme.onSurfaceVariant
    val totals = activitySummary(parts, live).map { (kind, count) ->
        stringResource(when (kind) {
            "running" -> R.string.rail_summary_running
            "commands" -> R.string.rail_summary_commands
            "read" -> R.string.rail_summary_read
            "changed" -> R.string.rail_summary_changed
            "searches" -> R.string.rail_summary_searches
            "failed" -> R.string.rail_summary_failed
            else -> R.string.rail_summary_other
        }, count)
    }.joinToString(" · ")
    val latest = parts.lastOrNull()
    val status = when {
        waiting -> stringResource(R.string.approval_required)
        !running || expanded -> totals.ifEmpty { stringResource(R.string.reasoning) }
        latest?.type == "reasoning" -> stringResource(R.string.activity_thinking)
        latest != null -> activityToolLabel(latest)
        else -> stringResource(R.string.activity_label)
    }
    val expandedLabel = stringResource(if (expanded) R.string.reminder_expanded else R.string.reminder_collapsed)
    Column(Modifier.fillMaxWidth()) {
        SuzentTextButton(onClick = { userExpanded = !expanded }, modifier = Modifier.fillMaxWidth().semantics { stateDescription = expandedLabel }, contentPadding = PaddingValues(horizontal = 2.dp)) {
            if (latest != null) { ActivityToolIcon(activityKind(latest), running, waiting, accent); Spacer(Modifier.width(8.dp)) }
            Text(status, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = accent)
            Text(stringResource(R.string.activity_steps, activityStepCount(parts)), fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = accent)
            ActivityChevron(expanded)
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(ink.copy(alpha = .1f)))
        ActivityDisclosure(expanded) {
            Column(Modifier.padding(vertical = 4.dp)) {
                val rows = activityRows(parts)
                rows.forEachIndexed { index, part ->
                    key(part.toolCallId.ifEmpty { "reason-$index" }) { ToolActivityBlock(part, live, index == rows.lastIndex, current) }
                }
            }
        }
    }
}

@Composable
fun ToolActivityBlock(part: MessagePart, live: Boolean, last: Boolean = true, current: Boolean = true) {
    var expanded by remember { mutableStateOf(false) }
    val failed = activityFailed(part)
    val pending = part.state == "approval-requested" && part.output.isEmpty()
    val active = !failed && !pending && live && current && (part.state == "running" || last && part.type == "reasoning")
    val color = if (failed) MaterialTheme.colorScheme.error else if (pending) Color(0xFFF59E0B) else if (active) suzentLink else MaterialTheme.colorScheme.onSurfaceVariant
    val ink = MaterialTheme.colorScheme.onSurface
    val status = stringResource(if (failed) R.string.activity_failed else if (pending) R.string.approval_required else if (active) R.string.activity_running else R.string.activity_completed)
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.width(10.dp).fillMaxHeight().padding(top = 20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.size(6.dp).background(color.copy(alpha = if (active || pending || failed) 1f else .35f), RoundedCornerShape(50)))
            Box(Modifier.width(1.dp).weight(1f).background(if (last) Color.Transparent else ink.copy(alpha = .13f)))
        }
        Column(Modifier.weight(1f)) {
            val expandedLabel = stringResource(if (expanded) R.string.reminder_expanded else R.string.reminder_collapsed)
            SuzentTextButton(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth().heightIn(min = 46.dp).semantics { stateDescription = "$status, $expandedLabel" }, contentPadding = PaddingValues(horizontal = 8.dp)) {
                ActivityToolIcon(activityKind(part), active, pending, color)
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(if (part.type == "reasoning") stringResource(R.string.reasoning) else canonicalActivityTool(part.toolName).replace('_', ' '), fontSize = 12.sp, fontWeight = FontWeight.Normal, maxLines = 1, overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (part.type == "tool") Text(activityToolLabel(part), fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                if (active || pending || failed) Text(status, fontSize = 9.sp, color = color, maxLines = 1)
                ActivityChevron(expanded)
            }
            if (!expanded && failed) Text(activityDetail(part.output, true).take(180), fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.error, maxLines = 2, modifier = Modifier.padding(horizontal = 8.dp).padding(bottom = 8.dp))
            ActivityDisclosure(expanded) {
                Column(Modifier.fillMaxWidth().padding(start = 8.dp, top = 8.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    ActivityDetailView(R.string.activity_input, activityDetail(part.args), true)
                    ActivityDetailView(R.string.activity_output, activityDetail(part.output, true), true)
                    ActivityDetailView(R.string.reasoning, part.text, false)
                }
            }
        }
    }
}

@Composable
private fun ActivityDetailView(label: Int, value: String, code: Boolean) {
    if (value.isEmpty()) return
    var showAll by remember { mutableStateOf(false) }
    val clipboard = LocalClipboardManager.current
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(label).uppercase(), fontSize = 10.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
            SuzentTextButton(onClick = { clipboard.setText(AnnotatedString(value)) }, contentPadding = PaddingValues(0.dp)) { Text(stringResource(R.string.activity_copy_details), fontSize = 10.sp) }
        }
        val visible = if (showAll) value else value.take(12000)
        Box(Modifier.fillMaxWidth().heightIn(max = 220.dp).verticalScroll(rememberScrollState())) {
            if (code) SelectionContainer { Text(visible, fontSize = 11.sp, lineHeight = 17.sp, fontFamily = FontFamily.Monospace, modifier = Modifier.horizontalScroll(rememberScrollState())) }
            else MarkdownText(visible, textSize = 12f)
        }
        if (value.length > 12000 && !showAll) SuzentTextButton(onClick = { showAll = true }) { Text(stringResource(R.string.activity_full_details), fontSize = 12.sp) }
    }
}

@Composable
private fun ActivityToolIcon(kind: String, active: Boolean, pending: Boolean, color: Color) {
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var seconds by remember { mutableDoubleStateOf(0.0) }
    LaunchedEffect(active, pending, reduced, lifecycle) {
        if (!reduced && (active || pending)) lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            var previous = 0L
            while (true) withFrameNanos { now ->
                if (previous != 0L) seconds += ((now - previous) / 1_000_000_000.0).coerceAtMost(.05)
                previous = now
            }
        }
    }
    Canvas(Modifier.size(18.dp)) {
        val t = if (reduced) 0.0 else seconds
        val ink = color.copy(alpha = if ((active || pending) && !reduced) (.7 + .3 * sin(t * 3)).toFloat() else 1f)
        scale(size.width / 24, size.height / 24, pivot = Offset.Zero) {
            fun line(x: Float, y: Float, x2: Float, y2: Float) = drawLine(ink, Offset(x,y), Offset(x2,y2), strokeWidth = 1.5f)
            when {
                pending -> { drawCircle(ink, 8f, Offset(12f,12f), style = Stroke(1.5f)); line(12f,7f,12f,13f); drawCircle(ink, 1f, Offset(12f,17f)) }
                kind == "terminal" -> {
                    drawRect(ink, Offset(2f,4f), Size(20f,16f), style = Stroke(1.5f))
                    line(6f,9f,9f,12f); line(9f,12f,6f,15f)
                    if (!active || reduced || sin(t*5)>0) line(12f,15f,17f,15f)
                }
                kind == "search" -> {
                    val shift = if (active && !reduced) sin(t*3).toFloat() else 0f
                    drawCircle(ink, 6f, Offset(10f+shift,10f), style = Stroke(1.5f)); line(15f+shift,15f,21f,21f)
                }
                kind == "read" || kind == "edit" -> {
                    drawRect(ink, Offset(5f,2f), Size(14f,20f), style = Stroke(1.5f))
                    line(8f,7f,16f,7f); line(8f,11f,16f,11f); line(8f,15f,13f,15f)
                    if (active && !reduced) drawRect(color.copy(alpha = .35f), Offset(4f, (11+sin(t*3)*7).toFloat()), Size(16f,2f))
                }
                kind == "agent" -> {
                    drawCircle(ink,3f,Offset(8f,7f),style=Stroke(1.5f)); drawCircle(ink,3f,Offset(17f,8f),style=Stroke(1.5f))
                    drawArc(ink,180f,180f,false,Offset(2f,12f),Size(12f,12f),style=Stroke(1.5f)); drawArc(ink,180f,180f,false,Offset(12f,13f),Size(10f,10f),style=Stroke(1.5f))
                }
                else -> {
                    drawPath(Path().apply { moveTo(12f,2f); lineTo(15f,9f); lineTo(22f,12f); lineTo(15f,15f); lineTo(12f,22f); lineTo(9f,15f); lineTo(2f,12f); lineTo(9f,9f); close() },ink,style=Stroke(1.5f))
                }
            }
        }
    }
}

package com.suzent.mobile

import android.animation.ValueAnimator
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.VisibilityThreshold
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntSize
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
                else if (live || !compact || pending) AssemblyBadge(thinking = showAssemblyBadge(parts, live), parts = parts, streaming = live)
                else SuzentAssistantBadge(compact = compact)
            }
            if (!live && work.isNotEmpty()) {
                val visible = expanded || pending
                val label = stringResource(if (visible) R.string.reminder_expanded else R.string.reminder_collapsed)
                SuzentTextButton(onClick = { expanded = !expanded }, modifier = Modifier.semantics { stateDescription = label }, contentPadding = PaddingValues(0.dp)) {
                    Text(if (workedSeconds != null) stringResource(R.string.activity_worked_for, activityDuration(workedSeconds)) else stringResource(R.string.activity_label),
                        fontSize = PresentationTokens.typeMeta.sp, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    ActivityChevron(visible)
                }
            }
        }
        if (live) ActivityContent(parts, true, citationSources, regent)
        // The gap below the disclosed work lives inside it: as a separate Column child the spacing stayed
        // after the content shrank to zero and vanished in one frame when the disclosure left composition.
        else Column {
            ActivityDisclosure(expanded || pending) {
                Box(Modifier.padding(bottom = 10.dp)) { ActivityContent(work, false, citationSources, regent) }
            }
            ActivityContent(persistent + parts.drop(start), false, citationSources, regent)
        }
    }
}

@Composable
private fun ActivityDisclosure(visible: Boolean, content: @Composable () -> Unit) {
    val animate = ValueAnimator.areAnimatorsEnabled()
    // Height follows a critically damped spring. Content fades in once there is room, and on collapse stays
    // visible while it is clipped away: fading it first left an empty block shrinking for the rest of the spring.
    val size = spring<IntSize>(stiffness = Spring.StiffnessMediumLow, visibilityThreshold = IntSize.VisibilityThreshold)
    AnimatedVisibility(visible, enter = if (animate) expandVertically(size, expandFrom = Alignment.Top) + fadeIn(tween(160, delayMillis = 60)) else EnterTransition.None,
        exit = if (animate) shrinkVertically(size, shrinkTowards = Alignment.Top) + fadeOut(tween(220, easing = LinearOutSlowInEasing)) else ExitTransition.None) { content() }
}

@Composable
private fun ActivityChevron(expanded: Boolean) {
    val rotation by animateFloatAsState(if (expanded) 90f else 0f,
        if (ValueAnimator.areAnimatorsEnabled()) spring(stiffness = Spring.StiffnessMediumLow) else snap(), label = "activity disclosure")
    Icon(painterResource(R.drawable.ic_chevron_right), contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(start = 6.dp).size(14.dp).graphicsLayer { rotationZ = rotation })
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
            "web" -> R.string.rail_summary_web
            "delegated" -> R.string.rail_summary_delegated
            "agents" -> R.string.rail_summary_agents
            "tasks" -> R.string.rail_summary_tasks
            "memory" -> R.string.rail_summary_memory
            "skills" -> R.string.rail_summary_skills
            "tools" -> R.string.rail_summary_tools
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
            parts.lastOrNull { it.type == "tool" }?.let { tool -> ActivityToolIcon(tool, tool.state == "running" && running, accent); Spacer(Modifier.width(8.dp)) }
            Text(status, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = PresentationTokens.typeLabel.sp, fontWeight = FontWeight.Medium, color = accent)
            Text(stringResource(R.string.activity_steps, activityStepCount(parts)), fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = accent)
            ActivityChevron(expanded)
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(ink.copy(alpha = .1f)))
        ActivityDisclosure(expanded) {
            Column(Modifier.padding(vertical = 4.dp)) {
                val rows = activityRows(parts)
                rows.forEachIndexed { index, part ->
                    key(part.toolCallId.ifEmpty { "reason-$index" }) { ToolActivityBlock(part, live, index == rows.lastIndex, current, first = index == 0) }
                }
            }
        }
    }
}

@Composable
fun ToolActivityBlock(part: MessagePart, live: Boolean, last: Boolean = true, current: Boolean = true, first: Boolean = true) {
    var expanded by remember { mutableStateOf(false) }
    val failed = activityFailed(part)
    val pending = part.state == "approval-requested" && part.output.isEmpty()
    val active = !failed && !pending && live && current && (part.state == "running" || last && part.type == "reasoning")
    val color = if (failed) MaterialTheme.colorScheme.error else if (pending) Color(0xFFF59E0B) else if (active) suzentLink else MaterialTheme.colorScheme.onSurfaceVariant
    val ink = MaterialTheme.colorScheme.onSurface
    val status = stringResource(if (failed) R.string.activity_failed else if (pending) R.string.approval_required else if (active) R.string.activity_running else R.string.activity_completed)
    val dot = color.copy(alpha = if (active || pending || failed) 1f else .35f)
    // Drawn over the row's real (animating) height so neighbouring rows join into one rail without intrinsic measurement.
    Row(Modifier.fillMaxWidth().drawBehind {
        val x = 5.dp.toPx()
        val center = 23.dp.toPx()
        val stroke = 1.dp.toPx()
        val line = ink.copy(alpha = .13f)
        if (!first) drawLine(line, Offset(x, 0f), Offset(x, center), stroke)
        if (!last) drawLine(line, Offset(x, center), Offset(x, size.height), stroke)
        drawCircle(dot, 3.dp.toPx(), Offset(x, center))
    }, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            val expandedLabel = stringResource(if (expanded) R.string.reminder_expanded else R.string.reminder_collapsed)
            SuzentTextButton(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth().heightIn(min = 46.dp).semantics { stateDescription = "$status, $expandedLabel" }, contentPadding = PaddingValues(horizontal = 8.dp)) {
                ActivityToolIcon(part, active, color)
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(if (part.type == "reasoning") stringResource(R.string.reasoning) else canonicalActivityTool(part.toolName).replace('_', ' '), fontSize = PresentationTokens.typeLabel.sp, fontWeight = FontWeight.Normal, maxLines = 1, overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (part.type == "tool") Text(activityToolLabel(part), fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                if (active || pending || failed) Text(status, fontSize = 9.sp, color = color, maxLines = 1)
                ActivityChevron(expanded)
            }
            if (!expanded && failed) Text(activityDetail(part.output, true).take(180), fontSize = PresentationTokens.typeMeta.sp, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.error, maxLines = 2, modifier = Modifier.padding(horizontal = 8.dp).padding(bottom = 8.dp))
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
            if (code) SelectionContainer { Text(visible, fontSize = PresentationTokens.typeMeta.sp, lineHeight = 17.sp, fontFamily = FontFamily.Monospace, modifier = Modifier.horizontalScroll(rememberScrollState())) }
            else MarkdownText(visible, textSize = PresentationTokens.typeLabel.toFloat())
        }
        if (value.length > 12000 && !showAll) SuzentTextButton(onClick = { showAll = true }) { Text(stringResource(R.string.activity_full_details), fontSize = PresentationTokens.typeLabel.sp) }
    }
}

private val toolIconDrawables = mapOf(
    "arrow-down-on-square" to R.drawable.ic_tool_arrow_down_on_square, "bolt" to R.drawable.ic_tool_bolt, "calendar-days" to R.drawable.ic_tool_calendar_days,
    "chat-bubble-left-right" to R.drawable.ic_tool_chat_bubble_left_right, "circle-stack" to R.drawable.ic_tool_circle_stack, "clipboard-document-check" to R.drawable.ic_tool_clipboard_document_check,
    "clipboard-document-list" to R.drawable.ic_tool_clipboard_document_list, "clock" to R.drawable.ic_tool_clock, "command-line" to R.drawable.ic_tool_command_line,
    "cpu-chip" to R.drawable.ic_tool_cpu_chip, "cursor-arrow-rays" to R.drawable.ic_tool_cursor_arrow_rays, "document-plus" to R.drawable.ic_tool_document_plus,
    "document-text" to R.drawable.ic_tool_document_text, "eye" to R.drawable.ic_tool_eye, "film" to R.drawable.ic_tool_film,
    "flag" to R.drawable.ic_tool_flag, "folder" to R.drawable.ic_tool_folder, "folder-open" to R.drawable.ic_tool_folder_open,
    "globe-alt" to R.drawable.ic_tool_globe_alt, "magnifying-glass" to R.drawable.ic_tool_magnifying_glass, "no-symbol" to R.drawable.ic_tool_no_symbol,
    "paint-brush" to R.drawable.ic_tool_paint_brush, "paper-airplane" to R.drawable.ic_tool_paper_airplane, "pencil-square" to R.drawable.ic_tool_pencil_square,
    "photo" to R.drawable.ic_tool_photo, "play" to R.drawable.ic_tool_play, "question-mark-circle" to R.drawable.ic_tool_question_mark_circle,
    "signal" to R.drawable.ic_tool_signal, "speaker-wave" to R.drawable.ic_tool_speaker_wave, "squares-2x2" to R.drawable.ic_tool_squares_2x2,
    "stop" to R.drawable.ic_tool_stop, "user-group" to R.drawable.ic_tool_user_group, "wrench-screwdriver" to R.drawable.ic_tool_wrench_screwdriver,
)

/** Desktop's ToolGroupIcon: the tool's Heroicon, moving while it runs; reasoning keeps the spark. */
@Composable
private fun ActivityToolIcon(part: MessagePart, running: Boolean, color: Color) {
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val approval = when {
        part.state == "approval-requested" && part.output.isEmpty() -> "pending"
        part.state in listOf("denied", "rejected") -> "denied"
        else -> null
    }
    val animation = if (part.type == "tool") activityToolAnimation(part.toolName, approval, running, part.output.isNotEmpty()) else "none"
    var seconds by remember { mutableDoubleStateOf(0.0) }
    LaunchedEffect(animation, reduced, lifecycle) {
        if (!reduced && animation != "none") lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            var previous = 0L
            while (true) withFrameNanos { now ->
                if (previous != 0L) seconds += ((now - previous) / 1_000_000_000.0).coerceAtMost(.05)
                previous = now
            }
        }
    }
    if (part.type != "tool") {
        Canvas(Modifier.size(18.dp)) {
            scale(size.width / 24, size.height / 24, pivot = Offset.Zero) {
                drawPath(Path().apply { moveTo(12f,2f); lineTo(15f,9f); lineTo(22f,12f); lineTo(15f,15f); lineTo(12f,22f); lineTo(9f,15f); lineTo(2f,12f); lineTo(9f,9f); close() }, color, style = Stroke(1.5f))
            }
        }
        return
    }
    // Desktop draws these at 14px; its keyframe offsets are in those pixels.
    val unit = 18f / 14f
    val pose = if (reduced || animation == "none") ToolIconPose() else toolIconPose(animation, seconds)
    Box(Modifier.size(18.dp)) {
        Icon(painterResource(toolIconDrawables[activityToolIcon(part.toolName, approval)] ?: R.drawable.ic_tool_wrench_screwdriver), contentDescription = null, tint = color,
            modifier = Modifier.fillMaxSize().graphicsLayer {
                translationX = (pose.dx * unit).dp.toPx(); translationY = (pose.dy * unit).dp.toPx()
                rotationZ = pose.rotation.toFloat(); scaleX = pose.scale.toFloat(); scaleY = pose.scale.toFloat(); alpha = pose.alpha.toFloat()
            })
        if (pose.sweepAlpha > 0) Box(Modifier.align(Alignment.Center).padding(horizontal = 1.dp).fillMaxWidth().height(1.5.dp)
            .graphicsLayer { translationY = (pose.sweepY * unit).dp.toPx(); alpha = pose.sweepAlpha.toFloat() }
            .background(color, RoundedCornerShape(50)))
    }
}

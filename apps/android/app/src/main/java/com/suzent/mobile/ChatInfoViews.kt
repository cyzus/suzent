package com.suzent.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import java.text.NumberFormat
import java.util.Locale

/** The desktop sidebar's plan and context sections, sized for a phone bottom sheet or a tablet side column. */
@Composable
fun ChatInfoPanel(model: MobileModel, chatId: String, modifier: Modifier = Modifier) {
    var overview by remember(chatId) { mutableStateOf<ChatOverview?>(null) }
    var loaded by remember(chatId) { mutableStateOf(false) }
    val running = model.streaming || model.selected?.running == true
    LaunchedEffect(chatId, running) {
        while (true) {
            model.overview(chatId)?.let { overview = it }
            loaded = true
            // The plan moves while the agent works; at rest it only changes from the desktop.
            delay(if (running) 4_000 else 15_000)
        }
    }
    Column(modifier.background(MaterialTheme.colorScheme.surface)) {
        // Closing is the sheet's drag or the header toggle, so the title stands alone.
        Text(stringResource(R.string.chat_info), Modifier.fillMaxWidth().heightIn(min = 44.dp)
            .padding(horizontal = PresentationTokens.spacePage.dp, vertical = 10.dp).semantics { heading() },
            style = MaterialTheme.typography.titleMedium)
        HorizontalDivider(thickness = PresentationTokens.borderWidthHeavy.dp, color = MaterialTheme.colorScheme.outline)
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(PresentationTokens.spacePage.dp),
            verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceLarge.dp)) {
            val current = overview
            when {
                current != null -> { PlanSection(current); ContextSection(current.context) }
                loaded -> Text(stringResource(R.string.chat_info_unavailable), color = MaterialTheme.colorScheme.onSurfaceVariant)
                else -> Box(Modifier.fillMaxWidth().padding(top = PresentationTokens.spaceLarge.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                }
            }
        }
    }
}

@Composable
private fun InfoSectionHeader(title: String, trailing: String? = null) {
    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title.uppercase(Locale.getDefault()), Modifier.weight(1f), fontWeight = FontWeight.ExtraBold,
                fontSize = PresentationTokens.typeSidebarSection.sp, letterSpacing = 1.6.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (trailing != null) Text(trailing, fontFamily = FontFamily.Monospace, fontSize = PresentationTokens.typeMeta.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        HorizontalDivider(Modifier.padding(top = 6.dp), color = suzentRowDivider)
    }
}

@Composable
private fun planColor(status: String): Color = when (status) {
    "completed" -> Color(PresentationTokens.green)
    "in_progress" -> suzentYellow()
    "blocked" -> MaterialTheme.colorScheme.error
    else -> suzentSelection
}

@Composable
private fun PlanSection(overview: ChatOverview) {
    Column(verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceMedium.dp)) {
        InfoSectionHeader(stringResource(R.string.plan), if (overview.tasks.isEmpty()) null else "${overview.completedCount}/${overview.tasks.size}")
        overview.goal?.let { goal ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(goal.objective, style = MaterialTheme.typography.titleMedium)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    val active = goal.status == "active"
                    Text(stringResource(when (goal.status) {
                        "active" -> R.string.plan_in_progress
                        "paused" -> R.string.plan_paused
                        "completed" -> R.string.plan_completed
                        else -> R.string.plan_not_started
                    }), Modifier.background(if (active) suzentYellow() else suzentSelection).padding(horizontal = 6.dp, vertical = 2.dp),
                        fontSize = PresentationTokens.typeLabel.sp, fontWeight = FontWeight.SemiBold,
                        color = if (active) Color.Black else MaterialTheme.colorScheme.onSurface)
                    val turns = goal.turnsElapsed
                    val max = goal.maxTurns
                    if (turns != null && max != null && max > 0) Text(stringResource(R.string.plan_turns, turns, max),
                        fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        if (overview.tasks.isEmpty()) {
            if (overview.goal == null) Text(stringResource(R.string.plan_empty), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Row(Modifier.fillMaxWidth().clearAndSetSemantics {}, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                overview.tasks.forEach { Box(Modifier.weight(1f).height(6.dp).background(planColor(it.status))) }
            }
            Column(verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceRow.dp)) {
                overview.tasks.forEach { PlanTaskRow(it) }
            }
        }
    }
}

@Composable
private fun PlanTaskRow(task: ChatOverview.PlanTask) {
    val status = stringResource(when (task.status) {
        "completed" -> R.string.plan_done
        "in_progress" -> R.string.plan_in_progress
        "blocked" -> R.string.plan_blocked
        "cancelled" -> R.string.plan_cancelled
        else -> R.string.plan_not_started
    })
    Row(Modifier.semantics(mergeDescendants = true) { contentDescription = "${task.title}, $status" }) {
        Box(Modifier.padding(top = 6.dp).size(8.dp).background(planColor(task.status), CircleShape)
            .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = if (task.status == "pending") 0.4f else 0f), CircleShape))
        Column(Modifier.padding(start = 10.dp)) {
            Text(task.title, fontSize = PresentationTokens.typeChat.sp,
                textDecoration = if (task.status == "cancelled") TextDecoration.LineThrough else null,
                color = if (task.isDone) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface)
            val detail = when {
                task.status == "in_progress" -> task.activeForm?.takeIf { it.isNotBlank() }
                task.status == "blocked" -> stringResource(R.string.plan_waiting_on_earlier)
                else -> null
            }
            if (detail != null) Text(detail, fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ContextSection(context: ChatOverview.Context) {
    val dark = isSystemInDarkTheme()
    val palette = listOf(PresentationTokens.blue, PresentationTokens.green, if (dark) PresentationTokens.yellow_dark else PresentationTokens.yellow,
        if (dark) PresentationTokens.muted_dark else PresentationTokens.muted_light, PresentationTokens.gray)
    val swatch = { index: Int -> Color(palette[index % palette.size]) }
    Column(verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceMedium.dp)) {
        InfoSectionHeader(stringResource(R.string.context), context.percent?.let(::percentText))
        val used = context.usedTokens
        if (used == null) {
            Text(stringResource(R.string.context_empty), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            return@Column
        }
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            context.percent?.let { Text(percentText(it), fontSize = PresentationTokens.typeTitle.sp, fontWeight = FontWeight.Bold) }
            val limit = context.limit
            Text(if (limit != null) stringResource(R.string.context_used_of, compactTokens(used), compactTokens(limit))
                else stringResource(R.string.context_used, compactTokens(used)),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        context.limit?.takeIf { it > 0 }?.let { limit ->
            val filled = (used.toFloat() / limit).coerceIn(0f, 1f)
            val total = context.categories.sumOf { it.tokens }
            Row(Modifier.fillMaxWidth().height(12.dp).background(suzentSelection)
                .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).clearAndSetSemantics {}) {
                if (total > 0) context.categories.forEachIndexed { index, category ->
                    val share = filled * category.tokens / total
                    if (share > 0f) Box(Modifier.weight(share).fillMaxHeight().background(swatch(index)))
                } else if (filled > 0f) Box(Modifier.weight(filled).fillMaxHeight().background(Color(PresentationTokens.blue)))
                if (filled < 1f) Box(Modifier.weight(1f - filled).fillMaxHeight())
            }
        }
        if (context.categories.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            context.categories.forEachIndexed { index, category ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(10.dp).background(swatch(index)).border(1.dp, MaterialTheme.colorScheme.outline))
                    Text(stringResource(categoryLabel(category.id)), Modifier.weight(1f).padding(start = 10.dp), style = MaterialTheme.typography.bodyMedium)
                    Text(compactTokens(category.tokens), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        context.reserveTokens?.takeIf { it > 0 }?.let {
            Text(stringResource(R.string.context_reserve, compactTokens(it)), fontSize = PresentationTokens.typeLabel.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun categoryLabel(id: String): Int = when (id) {
    "messages" -> R.string.context_messages
    "tool_results" -> R.string.context_tool_results
    "system_tools" -> R.string.context_system_tools
    "mcp_tools" -> R.string.context_mcp_tools
    "system_prompt" -> R.string.context_system_prompt
    "skills" -> R.string.context_skills
    "memory" -> R.string.context_memory
    "repository" -> R.string.context_repository
    else -> R.string.context_other
}

internal fun percentText(percent: Double): String =
    if (percent >= 1 || percent == 0.0) "${Math.round(percent)}%" else "<1%"

internal fun compactTokens(tokens: Int): String = when {
    tokens >= 1_000_000 -> trimmed(tokens / 1_000_000.0) + "M"
    tokens >= 1_000 -> trimmed(tokens / 1_000.0) + "k"
    else -> tokens.toString()
}

private fun trimmed(value: Double): String = NumberFormat.getNumberInstance(Locale.ROOT).apply {
    maximumFractionDigits = if (value < 100) 1 else 0
}.format(value)

/** Tablets keep the panel beside the conversation, like the desktop's right sidebar. */
@Composable
fun ChatInfoColumn(model: MobileModel, chatId: String) {
    Row(Modifier.fillMaxHeight()) {
        androidx.compose.material3.VerticalDivider(thickness = PresentationTokens.borderWidthHeavy.dp, color = MaterialTheme.colorScheme.outline)
        ChatInfoPanel(model, chatId, Modifier.width(PresentationTokens.sidebarWidth.dp).fillMaxSize())
    }
}

/** The desktop's sidebar glyph, turned to the edge the panel opens from: a frame whose panel fills in while it is open. */
@Composable
fun PanelToggleIcon(open: Boolean, bottom: Boolean, modifier: Modifier = Modifier) {
    val tint = androidx.compose.material3.LocalContentColor.current
    val divider by androidx.compose.animation.core.animateFloatAsState(if (open) 15f else 16.5f, label = "divider")
    val fill by androidx.compose.animation.core.animateFloatAsState(if (open) 0.22f else 0f, label = "fill")
    androidx.compose.foundation.Canvas(modifier.size(24.dp)) {
        val unit = size.width / 24
        val stroke = 2 * unit
        val start = if (bottom) Offset(4 * unit, divider * unit) else Offset(divider * unit, 4 * unit)
        val end = if (bottom) Offset(20 * unit, divider * unit) else Offset(divider * unit, 20 * unit)
        if (fill > 0f) drawRect(tint.copy(alpha = fill), topLeft = start,
            size = if (bottom) Size(16 * unit, (20 - divider) * unit) else Size((20 - divider) * unit, 16 * unit))
        drawRoundRect(tint, topLeft = Offset(4 * unit, 4 * unit), size = Size(16 * unit, 16 * unit),
            cornerRadius = CornerRadius(2 * unit), style = Stroke(stroke))
        drawLine(tint, start, end, stroke)
    }
}

package com.suzent.mobile

import androidx.compose.foundation.selection.selectable
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import android.widget.TextView
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.painterResource
import kotlin.math.sin
import kotlin.math.cos
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.BorderStroke
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.viewinterop.AndroidView
import io.noties.markwon.AbstractMarkwonPlugin
import io.noties.markwon.core.MarkwonTheme
import io.noties.markwon.Markwon
import io.noties.markwon.ext.tables.TablePlugin
import io.noties.markwon.ext.strikethrough.StrikethroughPlugin

@Composable
fun SuzentTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) darkColorScheme(
        primary = Color(PresentationTokens.blue), onPrimary = Color.White,
        secondaryContainer = Color(PresentationTokens.yellow), onSecondaryContainer = Color.Black,
        surface = Color(PresentationTokens.surface_dark), background = Color(PresentationTokens.surface_dark), outline = Color.White,
        onSurface = Color.White, onBackground = Color.White, onSurfaceVariant = Color(PresentationTokens.muted_dark),
        outlineVariant = Color(PresentationTokens.gray)
    ) else lightColorScheme(
        primary = Color(PresentationTokens.blue), onPrimary = Color.White,
        secondaryContainer = Color(PresentationTokens.yellow), onSecondaryContainer = Color.Black,
        surface = Color.White, background = Color.White, outline = Color.Black,
        onSurface = Color.Black, onBackground = Color.Black, onSurfaceVariant = Color(PresentationTokens.muted_light),
        outlineVariant = Color(0xFFE0E0E0)
    )
    val typography = Typography()
    MaterialTheme(colorScheme = colors, typography = typography.copy(
        titleLarge = typography.titleLarge.copy(fontSize = PresentationTokens.typeTitle.sp, fontWeight = FontWeight.Bold),
        bodyLarge = typography.bodyLarge.copy(fontSize = PresentationTokens.typeBody.sp),
        bodySmall = typography.bodySmall.copy(fontSize = PresentationTokens.typeCaption.sp)
    ), shapes = Shapes(
        extraSmall = RoundedCornerShape(0.dp), small = RoundedCornerShape(0.dp), medium = RoundedCornerShape(0.dp), large = RoundedCornerShape(0.dp), extraLarge = RoundedCornerShape(0.dp)
    ), content = content)
}

@Composable
fun MarkdownText(text: String) {
    val context = LocalContext.current
    val renderer = remember(context) { Markwon.builder(context)
        .usePlugin(object : AbstractMarkwonPlugin() {
            override fun configureTheme(builder: MarkwonTheme.Builder) {
                builder.codeBackgroundColor(Color(PresentationTokens.yellow).toArgb())
                    .codeTextColor(Color.Black.toArgb())
                    .codeBlockBackgroundColor(Color(PresentationTokens.code_bg).toArgb())
                    .codeBlockTextColor(Color.Black.toArgb())
                    .linkColor(Color(PresentationTokens.blue).toArgb())
            }
        }).usePlugin(TablePlugin.create(context)).usePlugin(StrikethroughPlugin.create()).build() }
    val foreground = MaterialTheme.colorScheme.onSurface.toArgb()
    val link = Color(PresentationTokens.blue).toArgb()
    val blocks by produceState<List<MarkdownBlock>>(initialValue = emptyList(), renderer, text) {
        value = withContext(Dispatchers.Default) {
            synchronized(renderer) {
                markdownSections(renderer.parse(text)).map { section ->
                    when (section) {
                        is MarkdownSection.Prose -> MarkdownBlock(renderer.render(section.document))
                        is MarkdownSection.Code -> MarkdownBlock(section.text, section.language)
                    }
                }
            }
        }
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        blocks.forEach { block ->
            if (block.language != null) {
                Column(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)) {
                    Text(block.language, Modifier.fillMaxWidth().background(Color.Black).padding(12.dp),
                        color = Color.White, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodySmall)
                    Row(Modifier.fillMaxWidth().background(Color(PresentationTokens.code_bg)).horizontalScroll(rememberScrollState())) {
                        SelectionContainer {
                            Text(block.body.toString(), Modifier.padding(16.dp), color = Color.Black,
                                fontFamily = FontFamily.Monospace, fontSize = 14.sp, softWrap = false)
                        }
                    }
                }
            } else {
                AndroidView(modifier = Modifier.fillMaxWidth(), factory = { ctx ->
                    TextView(ctx).apply { textSize = PresentationTokens.typeChat.toFloat(); setTextIsSelectable(true); setLineSpacing(0f, 1.2f) }
                }, update = { view ->
                    view.setTextColor(foreground); view.setLinkTextColor(link)
                    if (view.tag != block.body) { renderer.setParsedMarkdown(view, block.body as android.text.Spanned); view.tag = block.body }
                })
            }
        }
    }
}

private data class MarkdownBlock(val body: CharSequence, val language: String? = null)

@Composable
fun MessageView(message: DisplayMessage, isLatest: Boolean = false) {
    val user = message.role == "user"
    val outline = MaterialTheme.colorScheme.outline
    Box(Modifier.fillMaxWidth(), contentAlignment = if (user) androidx.compose.ui.Alignment.CenterEnd else androidx.compose.ui.Alignment.CenterStart) {
    Column((if (user) Modifier.widthIn(max = 320.dp) else Modifier.fillMaxWidth()).then(if (user) Modifier.padding(start = 40.dp, end = 2.dp)
        .drawBehind { drawRect(outline, topLeft = Offset(PresentationTokens.shadowOffset.dp.toPx(), PresentationTokens.shadowOffset.dp.toPx())) }
        .background(Color(PresentationTokens.code_bg))
        .border(PresentationTokens.borderWidth.dp, outline).padding(10.dp) else Modifier.padding(vertical = 6.dp)),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (!user) SuzentAssistantBadge(compact = !isLatest)
        if (user && message.text.isNotBlank()) {
            Text(stringResource(R.string.you), color = Color.Black, style = MaterialTheme.typography.labelLarge)
            SelectionContainer { Text(message.text, color = Color.Black, fontSize = PresentationTokens.typeChat.sp) }
        }
        if (!user) ActivityContent(message.parts, live = false)

    }
}
}

@Composable
fun SuzentAction(label: String, onClick: () -> Unit, prominent: Boolean = false, enabled: Boolean = true, compact: Boolean = false) {
    val outline = MaterialTheme.colorScheme.outline
    Box((if (compact) Modifier else Modifier.fillMaxWidth()).drawBehind {
        val offset = PresentationTokens.shadowOffset.dp.toPx()
        if (enabled) drawRect(outline, topLeft = Offset(offset, offset),
            size = androidx.compose.ui.geometry.Size((size.width - offset).coerceAtLeast(0f), (size.height - offset).coerceAtLeast(0f)))
    }.padding(end = PresentationTokens.shadowOffset.dp, bottom = PresentationTokens.shadowOffset.dp)) {
        val fill = if (prominent) Color(PresentationTokens.blue) else MaterialTheme.colorScheme.surface
        Row((if (compact) Modifier else Modifier.fillMaxWidth())
            .background(if (enabled) fill else fill.copy(alpha = 0.45f))
            .border(PresentationTokens.borderWidth.dp, outline)
            .clickable(enabled = enabled, role = androidx.compose.ui.semantics.Role.Button, onClick = onClick)
            .heightIn(min = PresentationTokens.controlHeight.dp)
            .padding(horizontal = (if (compact) 12 else 16).dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.Center, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text(label, fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold,
                color = (if (prominent) Color.White else MaterialTheme.colorScheme.onSurface).copy(alpha = if (enabled) 1f else 0.45f))
        }
    }
}

@Composable
fun SuzentWordmark() {
    Row(Modifier.fillMaxWidth().heightIn(min = PresentationTokens.controlHeight.dp).padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp, androidx.compose.ui.Alignment.CenterHorizontally),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Box(Modifier.size(10.dp).background(MaterialTheme.colorScheme.onSurface))
        Text("SUZENT", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Black)
        Box(Modifier.size(10.dp).background(MaterialTheme.colorScheme.onSurface))
    }
}

@Composable
fun SuzentAssistantBadge(compact: Boolean = false) {
    if (compact) Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Image(painterResource(R.drawable.suzent_logo), contentDescription = null,
            modifier = Modifier.size(16.dp).graphicsLayer { alpha = .5f })
        Text("SUZENT", fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold, fontSize = 10.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    } else {
        val outline = MaterialTheme.colorScheme.outline
        Box(Modifier.padding(end = 3.dp, bottom = 3.dp).drawBehind {
            drawRect(outline, topLeft = Offset(3.dp.toPx(), 3.dp.toPx()))
        }.size(90.dp, 40.dp).background(MaterialTheme.colorScheme.surface)
            .border(PresentationTokens.borderWidth.dp, outline), contentAlignment = androidx.compose.ui.Alignment.Center) {
            Image(painterResource(R.drawable.suzent_logo), contentDescription = "Suzent", modifier = Modifier.size(26.dp))
        }
    }
}

@Composable
fun ActivityContent(parts: List<MessagePart>, live: Boolean) {
    val chunks = remember(parts) { activityChunks(parts) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        chunks.forEachIndexed { index, chunk ->
            key(index) {
                if (chunk.first().type == "text") MarkdownText(chunk.first().text)
                else ActivityRail(chunk, live)
            }
        }
        if (live) StreamingPulse()
    }
}

@Composable
private fun ActivityRail(parts: List<MessagePart>, live: Boolean) {
    var expanded by remember { mutableStateOf(false) }
    val waiting = parts.any { it.state == "approval-requested" }
    val running = live && parts.any { it.state == "running" }
    val failed = parts.any { it.state in listOf("error", "denied") }
    val ink = MaterialTheme.colorScheme.onSurface
    val accent = if (failed) MaterialTheme.colorScheme.error else if (running) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
    val status = stringResource(if (waiting) R.string.approval_required else if (running) R.string.activity_running else if (failed) R.string.activity_failed else R.string.activity_completed)
    Column(Modifier.fillMaxWidth()) {
        TextButton(onClick = { expanded = !expanded }, contentPadding = PaddingValues(horizontal = 4.dp, vertical = 12.dp), modifier = Modifier.fillMaxWidth()) {
            Text(status.uppercase(), fontSize = 12.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold,
                color = if (waiting || failed) accent else MaterialTheme.colorScheme.onSurfaceVariant)
            if (running) { Spacer(Modifier.width(8.dp)); StreamingPulse() }
            Text("  |  ", fontSize = 12.sp, color = ink.copy(alpha = 0.25f))
            Text(stringResource(R.string.activity_steps, parts.size).uppercase(), fontSize = 12.sp, fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(if (expanded) "  ⌄" else "  ›", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.weight(1f))
        }
        if (expanded) {
            HorizontalDivider(color = ink.copy(alpha = 0.12f))
            Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
                parts.forEachIndexed { index, part ->
                    key(part.toolCallId.ifEmpty { "reason-$index" }) {
                        ToolActivityBlock(part, live, index == parts.lastIndex)
                    }
                }
            }
        }
        HorizontalDivider(color = ink.copy(alpha = 0.12f))
    }
}

@Composable
fun ToolActivityBlock(part: MessagePart, live: Boolean, last: Boolean = true) {
    val ink = MaterialTheme.colorScheme.onSurface
    var details by remember { mutableStateOf(false) }
    val active = live && part.state == "running"
    val error = part.state in listOf("error", "denied")
    val pending = part.state == "approval-requested"
    val color = if (error) MaterialTheme.colorScheme.error else if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Column(Modifier.width(16.dp).fillMaxHeight().padding(top = 14.dp), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
            Box(Modifier.size(16.dp).background(if (pending) Color(PresentationTokens.yellow) else color.copy(alpha = 0.08f)), contentAlignment = androidx.compose.ui.Alignment.Center) {
                Text(if (pending) "!" else if (error) "×" else if (active) "·" else "✓", fontSize = 10.sp, lineHeight = 12.sp, color = if (pending) Color.Black else color)
            }
            Box(Modifier.width(1.dp).weight(1f).background(if (last) Color.Transparent else ink.copy(alpha = 0.12f)))
        }
        Column(Modifier.weight(1f)) {
            TextButton(onClick = { details = !details }, contentPadding = PaddingValues(0.dp), modifier = Modifier.fillMaxWidth().heightIn(min = 44.dp)) {
                Text(if (part.type == "reasoning") stringResource(R.string.reasoning) else if (part.type == "tool") part.toolName.ifEmpty { stringResource(R.string.tool_activity) } else stringResource(R.string.unsupported_activity),
                    color = ink, fontSize = 13.sp, maxLines = 2, fontWeight = FontWeight.Medium,
                    fontFamily = if (part.type == "tool") FontFamily.Monospace else FontFamily.Default, modifier = Modifier.weight(1f))
                if (active) StreamingPulse()
                Text(if (details) "⌄" else "›", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
            val preview = if (error) part.output else part.args
            if (!details && part.type == "tool" && preview.isNotEmpty()) {
                Text(preview, modifier = Modifier.padding(bottom = 10.dp), fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            }
            if (details) Column(Modifier.padding(bottom = 12.dp).fillMaxWidth().background(ink.copy(alpha = 0.04f)).border(1.dp, ink.copy(alpha = 0.12f)).padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ActivityDetail(R.string.activity_input, part.args, true)
                ActivityDetail(R.string.activity_output, part.output, true)
                ActivityDetail(R.string.reasoning, part.text, false)
            }
        }
    }
}

@Composable
private fun ActivityDetail(label: Int, value: String, code: Boolean) {
    if (value.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(stringResource(label).uppercase(), fontSize = 10.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
        SelectionContainer { Text(value, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = if (code) FontFamily.Monospace else FontFamily.Default) }
    }
}

@Composable
fun ApprovalCards(model: MobileModel) {
    model.pendingApprovals.forEach { request ->
        key(request.id) {
            Column(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.approval_required), Modifier.fillMaxWidth().background(Color(PresentationTokens.yellow)).padding(12.dp), color = Color.Black, fontWeight = FontWeight.Bold)
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(request.toolName, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)
                    Text(stringResource(R.string.approval_backend), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    SelectionContainer { Text(request.args, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall) }
                    if (request.reason.isNotEmpty()) Text(request.reason, style = MaterialTheme.typography.bodySmall)
                    if (model.device?.permissions?.approveTools == true && request.actions.isNotEmpty()) {
                        request.actions.forEach { action ->
                            SuzentAction((if (model.approvalChoices[request.id] == action.id) "✓ " else "") + stringResource(if (action.behavior == "allow") R.string.allow_once else R.string.reject_tool),
                                { model.chooseApproval(request, action) }, prominent = action.behavior == "allow", enabled = !model.approvalBusy, compact = true)
                        }
                        Text(stringResource(R.string.approval_batch), style = MaterialTheme.typography.bodySmall)
                    } else Text(stringResource(R.string.approval_desktop_only), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}


@Composable
fun GreetingCube(modifier: Modifier = Modifier) {
    val motionEnabled = android.animation.ValueAnimator.areAnimatorsEnabled()
    val phase = if (motionEnabled) {
        val transition = rememberInfiniteTransition(label = "cube presence")
        transition.animateFloat(initialValue = 0f, targetValue = (Math.PI * 2).toFloat(),
            animationSpec = infiniteRepeatable(tween(24000, easing = LinearEasing)), label = "cube phase")
    } else remember { mutableFloatStateOf(0f) }
    Box(modifier) {
        Canvas(Modifier.fillMaxSize()) {
            val degrees = phase.value * 180f / Math.PI.toFloat()
            val side = size.minDimension * 0.675f
            val inset = Offset((size.width - side) / 2, (size.height - side) / 2)
            rotate(degrees) { drawRect(Color.Gray.copy(alpha = 0.5f), topLeft = inset, size = androidx.compose.ui.geometry.Size(side, side), style = Stroke(1.dp.toPx())) }
            rotate(-degrees + 45f) { drawRect(Color.Gray.copy(alpha = 0.4f), topLeft = inset, size = androidx.compose.ui.geometry.Size(side, side), style = Stroke(1.dp.toPx())) }
        }
        Image(painterResource(R.drawable.greeting_cube), contentDescription = null,
            modifier = Modifier.fillMaxSize().graphicsLayer {
                rotationY = sin(phase.value * 4) * 12
                rotationX = cos(phase.value * 4) * 4
                translationY = sin(phase.value * 4) * 4.dp.toPx()
                cameraDistance = 12 * density
            })
    }
}

@Composable
fun SuzentSelectionPanel(title: String, options: List<Pair<String, String>>, selected: String, dismiss: () -> Unit, choose: (String) -> Unit) {
    val outline = MaterialTheme.colorScheme.outline
    androidx.compose.ui.window.Dialog(onDismissRequest = dismiss) {
        Column(Modifier.fillMaxWidth().padding(4.dp).drawBehind {
            drawRect(outline, topLeft = Offset(4.dp.toPx(), 4.dp.toPx()))
        }.background(MaterialTheme.colorScheme.surface).border(2.dp, outline)) {
            val dismissLabel = stringResource(R.string.dismiss)
            Row(Modifier.fillMaxWidth().background(Color.Black).padding(start = 16.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text(title, Modifier.weight(1f), fontFamily = FontFamily.Monospace, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color.White)
                TextButton(onClick = dismiss, modifier = Modifier.size(44.dp)) { Text("×", color = Color.White, modifier = Modifier.semantics { contentDescription = dismissLabel }) }
            }
            androidx.compose.foundation.lazy.LazyColumn(Modifier.fillMaxWidth().heightIn(max = 480.dp)) {
                items(options.size) { index ->
                    val (id, label) = options[index]
                    val active = id == selected
                    Row(Modifier.fillMaxWidth().background(if (active) Color(PresentationTokens.yellow) else MaterialTheme.colorScheme.surface)
                        .selectable(selected = active, onClick = { choose(id) }, role = androidx.compose.ui.semantics.Role.RadioButton)
                        .heightIn(min = 48.dp).padding(16.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Text(label, Modifier.weight(1f), fontSize = 15.sp, fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
                            color = if (active) Color.Black else MaterialTheme.colorScheme.onSurface)
                        if (active) Text("✓", color = Color.Black)
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                }
            }
        }
    }
}


@Composable
fun StreamingPulse() {
    val enabled = android.animation.ValueAnimator.areAnimatorsEnabled()
    val phase = if (enabled) {
        val transition = rememberInfiniteTransition(label = "streaming")
        val value by transition.animateFloat(0f, (2 * Math.PI).toFloat(),
            infiniteRepeatable(tween(1600, easing = LinearEasing)), label = "streaming phase")
        value
    } else 0f
    Row(Modifier.width(18.dp).height(12.dp), horizontalArrangement = Arrangement.spacedBy(3.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        repeat(3) { index ->
            Box(Modifier.size(4.dp).graphicsLayer {
                alpha = if (enabled) 0.3f + 0.7f * (sin(phase - index * 0.8f) + 1f) / 2f else 0.7f
            }.background(MaterialTheme.colorScheme.primary))
        }
    }
}

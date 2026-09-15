package com.suzent.mobile

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
fun MessageView(message: DisplayMessage) {
    val user = message.role == "user"
    val outline = MaterialTheme.colorScheme.outline
    Box(Modifier.fillMaxWidth(), contentAlignment = if (user) androidx.compose.ui.Alignment.CenterEnd else androidx.compose.ui.Alignment.CenterStart) {
    Column((if (user) Modifier.widthIn(max = 320.dp) else Modifier.fillMaxWidth()).then(if (user) Modifier.padding(start = 40.dp, end = 2.dp)
        .drawBehind { drawRect(outline, topLeft = Offset(PresentationTokens.shadowOffset.dp.toPx(), PresentationTokens.shadowOffset.dp.toPx())) }
        .background(Color(PresentationTokens.code_bg))
        .border(PresentationTokens.borderWidth.dp, outline).padding(10.dp) else Modifier.padding(vertical = 6.dp)),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (message.text.isNotBlank()) {
            if (message.role == "assistant") SuzentAssistantBadge()
            else Text(stringResource(if (user) R.string.you else R.string.activity),
                color = if (user) Color.Black else MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.labelLarge)
            if (user) SelectionContainer { Text(message.text, color = Color.Black, fontSize = PresentationTokens.typeChat.sp) }
        }
        if (!user) ActivityContent(message.parts, live = false)

    }
}
}

@Composable
fun SuzentAction(label: String, onClick: () -> Unit, prominent: Boolean = false, enabled: Boolean = true, compact: Boolean = false) {
    val outline = MaterialTheme.colorScheme.outline
    Button(onClick = onClick, enabled = enabled, shape = RectangleShape,
        border = BorderStroke(PresentationTokens.borderWidth.dp, outline),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (prominent) Color(PresentationTokens.blue) else MaterialTheme.colorScheme.surface,
            contentColor = if (prominent) Color.White else MaterialTheme.colorScheme.onSurface),
        modifier = (if (compact) Modifier else Modifier.fillMaxWidth()).heightIn(min = PresentationTokens.controlHeight.dp).padding(end = 2.dp, bottom = 2.dp).drawBehind {
            if (enabled) drawRect(outline, topLeft = Offset(PresentationTokens.shadowOffset.dp.toPx(), PresentationTokens.shadowOffset.dp.toPx()))
        }, contentPadding = PaddingValues(horizontal = (if (compact) PresentationTokens.spaceMedium else PresentationTokens.spacePage).dp, vertical = (if (compact) 8 else 12).dp)) {
        Text(label, fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold)
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
fun SuzentAssistantBadge() {
    Row(Modifier.border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)
        .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.size(28.dp).background(Color.Black, RoundedCornerShape(5.dp)),
            horizontalArrangement = Arrangement.spacedBy(4.dp, androidx.compose.ui.Alignment.CenterHorizontally),
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            repeat(2) { Box(Modifier.size(5.dp).background(Color.White, RoundedCornerShape(1.dp))) }
        }
        Text("SUZENT", fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
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
    }
}

@Composable
private fun ActivityRail(parts: List<MessagePart>, live: Boolean) {
    var expanded by remember { mutableStateOf(live) }
    val waiting = parts.any { it.state == "approval-requested" }
    val running = live && parts.any { it.state == "running" }
    val failed = parts.any { it.state in listOf("error", "denied") }
    val status = stringResource(if (waiting) R.string.approval_required else if (running) R.string.activity_running else if (failed) R.string.activity_failed else R.string.activity_completed)
    Column(Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
        TextButton(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth()) {
            Text(if (expanded) "−" else "+", color = MaterialTheme.colorScheme.onSurface)
            Spacer(Modifier.width(8.dp))
            Text(stringResource(R.string.activity_count, parts.size), fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurface, modifier = Modifier.weight(1f))
            Text(status, style = MaterialTheme.typography.labelSmall, color = if (running) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (expanded) parts.forEachIndexed { index, part ->
            key(part.toolCallId.ifEmpty { "reason-$index" }) {
                var details by remember { mutableStateOf(false) }
                val color = when {
                    part.state == "approval-requested" -> Color(PresentationTokens.yellow)
                    part.state in listOf("error", "denied") -> MaterialTheme.colorScheme.error
                    live && part.state == "running" -> Color(PresentationTokens.blue)
                    else -> Color(0xFF62A87C)
                }
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp).height(IntrinsicSize.Min)) {
                    Box(Modifier.width(18.dp).fillMaxHeight().drawBehind {
                        drawLine(color.copy(alpha = .45f), Offset(5.dp.toPx(), 0f), Offset(5.dp.toPx(), size.height), 2.dp.toPx())
                    }) { Box(Modifier.padding(top = 16.dp).size(10.dp).background(color).border(1.dp, MaterialTheme.colorScheme.outline)) }
                    Column(Modifier.weight(1f).padding(bottom = 8.dp)) {
                        TextButton(onClick = { details = !details }, contentPadding = PaddingValues(vertical = 8.dp), modifier = Modifier.fillMaxWidth()) {
                            Text(if (part.type == "reasoning") stringResource(R.string.reasoning) else if (part.type == "tool") part.toolName.ifEmpty { stringResource(R.string.tool_activity) } else stringResource(R.string.unsupported_activity),
                                color = MaterialTheme.colorScheme.onSurface, fontFamily = FontFamily.Monospace, modifier = Modifier.weight(1f))
                            Text(if (details) "−" else "+")
                        }
                        if (details) SelectionContainer {
                            Text(listOf(part.args, part.output, part.text).filter { it.isNotBlank() }.joinToString("\n\n").ifEmpty { status },
                                style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
                        }
                    }
                }
            }
        }
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

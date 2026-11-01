package com.suzent.mobile

import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.ui.draw.alpha
import androidx.compose.foundation.selection.selectable
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.contentDescription
import android.widget.TextView
import android.content.Intent
import android.net.Uri
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.painterResource
import kotlin.math.sin
import kotlin.math.cos
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.conflate
import kotlinx.coroutines.flow.filter
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.layout.layout
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontWeight
import android.os.Build
import android.view.HapticFeedbackConstants
import android.view.View
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalAccessibilityManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.onLongClick
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.withTimeoutOrNull
import io.noties.markwon.AbstractMarkwonPlugin
import io.noties.markwon.core.MarkwonTheme
import io.noties.markwon.Markwon
import io.noties.markwon.MarkwonConfiguration
import io.noties.markwon.LinkResolver
import io.noties.markwon.ext.tables.TablePlugin
import io.noties.markwon.ext.strikethrough.StrikethroughPlugin

@Composable
fun SuzentTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) darkColorScheme(
        primary = Color(PresentationTokens.blue), onPrimary = Color.White,
        secondaryContainer = Color(PresentationTokens.yellow), onSecondaryContainer = Color.Black,
        surface = Color(PresentationTokens.surface_dark), background = Color(PresentationTokens.background_dark),
        surfaceVariant = Color(PresentationTokens.code_header_dark),
        surfaceDim = Color(PresentationTokens.background_dark), surfaceBright = Color(PresentationTokens.code_header_dark),
        surfaceContainerLowest = Color(PresentationTokens.background_dark), surfaceContainerLow = Color(PresentationTokens.surface_dark),
        surfaceContainer = Color(PresentationTokens.surface_dark), surfaceContainerHigh = Color(PresentationTokens.code_header_dark),
        surfaceContainerHighest = Color(PresentationTokens.gray), surfaceTint = Color.Transparent,
        outline = Color(PresentationTokens.outline_dark), outlineVariant = Color(PresentationTokens.outline_subtle_dark),
        onSurface = Color(PresentationTokens.text_dark), onBackground = Color(PresentationTokens.text_dark),
        onSurfaceVariant = Color(PresentationTokens.muted_dark),
        error = Color(PresentationTokens.danger_dark), onError = Color.Black
    ) else lightColorScheme(
        primary = Color(PresentationTokens.blue), onPrimary = Color.White,
        secondaryContainer = Color(PresentationTokens.yellow), onSecondaryContainer = Color.Black,
        surface = Color.White, background = Color.White, outline = Color.Black,
        onSurface = Color.Black, onBackground = Color.Black, onSurfaceVariant = Color(PresentationTokens.muted_light),
        outlineVariant = Color(0xFFE0E0E0),
        error = Color(PresentationTokens.danger), onError = Color.White
    )
    val typography = Typography()
    MaterialTheme(colorScheme = colors, typography = typography.copy(
        titleLarge = typography.titleLarge.copy(fontSize = PresentationTokens.typeTitle.sp, fontWeight = FontWeight.Bold),
        titleMedium = typography.titleMedium.copy(fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold),
        labelMedium = typography.labelMedium.copy(fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold),
        bodyMedium = typography.bodyMedium.copy(fontSize = PresentationTokens.typeControl.sp),
        bodyLarge = typography.bodyLarge.copy(fontSize = PresentationTokens.typeBody.sp),
        bodySmall = typography.bodySmall.copy(fontSize = PresentationTokens.typeCaption.sp)
    ), shapes = Shapes(
        extraSmall = RoundedCornerShape(PresentationTokens.radius.dp), small = RoundedCornerShape(PresentationTokens.radius.dp),
        medium = RoundedCornerShape(PresentationTokens.radius.dp), large = RoundedCornerShape(PresentationTokens.radius.dp),
        extraLarge = RoundedCornerShape(PresentationTokens.radius.dp)
    ), content = content)
}

val suzentShadow: Color
    @Composable get() = Color(if (isSystemInDarkTheme()) PresentationTokens.shadow_dark else PresentationTokens.black)

val suzentSelection: Color
    @Composable get() = Color(if (isSystemInDarkTheme()) PresentationTokens.selection_dark else PresentationTokens.selection_light)

val suzentRowDivider: Color
    @Composable get() = Color(if (isSystemInDarkTheme()) PresentationTokens.selection_dark else PresentationTokens.selection_light)

val suzentLink: Color
    @Composable get() = Color(if (isSystemInDarkTheme()) PresentationTokens.link_dark else PresentationTokens.blue)

val PressedAlpha = PresentationTokens.pressedAlpha.toFloat()
val DisabledAlpha = PresentationTokens.disabledAlpha.toFloat()

enum class SuzentHaptic { Light, LongPress, Confirm, Reject }

fun View.suzentHaptic(kind: SuzentHaptic) {
    performHapticFeedback(when (kind) {
        SuzentHaptic.Light -> HapticFeedbackConstants.VIRTUAL_KEY
        SuzentHaptic.LongPress -> HapticFeedbackConstants.LONG_PRESS
        SuzentHaptic.Confirm -> if (Build.VERSION.SDK_INT >= 30) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.VIRTUAL_KEY
        SuzentHaptic.Reject -> if (Build.VERSION.SDK_INT >= 30) HapticFeedbackConstants.REJECT else HapticFeedbackConstants.LONG_PRESS
    })
}

fun shareText(context: android.content.Context, text: String) {
    val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text)
    try { context.startActivity(Intent.createChooser(send, null)) } catch (_: android.content.ActivityNotFoundException) {}
}

@Composable
fun formattedTimestamp(raw: String): String {
    val context = LocalContext.current
    val is24Hour = android.text.format.DateFormat.is24HourFormat(context)
    return remember(raw, is24Hour) {
        val locale = java.util.Locale.getDefault()
        formatTimestamp(raw, java.time.ZonedDateTime.now(), locale, is24Hour) { android.text.format.DateFormat.getBestDateTimePattern(locale, it) }
    }
}

@Composable
fun SuzentChevron(expanded: Boolean, modifier: Modifier = Modifier, size: Dp = 16.dp, tint: Color = LocalContentColor.current) {
    Icon(painterResource(R.drawable.ic_chevron_right), contentDescription = null, tint = tint,
        modifier = modifier.size(size).rotate(if (expanded) 90f else 0f))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MarkdownText(text: String, citationSources: List<CitationSource> = emptyList(), textSize: Float = PresentationTokens.typeChat.toFloat()) {
    val context = LocalContext.current
    var pendingLink by remember { mutableStateOf<String?>(null) }
    val renderedText = remember(text, citationSources) { markdownWithCitationLinks(text, citationSources, badges = true) }
    val dark = isSystemInDarkTheme()
    val iconURLs = remember(citationSources) { citationSources.map { it.favicon }.filter { it.startsWith("https://") }.distinct() }
    val icons by produceState<Map<String, android.graphics.Bitmap>>(emptyMap(), iconURLs) {
        value = emptyMap()
        for (url in iconURLs) {
            val bitmap = withContext(Dispatchers.IO) { CitationIcons.load(url) }
            if (bitmap != null) value = value + (url to bitmap)
        }
    }
    val codeBackground = Color(if (dark) PresentationTokens.surface_dark else PresentationTokens.code_bg)
    val codeForeground = Color(if (dark) PresentationTokens.text_dark else PresentationTokens.code_text)
    val codeHeader = Color(if (dark) PresentationTokens.code_header_dark else PresentationTokens.black)
    val link = suzentLink.toArgb()
    val tablePlugin = remember(context) { TablePlugin.create(context) }
    val renderer = remember(context, dark) { Markwon.builder(context)
        .usePlugin(object : AbstractMarkwonPlugin() {
            override fun configureConfiguration(builder: MarkwonConfiguration.Builder) {
                builder.linkResolver(LinkResolver { _, link ->
                    if (runCatching { java.net.URI(link).scheme?.lowercase() }.getOrNull() in listOf("http", "https", "suzent-citation")) pendingLink = link
                })
            }
        })
        .usePlugin(object : AbstractMarkwonPlugin() {
            override fun configureTheme(builder: MarkwonTheme.Builder) {
                builder.codeBackgroundColor(Color(PresentationTokens.yellow).toArgb())
                    .codeTextColor(Color.Black.toArgb())
                    .codeBlockBackgroundColor(codeBackground.toArgb())
                    .codeBlockTextColor(codeForeground.toArgb())
                    .linkColor(link)
            }
        }).usePlugin(tablePlugin).usePlugin(StrikethroughPlugin.create()).build() }
    val foreground = MaterialTheme.colorScheme.onSurface.toArgb()
    val latestText by rememberUpdatedState(renderedText)
    fun renderBlocks(markdown: String) = synchronized(renderer) {
        markdownSections(renderer.parse(markdown)).map { section ->
            when (section) {
                is MarkdownSection.Prose -> MarkdownBlock(renderer.render(section.document))
                is MarkdownSection.Code -> MarkdownBlock(section.text, section.language)
            }
        }
    }
    // The first render is synchronous so a message has its real height on the frame it scrolls into view;
    // rendering it a frame later made everything below jump by the height of the text.
    val first = remember(renderer) { renderedText to renderBlocks(renderedText) }
    val blocks by produceState(initialValue = first.second, renderer) {
        // Finish the current parse, then render the newest pending text. Cancelling on
        // every token can starve publication when a long document takes >50 ms to parse.
        snapshotFlow { latestText }.filter { it != first.first }.conflate().collect { markdown ->
            value = withContext(Dispatchers.Default) { renderBlocks(markdown) }
        }
    }
    fun binding(body: CharSequence) =
        MarkdownBinding(body, textSize, foreground, link, dark, pendingLink, icons, citationSources)
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        blocks.forEach { block ->
            if (block.language != null) {
                Column(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)) {
                    Text(block.language, Modifier.fillMaxWidth().background(codeHeader).padding(12.dp),
                        color = Color.White, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodySmall)
                    Row(Modifier.fillMaxWidth().background(codeBackground).horizontalScroll(rememberScrollState())) {
                        SelectionContainer {
                            Text(block.body.toString(), Modifier.padding(16.dp), color = codeForeground,
                                fontFamily = FontFamily.Monospace, fontSize = 14.sp, softWrap = false)
                        }
                    }
                }
            } else {
                MarkdownProse(binding(block.body), renderer, tablePlugin, Modifier.fillMaxWidth())
            }
        }
    }
    pendingLink?.let { link ->
        val ids = Uri.parse(link).path.orEmpty().removePrefix("/").split(',')
        val sources = if (link.startsWith("suzent-citation://")) ids.mapNotNull { id -> citationSources.firstOrNull { it.id == id } }
            else listOf(citationSources.firstOrNull { it.url == link } ?: CitationSource("", "webpage", Uri.parse(link).host.orEmpty(), link))
        ModalBottomSheet(onDismissRequest = { pendingLink = null }, shape = RectangleShape) {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(stringResource(R.string.citation_sources), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                sources.forEach { source ->
                    val uri = Uri.parse(source.url)
                    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            val icon = icons[source.favicon]
                            if (icon != null) Image(icon.asImageBitmap(), contentDescription = null, modifier = Modifier.size(18.dp))
                            else Icon(painterResource(R.drawable.ic_globe), contentDescription = null, modifier = Modifier.size(18.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(uri.host.orEmpty().removePrefix("www."), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text(source.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        if (source.snippet.isNotBlank()) Text(source.snippet, style = MaterialTheme.typography.bodyMedium, maxLines = 6, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                        if (uri.scheme in listOf("http", "https")) {
                            Button(onClick = { androidx.browser.customtabs.CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, uri) }, shape = RectangleShape) {
                                Text(stringResource(R.string.citation_read))
                            }
                            Row {
                                TextButton(onClick = {
                                    val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                                    clipboard.setPrimaryClip(android.content.ClipData.newPlainText(source.title, source.url))
                                }) { Text(stringResource(R.string.citation_copy)) }
                                TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, uri)) }) { Text(stringResource(R.string.citation_external)) }
                            }
                        }
                    }
                }
            }
        }
    }
}


@Composable
private fun MarkdownProse(binding: MarkdownBinding, renderer: Markwon, tablePlugin: TablePlugin, modifier: Modifier) {
    AndroidView(modifier = modifier, factory = { ctx ->
        StableTableTextView(ctx).apply { setTextIsSelectable(true); setLineSpacing(0f, 1.2f) }
    }, update = update@ { view ->
        if (view.tag == binding) return@update
        view.tag = binding
        view.textSize = binding.textSize
        view.tablePlugin = tablePlugin
        view.setTextColor(binding.foreground); view.setLinkTextColor(binding.link)
        val styled = android.text.SpannableString(binding.body)
        styled.getSpans(0, styled.length, android.text.style.ClickableSpan::class.java).forEach { span ->
            val start = styled.getSpanStart(span)
            val end = styled.getSpanEnd(span)
            if (styled.subSequence(start, end).startsWith("↗  ")) {
                val target = (span as? android.text.style.URLSpan)?.url
                val sourceId = target?.let { Uri.parse(it).path?.removePrefix("/")?.split(',')?.firstOrNull() }
                val icon = binding.sources.firstOrNull { it.id == sourceId }?.favicon?.let(binding.icons::get)
                styled.setSpan(CitationBadgeSpan(binding.dark, target == binding.selectedLink, icon), start, end, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
        }
        renderer.setParsedMarkdown(view, view.prepareMarkdown(styled))
        view.movementMethod = io.noties.markwon.ext.tables.TableAwareMovementMethod.create()
        view.highlightColor = android.graphics.Color.TRANSPARENT
    })
}

private object CitationIcons {
    private val cache = android.util.LruCache<String, android.graphics.Bitmap>(128)
    private val client = okhttp3.OkHttpClient.Builder().callTimeout(8, java.util.concurrent.TimeUnit.SECONDS).build()

    fun load(url: String): android.graphics.Bitmap? {
        cache.get(url)?.let { return it }
        return runCatching {
            client.newCall(okhttp3.Request.Builder().url(url).build()).execute().use { response ->
                if (!response.isSuccessful) return@use null
                val source = response.body?.source() ?: return@use null
                source.request(262145)
                if (source.buffer.size > 262144) return@use null
                val bytes = source.buffer.readByteArray()
                val bounds = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
                android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
                val options = android.graphics.BitmapFactory.Options().apply {
                    inSampleSize = (maxOf(bounds.outWidth, bounds.outHeight) / 64).coerceAtLeast(1)
                }
                android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)?.also { cache.put(url, it) }
            }
        }.getOrNull()
    }
}

private class CitationBadgeSpan(private val dark: Boolean, private val selected: Boolean, private val icon: android.graphics.Bitmap?) : android.text.style.ReplacementSpan() {
    private fun badgePaint(paint: android.graphics.Paint) = android.graphics.Paint(paint).apply {
        textSize = paint.textSize * 0.72f
        isUnderlineText = false
        typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
    }

    override fun getSize(paint: android.graphics.Paint, text: CharSequence, start: Int, end: Int,
        fm: android.graphics.Paint.FontMetricsInt?): Int {
        val badge = badgePaint(paint)
        return kotlin.math.ceil(badge.measureText(text, start + 3, end) + paint.textSize * 1.85f).toInt()
    }

    override fun draw(canvas: android.graphics.Canvas, text: CharSequence, start: Int, end: Int,
        x: Float, top: Int, y: Int, bottom: Int, paint: android.graphics.Paint) {
        val badge = badgePaint(paint)
        val padding = paint.textSize * 0.3f
        val bounds = android.graphics.RectF(x + 2, y + badge.ascent() - padding * 0.45f,
            x + getSize(paint, text, start, end, null) - 2, y + badge.descent() + padding * 0.45f)
        badge.color = android.graphics.Color.parseColor(if (selected) "#BDD6FF" else if (dark) "#303030" else "#F5F5F5")
        canvas.drawRoundRect(bounds, bounds.height() / 2, bounds.height() / 2, badge)
        badge.style = android.graphics.Paint.Style.STROKE
        badge.strokeWidth = paint.textSize * 0.035f
        badge.color = android.graphics.Color.parseColor(if (dark) "#606060" else "#CCCCCC")
        canvas.drawRoundRect(bounds, bounds.height() / 2, bounds.height() / 2, badge)
        badge.style = android.graphics.Paint.Style.FILL
        badge.color = android.graphics.Color.parseColor(if (dark && !selected) "#EEEEEE" else "#404040")
        val iconSize = paint.textSize * 0.72f
        if (icon != null) {
            val iconTop = bounds.centerY() - iconSize / 2
            canvas.drawBitmap(icon, null, android.graphics.RectF(x + padding, iconTop, x + padding + iconSize, iconTop + iconSize), badge)
        } else canvas.drawText("↗", x + padding, y.toFloat(), badge)
        canvas.drawText(text, start + 3, end, x + padding + paint.textSize, y.toFloat(), badge)
    }
}

private data class MarkdownBlock(val body: CharSequence, val language: String? = null)

private data class MarkdownBinding(
    val body: CharSequence,
    val textSize: Float,
    val foreground: Int,
    val link: Int,
    val dark: Boolean,
    val selectedLink: String?,
    val icons: Map<String, android.graphics.Bitmap>,
    val sources: List<CitationSource>,
)

@Composable
fun MessageView(message: DisplayMessage, regent: Boolean = false, isLatest: Boolean = false, fallbackModel: String? = null,
                canRetry: Boolean = false, canEdit: Boolean = false, canFork: Boolean = false,
                onAction: (String, String?) -> Unit = { _, _ -> }) {
    val outline = MaterialTheme.colorScheme.outline
    val shadowColor = suzentShadow
    val view = LocalView.current
    var menu by remember { mutableStateOf(false) }
    val actionsLabel = stringResource(R.string.message_actions)
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
    if (message.role in listOf("system_triggered", "trigger")) {
        systemReminder(message.text)?.let { SystemReminderView(it, message.citationSources) }
    } else if (message.role == "user") Box(Modifier.fillMaxWidth().padding(start = 40.dp), contentAlignment = androidx.compose.ui.Alignment.CenterEnd) {
        val dark = isSystemInDarkTheme()
        val bubbleShape = RoundedCornerShape(PresentationTokens.radiusBubble.dp)
        val bubble = if (regent) Modifier
            .background(Color(if (dark) 0xFF27272A else 0xFFF5F5F5), bubbleShape)
            .border(1.dp, (if (dark) Color.White else Color.Black).copy(alpha = if (dark) .14f else .18f), bubbleShape)
        else Modifier.drawBehind {
            drawRect(shadowColor, topLeft = Offset(PresentationTokens.shadowOffset.dp.toPx(), PresentationTokens.shadowOffset.dp.toPx()), size = size)
        }.background(Color(PresentationTokens.yellow)).border(PresentationTokens.borderWidth.dp, outline)
        // The text inside keeps long-press for selection; the bubble's padding opens the actions menu.
        Box(Modifier.padding(end = if (regent) 0.dp else PresentationTokens.shadowOffset.dp,
            bottom = if (regent) 0.dp else PresentationTokens.shadowOffset.dp)
            .widthIn(max = 320.dp).then(bubble)
            .pointerInput(Unit) { detectTapGestures(onLongPress = { view.suzentHaptic(SuzentHaptic.LongPress); menu = true }) }
            .semantics { onLongClick(actionsLabel) { menu = true; true } }
            .padding(PresentationTokens.spaceMedium.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceSmall.dp)) {
                message.files.forEach { AttachmentChip(it.filename, it.mimeType, color = Color.Black) }
                if (message.text.isNotEmpty()) SelectionContainer { Text(message.text, color = if (regent) MaterialTheme.colorScheme.onSurface else Color.Black, fontSize = PresentationTokens.typeChat.sp) }
            }
        }
    } else Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        ActivityTurn(message.parts, regent = regent, compact = !isLatest, workedSeconds = message.workedSeconds, citationSources = message.citationSources)
    }
    message.reaction?.takeIf { it.isNotEmpty() }?.let { reaction ->
        val label = stringResource(R.string.regent_reaction, reaction)
        val dark = isSystemInDarkTheme()
        // Tucked over the bubble's bottom edge like the desktop tapback.
        Text(reaction, fontSize = PresentationTokens.typeCaption.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            modifier = Modifier.align(androidx.compose.ui.Alignment.End).padding(end = 12.dp)
            .layout { measurable, constraints ->
                val placeable = measurable.measure(constraints)
                val overlap = 18.dp.roundToPx()
                layout(placeable.width, (placeable.height - overlap).coerceAtLeast(0)) { placeable.place(0, -overlap) }
            }
            .background(Color(if (dark) 0xFF27272A else 0xFFF5F5F5), RoundedCornerShape(50))
            .border(1.dp, (if (dark) Color.White else Color.Black).copy(alpha = if (dark) .14f else .12f), RoundedCornerShape(50))
            .widthIn(min = 28.dp).heightIn(min = 24.dp).padding(horizontal = 6.dp, vertical = 2.dp)
            .semantics { contentDescription = label })
    }
    if (message.role in listOf("user", "assistant")) MessageFooter(message, fallbackModel, canRetry, canEdit, canFork,
        showActions = isLatest, menu = menu, onMenu = { menu = it }, onAction = onAction)
    }
}

@Composable
private fun SystemReminderView(reminder: SystemReminder, sources: List<CitationSource>) {
    var expanded by remember(reminder.content) { mutableStateOf(!reminder.initiallyCollapsed) }
    val expandedLabel = stringResource(R.string.reminder_expanded)
    val collapsedLabel = stringResource(R.string.reminder_collapsed)
    val outline = MaterialTheme.colorScheme.outlineVariant
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    Column(Modifier.fillMaxWidth().drawBehind {
        drawRect(outline, size = androidx.compose.ui.geometry.Size(3.dp.toPx(), size.height))
    }.padding(start = 14.dp, top = 4.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(Modifier.fillMaxWidth().then(if (reminder.body.isNotEmpty()) Modifier
            .clickable(role = androidx.compose.ui.semantics.Role.Button) { expanded = !expanded }
            .semantics { stateDescription = if (expanded) expandedLabel else collapsedLabel }
            .heightIn(min = 44.dp) else Modifier), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Icon(painterResource(R.drawable.ic_clock), contentDescription = null, tint = muted, modifier = Modifier.padding(end = 8.dp).size(14.dp))
            Text(reminder.title, color = muted, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold,
                fontSize = PresentationTokens.typeMeta.sp, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            if (reminder.body.isNotEmpty()) SuzentChevron(expanded, Modifier.padding(horizontal = 8.dp), tint = muted)
        }
        if (expanded && reminder.body.isNotEmpty()) MarkdownText(reminder.body, citationSources = sources, textSize = PresentationTokens.typeLabel.toFloat())
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MessageFooter(message: DisplayMessage, fallbackModel: String?, canRetry: Boolean, canEdit: Boolean,
                          canFork: Boolean, showActions: Boolean, menu: Boolean, onMenu: (Boolean) -> Unit,
                          onAction: (String, String?) -> Unit) {
    val context = LocalContext.current
    val view = LocalView.current
    var copied by remember(message.text) { mutableStateOf(false) }
    var action by remember { mutableStateOf<String?>(null) }
    var edited by remember(message.text) { mutableStateOf(message.text) }
    var sourcesOpen by remember { mutableStateOf(false) }
    var modelDetails by remember { mutableStateOf<String?>(null) }
    val user = message.role == "user"
    val ink = MaterialTheme.colorScheme.onSurfaceVariant
    val hasText = message.text.isNotBlank()
    val hasSources = !user && message.citationSources.isNotEmpty()
    val hasMenu = hasText || canEdit || canRetry || canFork || hasSources
    val actionsLabel = stringResource(R.string.message_actions)
    LaunchedEffect(copied) { if (copied) { kotlinx.coroutines.delay(1800); copied = false } }
    fun copy() {
        val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
        clipboard.setPrimaryClip(android.content.ClipData.newPlainText("", message.text)); copied = true
        view.suzentHaptic(SuzentHaptic.Light)
    }
    Box(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth()
            .pointerInput(hasMenu) { if (hasMenu) detectTapGestures(onLongPress = { view.suzentHaptic(SuzentHaptic.LongPress); onMenu(true) }) }
            .semantics { if (hasMenu) onLongClick(actionsLabel) { onMenu(true); true } },
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            if (user) Spacer(Modifier.weight(1f))
            if (showActions) {
                if (hasText) IconButton(modifier = Modifier.size(32.dp), onClick = { copy() }) {
                    Icon(painterResource(if (copied) R.drawable.ic_message_check else R.drawable.ic_message_copy), stringResource(if (copied) R.string.message_copied else R.string.message_copy), Modifier.size(18.dp), tint = ink)
                }
                if (hasText) IconButton(modifier = Modifier.size(32.dp), onClick = { shareText(context, message.text) }) {
                    Icon(painterResource(R.drawable.ic_share), stringResource(R.string.message_share), Modifier.size(18.dp), tint = ink)
                }
                if (canEdit) IconButton(modifier = Modifier.size(32.dp), onClick = { edited = message.text; action = "edit" }) { Icon(painterResource(R.drawable.ic_chat_rename), stringResource(R.string.message_edit), Modifier.size(18.dp), tint = ink) }
                if (canRetry) IconButton(modifier = Modifier.size(32.dp), onClick = { action = "retry" }) { Icon(painterResource(R.drawable.ic_message_retry), stringResource(R.string.message_retry), Modifier.size(18.dp), tint = ink) }
                if (canFork) IconButton(modifier = Modifier.size(32.dp), onClick = { action = "fork" }) { Icon(painterResource(R.drawable.ic_message_fork), stringResource(R.string.message_fork), Modifier.size(18.dp), tint = ink) }
            }
            if (hasSources) TextButton(onClick = { sourcesOpen = true }, contentPadding = PaddingValues(horizontal = 4.dp), shape = RectangleShape,
                modifier = Modifier.widthIn(min = 32.dp).height(32.dp)
                    .semantics(mergeDescendants = true) { contentDescription = context.getString(R.string.message_sources, message.citationSources.size) }) {
                Icon(painterResource(R.drawable.ic_globe), contentDescription = null, modifier = Modifier.size(14.dp), tint = ink)
                Spacer(Modifier.width(4.dp))
                Text("${message.citationSources.size}", fontSize = PresentationTokens.typeMeta.sp, color = ink, maxLines = 1)
            }
            if (showActions && !user) (message.model ?: fallbackModel)?.takeIf { it.isNotBlank() }?.let { model ->
                Text(model.substringAfter('/'), Modifier.weight(1f, fill = false)
                    .clickable(onClickLabel = stringResource(R.string.message_model)) { modelDetails = model }
                    .border(1.dp, MaterialTheme.colorScheme.outlineVariant).padding(horizontal = 6.dp, vertical = 3.dp),
                    fontSize = PresentationTokens.typeMeta.sp, fontWeight = FontWeight.Medium, color = ink,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            message.timestamp?.let { raw ->
                Text(formattedTimestamp(raw), Modifier.widthIn(max = 120.dp), fontSize = PresentationTokens.typeMeta.sp, color = ink,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (showActions && user) Text(stringResource(R.string.you), fontSize = PresentationTokens.typeMeta.sp, color = ink, maxLines = 1)
        }
        SuzentMenu(expanded = menu && hasMenu, onDismissRequest = { onMenu(false) }) {
            if (hasText) {
                SuzentMenuItem(stringResource(R.string.message_copy), R.drawable.ic_message_copy) { onMenu(false); copy() }
                SuzentMenuItem(stringResource(R.string.message_share), R.drawable.ic_share) { onMenu(false); shareText(context, message.text) }
            }
            if (canEdit) SuzentMenuItem(stringResource(R.string.message_edit), R.drawable.ic_chat_rename) { onMenu(false); edited = message.text; action = "edit" }
            if (canRetry) SuzentMenuItem(stringResource(R.string.message_retry), R.drawable.ic_message_retry) { onMenu(false); action = "retry" }
            if (canFork) SuzentMenuItem(stringResource(R.string.message_fork), R.drawable.ic_message_fork) { onMenu(false); action = "fork" }
            if (hasSources) SuzentMenuItem(stringResource(R.string.message_sources, message.citationSources.size), R.drawable.ic_globe) { onMenu(false); sourcesOpen = true }
        }
    }
    modelDetails?.let { model ->
        AlertDialog(onDismissRequest = { modelDetails = null }, title = { Text(stringResource(R.string.message_model)) },
            text = { SelectionContainer { Text(model) } },
            confirmButton = { TextButton(onClick = { modelDetails = null }) { Text(stringResource(android.R.string.ok)) } })
    }
    action?.let { selected ->
        if (selected == "edit") SuzentInputSheet(title = stringResource(R.string.message_edit), value = edited, onValueChange = { edited = it },
            placeholder = stringResource(R.string.message), saveLabel = stringResource(R.string.send), saveEnabled = edited.isNotBlank(),
            dismiss = { action = null }, save = { onAction("edit", edited); action = null }, multiline = true)
        else {
            val title = stringResource(if (selected == "fork") R.string.message_fork else R.string.message_retry)
            AlertDialog(onDismissRequest = { action = null }, title = { Text(title) },
                text = { Text(stringResource(if (selected == "fork") R.string.message_fork_help else R.string.message_retry_help)) },
                confirmButton = { TextButton(onClick = { onAction(selected, null); action = null }) { Text(title) } },
                dismissButton = { TextButton(onClick = { action = null }) { Text(stringResource(R.string.cancel_link)) } })
        }
    }
    if (sourcesOpen) ModalBottomSheet(onDismissRequest = { sourcesOpen = false }, shape = RectangleShape) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(stringResource(R.string.citation_sources), style = MaterialTheme.typography.titleLarge)
            message.citationSources.distinctBy { it.id }.forEach { source ->
                Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(source.title, fontWeight = FontWeight.SemiBold)
                    if (source.snippet.isNotBlank()) Text(source.snippet, maxLines = 5, style = MaterialTheme.typography.bodySmall)
                    if (Uri.parse(source.url).scheme in listOf("http", "https")) TextButton(onClick = {
                        androidx.browser.customtabs.CustomTabsIntent.Builder().build().launchUrl(context, Uri.parse(source.url))
                    }, shape = RectangleShape) { Text(stringResource(R.string.citation_read)) }
                }
            }
        }
    }
}

/** Long-press menu in the Suzent style: square panel, 2 px rule, hard offset shadow. */
@Composable
fun SuzentMenu(expanded: Boolean, onDismissRequest: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    val outline = MaterialTheme.colorScheme.outline
    val menuShadow = suzentShadow
    val menuSurface = MaterialTheme.colorScheme.surface
    val menuShadowSize = PresentationTokens.shadowOffsetOverlay.dp
    DropdownMenu(expanded = expanded, onDismissRequest = onDismissRequest, shape = RectangleShape,
        containerColor = Color.Transparent, tonalElevation = 0.dp, shadowElevation = 0.dp,
        modifier = Modifier.width(260.dp)) {
        // The popup's scroll container clips anything drawn outside its bounds, so the offset is
        // reserved inside the content: shadow first, opaque panel over it.
        Box(Modifier.fillMaxWidth().drawBehind {
            val offset = menuShadowSize.toPx()
            drawRect(menuShadow, topLeft = Offset(offset, offset), size = size)
        }.padding(end = menuShadowSize, bottom = menuShadowSize)) {
            Column(Modifier.fillMaxWidth().background(menuSurface).border(PresentationTokens.borderWidth.dp, outline), content = content)
        }
    }
}

@Composable
fun SuzentMenuItem(label: String, icon: Int, enabled: Boolean = true, danger: Boolean = false, action: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val error = MaterialTheme.colorScheme.error
    val background = if (pressed) { if (danger) error else Color(PresentationTokens.yellow) } else Color.Transparent
    val foreground = (if (pressed) { if (danger) MaterialTheme.colorScheme.onError else Color.Black } else if (danger) error else MaterialTheme.colorScheme.onSurface)
        .copy(alpha = if (enabled) 1f else DisabledAlpha)
    Row(Modifier.fillMaxWidth().background(background).clickable(interactionSource = interaction, indication = null, enabled = enabled, onClick = action)
        .heightIn(min = 44.dp).padding(horizontal = 12.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Icon(painterResource(icon), null, tint = foreground, modifier = Modifier.padding(end = 10.dp).size(18.dp))
        Text(label, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = foreground)
    }
}

/** Text-input flow (rename, edit and resend): square sheet with title, field and Cancel/Save. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SuzentInputSheet(title: String, value: String, onValueChange: (String) -> Unit, placeholder: String, saveLabel: String,
                     saveEnabled: Boolean, dismiss: () -> Unit, save: () -> Unit, multiline: Boolean = false) {
    val focus = remember { FocusRequester() }
    ModalBottomSheet(onDismissRequest = dismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        shape = RectangleShape, containerColor = MaterialTheme.colorScheme.surface) {
        Column(Modifier.fillMaxWidth().imePadding().padding(horizontal = PresentationTokens.spacePage.dp).padding(bottom = PresentationTokens.spacePage.dp),
            verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceMedium.dp)) {
            LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            SuzentTextInput(value, onValueChange, placeholder, Modifier.focusRequester(focus), multiline = multiline)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                SuzentTextButton(onClick = dismiss) { Text(stringResource(android.R.string.cancel)) }
                SuzentTextButton(onClick = save, enabled = saveEnabled) { Text(saveLabel, fontWeight = FontWeight.SemiBold) }
            }
        }
    }
}

/** Transient error toast: square, 2 px rule, error surface, Dismiss, gone after 6 s (longer if accessibility asks). */
@Composable
fun SuzentErrorHost(model: MobileModel, modifier: Modifier = Modifier) {
    val host = remember { SnackbarHostState() }
    val accessibility = LocalAccessibilityManager.current
    val dismissLabel = stringResource(R.string.dismiss)
    LaunchedEffect(model.error) {
        val message = model.error ?: return@LaunchedEffect
        val timeout = accessibility?.calculateRecommendedTimeoutMillis(6000L, false, true, true) ?: 6000L
        withTimeoutOrNull(timeout) { host.showSnackbar(message, actionLabel = dismissLabel, duration = SnackbarDuration.Indefinite) }
        if (model.error == message) model.error = null
    }
    val surface = Color(if (isSystemInDarkTheme()) PresentationTokens.error_surface_dark else PresentationTokens.error_surface)
    SnackbarHost(host, modifier) { data ->
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp).background(surface)
            .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).padding(start = 12.dp),
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text(data.visuals.message, Modifier.weight(1f).padding(vertical = 12.dp), color = MaterialTheme.colorScheme.onSurface,
                fontSize = PresentationTokens.typeCaption.sp)
            SuzentTextButton(onClick = { data.dismiss() }, modifier = Modifier.heightIn(min = PresentationTokens.controlHeight.dp)) {
                Text(data.visuals.actionLabel ?: dismissLabel, fontSize = PresentationTokens.typeCaption.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}


@Composable
fun SuzentTextButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    contentPadding: PaddingValues = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
    content: @Composable RowScope.() -> Unit,
) {
    TextButton(onClick = onClick, modifier = modifier, enabled = enabled, shape = RectangleShape, contentPadding = contentPadding,
        colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.onSurface,
            disabledContentColor = MaterialTheme.colorScheme.onSurface.copy(alpha = DisabledAlpha)), content = content)
}

@Composable
fun SuzentAction(label: String, onClick: () -> Unit, prominent: Boolean = false, enabled: Boolean = true, compact: Boolean = false, quiet: Boolean = false,
                 destructive: Boolean = false, leadingIcon: Int? = null) {
    val outline = MaterialTheme.colorScheme.outline
    val shadowColor = suzentShadow
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val shadow = if (quiet) 0.dp else PresentationTokens.shadowOffset.dp
    Box((if (compact) Modifier else Modifier.fillMaxWidth()).alpha(if (enabled) 1f else DisabledAlpha).drawBehind {
        val offset = shadow.toPx()
        if (!quiet && !pressed) drawRect(shadowColor, topLeft = Offset(offset, offset),
            size = androidx.compose.ui.geometry.Size((size.width - offset).coerceAtLeast(0f), (size.height - offset).coerceAtLeast(0f)))
    }.padding(end = shadow, bottom = shadow)) {
        Row((if (compact) Modifier else Modifier.fillMaxWidth())
            .offset(x = if (pressed) shadow else 0.dp, y = if (pressed) shadow else 0.dp)
            .background(if (prominent) Color(PresentationTokens.blue) else MaterialTheme.colorScheme.surface)
            .then(if (quiet) Modifier else Modifier.border(PresentationTokens.borderWidth.dp, outline))
            .clickable(interactionSource = interaction, indication = null, enabled = enabled, role = androidx.compose.ui.semantics.Role.Button, onClick = onClick)
            .heightIn(min = PresentationTokens.controlHeight.dp)
            .padding(horizontal = (if (compact) PresentationTokens.spaceMedium else PresentationTokens.spacePage).dp, vertical = PresentationTokens.spaceSmall.dp),
            horizontalArrangement = Arrangement.Center, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            val foreground = if (destructive) MaterialTheme.colorScheme.error else if (prominent) Color.White else MaterialTheme.colorScheme.onSurface
            if (leadingIcon != null) Icon(painterResource(leadingIcon), contentDescription = null, tint = foreground,
                modifier = Modifier.padding(end = 6.dp).size(18.dp))
            Text(label, fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold, color = foreground)
        }
    }
}

/** Plain icon control: 44 target, no border or shadow, quiet pressed fill (desktop header icons). */
@Composable
fun SuzentIconButton(onClick: () -> Unit, label: String, modifier: Modifier = Modifier, enabled: Boolean = true,
                     content: @Composable () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    Box(modifier.size(PresentationTokens.controlHeight.dp).alpha(if (enabled) 1f else DisabledAlpha)
        .background(if (pressed) MaterialTheme.colorScheme.onSurface.copy(alpha = PressedAlpha) else Color.Transparent)
        .clickable(interactionSource = interaction, indication = null, enabled = enabled,
            role = androidx.compose.ui.semantics.Role.Button, onClick = onClick)
        .semantics { contentDescription = label },
        contentAlignment = androidx.compose.ui.Alignment.Center) {
        CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onSurface) { content() }
    }
}

/** Plain navigation row, mirroring the desktop sidebar's New chat row: icon, label, hover fill. */
@Composable
fun SuzentRowButton(label: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true,
                    leadingIcon: Int? = null) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    Row(modifier.fillMaxWidth().alpha(if (enabled) 1f else DisabledAlpha)
        .background(if (pressed) MaterialTheme.colorScheme.onSurface.copy(alpha = PressedAlpha) else Color.Transparent)
        .clickable(interactionSource = interaction, indication = null, enabled = enabled,
            role = androidx.compose.ui.semantics.Role.Button, onClick = onClick)
        .heightIn(min = 40.dp)
        .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        if (leadingIcon != null) Icon(painterResource(leadingIcon), null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(18.dp))
        Text(label, fontSize = PresentationTokens.typeCaption.sp, fontWeight = FontWeight.Medium,
            color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
    }
}

@Composable
fun SuzentTextInput(value: String, onValueChange: (String) -> Unit, placeholder: String, modifier: Modifier = Modifier, multiline: Boolean = false) {
    val interaction = remember { MutableInteractionSource() }
    val focused by interaction.collectIsFocusedAsState()
    androidx.compose.foundation.text.BasicTextField(value, onValueChange, singleLine = !multiline,
        minLines = if (multiline) 3 else 1, maxLines = if (multiline) 6 else 1, interactionSource = interaction,
        textStyle = MaterialTheme.typography.bodyMedium.copy(color = MaterialTheme.colorScheme.onSurface),
        cursorBrush = androidx.compose.ui.graphics.SolidColor(suzentLink),
        modifier = modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, if (focused) suzentLink else MaterialTheme.colorScheme.outline)
            .heightIn(min = PresentationTokens.controlHeight.dp).padding(PresentationTokens.spaceMedium.dp),
        decorationBox = { input -> Box { if (value.isEmpty()) Text(placeholder, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = PresentationTokens.typeControl.sp); input() } })
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
        val shadowColor = suzentShadow
        Box(Modifier.padding(end = PresentationTokens.shadowOffsetOverlay.dp,
            bottom = PresentationTokens.shadowOffsetOverlay.dp).drawBehind {
            val offset = PresentationTokens.shadowOffsetOverlay.dp.toPx()
            // Full-size rect offset into the reserved padding; without `size` it stayed inside the face and was painted over.
            drawRect(shadowColor, topLeft = Offset(offset, offset), size = size)
        }.size(90.dp, 40.dp).background(MaterialTheme.colorScheme.surface)
            .border(PresentationTokens.borderWidth.dp, outline), contentAlignment = androidx.compose.ui.Alignment.Center) {
            Image(painterResource(R.drawable.suzent_logo), contentDescription = "Suzent", modifier = Modifier.size(26.dp))
        }
    }
}

@Composable
fun ActivityContent(parts: List<MessagePart>, live: Boolean, citationSources: List<CitationSource> = emptyList(), regent: Boolean = false) {
    val chunks = remember(parts) { activityChunks(parts) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        chunks.forEachIndexed { index, chunk ->
            key(index) {
                if (chunk.first().type == "text") {
                    Box(if (regent) Modifier.background(MaterialTheme.colorScheme.onSurface.copy(alpha = .045f), RoundedCornerShape(PresentationTokens.radiusBubble.dp)).padding(12.dp) else Modifier) {
                        MarkdownText(chunk.first().text, citationSources)
                    }
                }
                else ActivityRail(chunk, live, index == chunks.lastIndex)
            }
        }
    }
}

@Composable
fun ApprovalCards(model: MobileModel) {
    val view = LocalView.current
    Column(verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceSmall.dp)) {
    model.pendingApprovals.forEach { request ->
        key(request.id) {
            var showAll by remember { mutableStateOf(false) }
            var overflowing by remember { mutableStateOf(false) }
            Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
                .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)) {
                Text(stringResource(R.string.approval_required), Modifier.fillMaxWidth().background(Color(PresentationTokens.yellow)).padding(12.dp), color = Color.Black, fontWeight = FontWeight.Bold)
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(request.toolName, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)
                    Text(stringResource(R.string.approval_backend), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    SelectionContainer {
                        Text(request.args, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall,
                            maxLines = if (showAll) Int.MAX_VALUE else 3, overflow = TextOverflow.Ellipsis,
                            onTextLayout = { if (!showAll) overflowing = it.hasVisualOverflow })
                    }
                    if (overflowing || showAll) SuzentTextButton(onClick = { showAll = !showAll }, contentPadding = PaddingValues(vertical = 4.dp)) {
                        Text(stringResource(if (showAll) R.string.approval_show_less else R.string.approval_show_all),
                            fontSize = PresentationTokens.typeLabel.sp, fontWeight = FontWeight.SemiBold, color = suzentLink)
                    }
                    if (request.reason.isNotEmpty()) Text(request.reason, style = MaterialTheme.typography.bodySmall)
                    if (model.device?.permissions?.approveTools == true && request.actions.isNotEmpty()) {
                        // Side by side when they fit, stacked on narrow screens or large text.
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            request.actions.forEach { action ->
                                val allow = action.behavior == "allow"
                                SuzentAction(stringResource(if (allow) R.string.allow_once else R.string.reject_tool), {
                                    view.suzentHaptic(if (allow) SuzentHaptic.Confirm else SuzentHaptic.Reject)
                                    model.chooseApproval(request, action)
                                }, prominent = allow, enabled = !model.approvalBusy, compact = true,
                                    leadingIcon = if (model.approvalChoices[request.id] == action.id) R.drawable.ic_message_check else null)
                            }
                        }
                        Text(stringResource(R.string.approval_batch), style = MaterialTheme.typography.bodySmall)
                    } else Text(stringResource(R.string.approval_desktop_only), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
    }
}


@Composable
fun GreetingCube(engaged: Boolean, modifier: Modifier = Modifier) {
    val reduced = !android.animation.ValueAnimator.areAnimatorsEnabled()
    val seconds = remember { mutableDoubleStateOf(0.0) }
    LaunchedEffect(reduced) {
        if (reduced) return@LaunchedEffect
        var previous = 0L
        while (true) withFrameNanos { now ->
            if (previous != 0L) seconds.doubleValue += minOf((now - previous) / 1_000_000_000.0, .05)
            previous = now
        }
    }
    val ink = MaterialTheme.colorScheme.onSurface.toArgb().toLong() and 0xFFFFFFFFL
    Canvas(modifier) {
        val marks = GreetingCubeScene.frame(seconds.doubleValue, engaged, reduced, ink)
        scale(size.width / 160f, size.height / 160f, pivot = Offset.Zero) {
            marks.forEach { mark ->
                val path = androidx.compose.ui.graphics.Path().apply {
                    mark.points.forEachIndexed { i, p -> if (i == 0) moveTo(p.x.toFloat(), p.y.toFloat()) else lineTo(p.x.toFloat(), p.y.toFloat()) }
                    if (mark.points.size > 2) close()
                }
                val color = Color(mark.color).copy(alpha = mark.alpha.toFloat())
                if (mark.stroke) drawPath(path, color, style = Stroke(mark.width.toFloat())) else drawPath(path, color)
            }
        }
    }
}

@Composable
fun SuzentSelectionTrigger(value: String, onClick: () -> Unit, enabled: Boolean = true, prefix: String? = null) {
    val outline = MaterialTheme.colorScheme.outline
    val shadowColor = suzentShadow
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val offset = PresentationTokens.shadowOffset.dp
    Row(Modifier.alpha(if (enabled) 1f else DisabledAlpha).padding(end = offset, bottom = offset)
        .drawBehind { if (!pressed) drawRect(shadowColor, topLeft = Offset(offset.toPx(), offset.toPx()), size = size) }
        .offset(x = if (pressed) offset else 0.dp, y = if (pressed) offset else 0.dp)
        .background(MaterialTheme.colorScheme.surface).border(PresentationTokens.borderWidth.dp, outline)
        .clickable(interactionSource = interaction, indication = null, enabled = enabled, role = androidx.compose.ui.semantics.Role.Button, onClick = onClick)
        .heightIn(min = PresentationTokens.controlHeight.dp).padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (prefix != null) Text(prefix, fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
        Text(value, Modifier.weight(1f, fill = false), fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.MiddleEllipsis)
        Icon(painterResource(R.drawable.ic_chevron_down), contentDescription = null, tint = outline, modifier = Modifier.size(14.dp))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SuzentSelectionPanel(title: String, options: List<Pair<String, String>>, selected: String, dismiss: () -> Unit, choose: (String) -> Unit) {
    val outline = MaterialTheme.colorScheme.outline
    val shadowColor = suzentShadow
    ModalBottomSheet(onDismissRequest = dismiss, containerColor = Color.Transparent,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), dragHandle = null, shape = RectangleShape) {
        Column(Modifier.fillMaxWidth().padding(16.dp).drawBehind {
            val offset = PresentationTokens.shadowOffsetHeavy.dp.toPx()
            drawRect(shadowColor, topLeft = Offset(offset, offset), size = size)
        }.background(MaterialTheme.colorScheme.surface).border(2.dp, outline)) {
            val dismissLabel = stringResource(R.string.dismiss)
            Row(Modifier.fillMaxWidth().background(Color.Black).padding(start = 16.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text(title, Modifier.weight(1f), fontFamily = FontFamily.Monospace, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color.White)
                SuzentIconButton(onClick = dismiss, label = dismissLabel) {
                    Icon(painterResource(R.drawable.ic_close), contentDescription = null, tint = Color.White, modifier = Modifier.size(20.dp))
                }
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
                        if (active) Icon(painterResource(R.drawable.ic_message_check), contentDescription = null, tint = Color.Black, modifier = Modifier.size(18.dp))
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                }
            }
        }
    }
}


private fun reconnectSample(phase: Float, vararg frames: Pair<Float, Float>): Float {
    for (index in 1 until frames.size) {
        if (phase <= frames[index].first) {
            val (start, from) = frames[index - 1]
            val (end, to) = frames[index]
            val t = ((phase - start) / (end - start)).coerceIn(0f, 1f)
            return from + (to - from) * t * t * (3f - 2f * t)
        }
    }
    return frames.last().second
}

@Composable
fun ReconnectIndicator(active: Boolean) {
    val owner = androidx.lifecycle.compose.LocalLifecycleOwner.current
    val lifecycle by owner.lifecycle.currentStateFlow.collectAsState()
    val animated = active && android.animation.ValueAnimator.areAnimatorsEnabled() &&
        lifecycle.isAtLeast(androidx.lifecycle.Lifecycle.State.RESUMED)
    val p = if (animated) {
        val transition = rememberInfiniteTransition(label = "reconnect")
        val value by transition.animateFloat(0f, 1f,
            infiniteRepeatable(tween(7800, easing = LinearEasing)), label = "curious logo")
        value
    } else 0f
    val gaze = reconnectSample(p, 0f to 0f, .09f to 0f, .15f to -1.5f, .28f to -1.5f, .34f to 0f, .40f to 1.33f, .53f to 1.33f, .60f to 0f, 1f to 0f)
    val eyeY = reconnectSample(p, 0f to 0f, .15f to -.33f, .28f to -.33f, .34f to 0f, .40f to -.67f, .53f to -.67f, .60f to -1f, .68f to -1f, .76f to 0f, 1f to 0f)
    val lift = reconnectSample(p, 0f to 0f, .09f to 0f, .18f to -3f, .27f to -3f, .35f to 1f, .43f to -5f, .51f to -5f, .57f to 2f, .64f to -7f, .72f to 1f, .76f to 0f, 1f to 0f)
    val tilt = reconnectSample(p, 0f to 0f, .09f to 0f, .18f to -7f, .27f to -7f, .35f to 2f, .43f to 6f, .51f to 6f, .57f to -2f, .64f to 0f, 1f to 0f)
    val blink = reconnectSample(p, 0f to 1f, .12f to 1f, .145f to .12f, .17f to 1f, .31f to 1f, .335f to .12f, .36f to 1f, .55f to 1f, .575f to .12f, .60f to 1f, .71f to 1f, .735f to .12f, .76f to 1f, 1f to 1f)
    val ink = MaterialTheme.colorScheme.onSurface
    Box(Modifier.size(210.dp, 130.dp).semantics { contentDescription = "Suzent" }, contentAlignment = androidx.compose.ui.Alignment.Center) {
        Canvas(Modifier.size(72.dp).graphicsLayer {
            rotationZ = tilt; translationY = lift * density
            transformOrigin = androidx.compose.ui.graphics.TransformOrigin(.5f, .8f)
        }) {
            val scale = size.width / 24f
            SuzentLogoGeometry.rectangles.forEachIndexed { index, rect ->
                val eye = index > 0
                val height = rect[3] * if (eye) blink else 1f
                drawRoundRect(if (eye) Color.White else Color.Black,
                    topLeft = Offset((rect[0] + if (eye) gaze else 0f) * scale,
                        (rect[1] + if (eye) eyeY + (rect[3] - height) / 2f else 0f) * scale),
                    size = androidx.compose.ui.geometry.Size(rect[2] * scale, height * scale),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(minOf(rect[4], height / 2f) * scale))
            }
        }
        if (animated) Canvas(Modifier.fillMaxSize()) {
            val opacity = reconnectSample(p, 0f to 0f, .05f to 0f, .12f to 1f, .21f to 0f, 1f to 0f)
            val x = size.width / 2f + (-92f + reconnectSample(p, 0f to -8f, .21f to 13f, 1f to 13f)).dp.toPx()
            drawRect(androidx.compose.ui.graphics.Brush.horizontalGradient(listOf(Color.Transparent, ink.copy(alpha = .65f * opacity)), x, x + 44.dp.toPx()),
                topLeft = Offset(x, size.height / 2f - 10.dp.toPx()), size = androidx.compose.ui.geometry.Size(44.dp.toPx(), 1.dp.toPx()))
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
            }.background(suzentLink))
        }
    }
}

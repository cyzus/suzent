package com.suzent.mobile

import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.selection.toggleable
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
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.painterResource
import kotlin.math.sin
import kotlin.math.cos
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
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
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.asImageBitmap
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
        onSurfaceVariant = Color(PresentationTokens.muted_dark)
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
        titleMedium = typography.titleMedium.copy(fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold),
        labelMedium = typography.labelMedium.copy(fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold),
        bodyMedium = typography.bodyMedium.copy(fontSize = PresentationTokens.typeControl.sp),
        bodyLarge = typography.bodyLarge.copy(fontSize = PresentationTokens.typeBody.sp),
        bodySmall = typography.bodySmall.copy(fontSize = PresentationTokens.typeCaption.sp)
    ), shapes = Shapes(
        extraSmall = RoundedCornerShape(0.dp), small = RoundedCornerShape(0.dp), medium = RoundedCornerShape(0.dp), large = RoundedCornerShape(0.dp), extraLarge = RoundedCornerShape(0.dp)
    ), content = content)
}

val suzentShadow: Color
    @Composable get() = Color(if (isSystemInDarkTheme()) PresentationTokens.shadow_dark else PresentationTokens.black)

val suzentLink: Color
    @Composable get() = Color(if (isSystemInDarkTheme()) PresentationTokens.link_dark else PresentationTokens.blue)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MarkdownText(text: String, citationSources: List<CitationSource> = emptyList(), softStreaming: Boolean = false, textSize: Float = PresentationTokens.typeChat.toFloat()) {
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
        }).usePlugin(TablePlugin.create(context)).usePlugin(StrikethroughPlugin.create()).build() }
    val foreground = MaterialTheme.colorScheme.onSurface.toArgb()
    val blocks by produceState<List<MarkdownBlock>>(initialValue = emptyList(), renderer, renderedText) {
        value = withContext(Dispatchers.Default) {
            synchronized(renderer) {
                markdownSections(renderer.parse(renderedText)).map { section ->
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
                AndroidView(modifier = Modifier.fillMaxWidth(), factory = { ctx ->
                    SoftStreamTextView(ctx).apply { this.textSize = textSize; setTextIsSelectable(true); setLineSpacing(0f, 1.2f) }
                }, update = { view ->
                    view.textSize = textSize
                    view.setTextColor(foreground); view.setLinkTextColor(link)
                    val styled = android.text.SpannableString(block.body)
                    styled.getSpans(0, styled.length, android.text.style.ClickableSpan::class.java).forEach { span ->
                        val start = styled.getSpanStart(span)
                        val end = styled.getSpanEnd(span)
                        if (styled.subSequence(start, end).startsWith("↗  ")) {
                            val target = (span as? android.text.style.URLSpan)?.url
                            val sourceId = target?.let { Uri.parse(it).path?.removePrefix("/")?.split(',')?.firstOrNull() }
                            val icon = citationSources.firstOrNull { it.id == sourceId }?.favicon?.let(icons::get)
                            styled.setSpan(CitationBadgeSpan(dark, target == pendingLink, icon), start, end, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                        }
                    }
                    renderer.setParsedMarkdown(view, view.prepare(styled, softStreaming))
                    // Text selection installs ArrowKeyMovementMethod, which prevents Markwon
                    // from installing its link handler automatically.
                    view.movementMethod = android.text.method.LinkMovementMethod.getInstance()
                    view.highlightColor = android.graphics.Color.TRANSPARENT
                })
            }
        }
    }
    pendingLink?.let { link ->
        val ids = Uri.parse(link).path.orEmpty().removePrefix("/").split(',')
        val sources = if (link.startsWith("suzent-citation://")) ids.mapNotNull { id -> citationSources.firstOrNull { it.id == id } }
            else listOf(citationSources.firstOrNull { it.url == link } ?: CitationSource("", "webpage", Uri.parse(link).host.orEmpty(), link))
        ModalBottomSheet(onDismissRequest = { pendingLink = null }, shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)) {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(stringResource(R.string.citation_sources), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                sources.forEach { source ->
                    val uri = Uri.parse(source.url)
                    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            val icon = icons[source.favicon]
                            if (icon != null) Image(icon.asImageBitmap(), contentDescription = null, modifier = Modifier.size(18.dp))
                            else Text("↗", Modifier.size(18.dp), style = MaterialTheme.typography.labelMedium)
                            Text(uri.host.orEmpty().removePrefix("www."), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text(source.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        if (source.snippet.isNotBlank()) Text(source.snippet, style = MaterialTheme.typography.bodyMedium, maxLines = 6, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                        if (uri.scheme in listOf("http", "https")) {
                            Button(onClick = { androidx.browser.customtabs.CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, uri) }, shape = RoundedCornerShape(50)) {
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

@Composable
fun MessageView(message: DisplayMessage, isLatest: Boolean = false, fallbackModel: String? = null,
                canRetry: Boolean = false, canEdit: Boolean = false, canFork: Boolean = false,
                onAction: (String, String?) -> Unit = { _, _ -> }) {
    val outline = MaterialTheme.colorScheme.outline
    val shadowColor = suzentShadow
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
    if (message.role in listOf("system_triggered", "trigger")) {
        systemReminder(message.text)?.let { SystemReminderView(it, message.citationSources) }
    } else if (message.role == "user") Box(Modifier.fillMaxWidth().padding(start = 40.dp), contentAlignment = androidx.compose.ui.Alignment.CenterEnd) {
        Box(Modifier.padding(end = PresentationTokens.shadowOffset.dp, bottom = PresentationTokens.shadowOffset.dp)
            .widthIn(max = 320.dp).drawBehind {
                drawRect(shadowColor, topLeft = Offset(PresentationTokens.shadowOffset.dp.toPx(), PresentationTokens.shadowOffset.dp.toPx()), size = size)
            }.background(Color(PresentationTokens.yellow)).border(PresentationTokens.borderWidth.dp, outline).padding(PresentationTokens.spaceMedium.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceSmall.dp)) {
                message.files.forEach { AttachmentChip(it.filename, it.mimeType, color = Color.Black) }
                if (message.text.isNotEmpty()) SelectionContainer { Text(message.text, color = Color.Black, fontSize = PresentationTokens.typeChat.sp) }
            }
        }
    } else Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SuzentAssistantBadge(compact = !isLatest)
        ActivityContent(message.parts, live = false, citationSources = message.citationSources)
    }
    if (message.role in listOf("user", "assistant")) MessageFooter(message, fallbackModel, canRetry, canEdit, canFork, onAction)
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
            Text("◷", color = muted, fontSize = 12.sp, modifier = Modifier.padding(end = 8.dp))
            Text(reminder.title, color = muted, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold,
                fontSize = 11.sp, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            if (reminder.body.isNotEmpty()) Text(if (expanded) "−" else "+", color = muted, modifier = Modifier.padding(horizontal = 8.dp))
        }
        if (expanded && reminder.body.isNotEmpty()) MarkdownText(reminder.body, citationSources = sources, textSize = 12f)
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun MessageFooter(message: DisplayMessage, fallbackModel: String?, canRetry: Boolean, canEdit: Boolean,
                          canFork: Boolean, onAction: (String, String?) -> Unit) {
    val context = LocalContext.current
    var copied by remember(message.text) { mutableStateOf(false) }
    var action by remember { mutableStateOf<String?>(null) }
    var edited by remember(message.text) { mutableStateOf(message.text) }
    var sourcesOpen by remember { mutableStateOf(false) }
    var modelDetails by remember { mutableStateOf<String?>(null) }
    val user = message.role == "user"
    val ink = MaterialTheme.colorScheme.onSurfaceVariant
    LaunchedEffect(copied) { if (copied) { kotlinx.coroutines.delay(1800); copied = false } }
    Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            if (user) Spacer(Modifier.weight(1f))
            if (message.text.isNotBlank()) IconButton(modifier = Modifier.size(32.dp), onClick = {
                val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                clipboard.setPrimaryClip(android.content.ClipData.newPlainText("", message.text)); copied = true
            }) { Icon(painterResource(if (copied) R.drawable.ic_message_check else R.drawable.ic_message_copy), stringResource(if (copied) R.string.message_copied else R.string.message_copy), Modifier.size(18.dp), tint = ink) }
            if (canEdit) IconButton(modifier = Modifier.size(32.dp), onClick = { action = "edit" }) { Icon(painterResource(R.drawable.ic_chat_rename), stringResource(R.string.message_edit), Modifier.size(18.dp), tint = ink) }
            if (canRetry) IconButton(modifier = Modifier.size(32.dp), onClick = { action = "retry" }) { Icon(painterResource(R.drawable.ic_message_retry), stringResource(R.string.message_retry), Modifier.size(18.dp), tint = ink) }
            if (canFork) IconButton(modifier = Modifier.size(32.dp), onClick = { action = "fork" }) { Icon(painterResource(R.drawable.ic_message_fork), stringResource(R.string.message_fork), Modifier.size(18.dp), tint = ink) }
            if (!user && message.citationSources.isNotEmpty()) TextButton(onClick = { sourcesOpen = true }, contentPadding = PaddingValues(horizontal = 4.dp),
                modifier = Modifier.widthIn(min = 32.dp).height(32.dp)
                    .semantics { contentDescription = context.getString(R.string.message_sources, message.citationSources.size) }) {
                Text("↗ ${message.citationSources.size}", fontSize = 11.sp, color = ink, maxLines = 1)
            }
            if (!user) (message.model ?: fallbackModel)?.takeIf { it.isNotBlank() }?.let { model ->
                Text(model.substringAfter('/'), Modifier.weight(1f, fill = false)
                    .clickable(onClickLabel = stringResource(R.string.message_model)) { modelDetails = model }
                    .border(1.dp, MaterialTheme.colorScheme.outlineVariant).padding(horizontal = 6.dp, vertical = 3.dp),
                    fontSize = 11.sp, fontWeight = FontWeight.Medium, color = ink,
                    maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            }
            message.timestamp?.let { raw ->
                val formatted = remember(raw) { runCatching {
                    val parsed = java.time.OffsetDateTime.parse(raw).atZoneSameInstant(java.time.ZoneId.systemDefault())
                    parsed.format(java.time.format.DateTimeFormatter.ofPattern("d MMM HH:mm", java.util.Locale.getDefault()))
                }.getOrDefault(raw) }
                Text(formatted, Modifier.widthIn(max = 100.dp), fontSize = 11.sp, color = ink,
                    maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            }
            if (user) Text(stringResource(R.string.you), fontSize = 11.sp, color = ink, maxLines = 1)
    }
    modelDetails?.let { model ->
        AlertDialog(onDismissRequest = { modelDetails = null }, title = { Text(stringResource(R.string.message_model)) },
            text = { SelectionContainer { Text(model) } },
            confirmButton = { TextButton(onClick = { modelDetails = null }) { Text(stringResource(android.R.string.ok)) } })
    }
    action?.let { selected ->
        val title = stringResource(when (selected) { "edit" -> R.string.message_edit; "fork" -> R.string.message_fork; else -> R.string.message_retry })
        AlertDialog(onDismissRequest = { action = null }, title = { Text(title) }, text = {
            if (selected == "edit") OutlinedTextField(edited, { edited = it }, Modifier.fillMaxWidth(), minLines = 3, maxLines = 8)
            else Text(stringResource(if (selected == "fork") R.string.message_fork_help else R.string.message_retry_help))
        }, confirmButton = { TextButton(enabled = selected != "edit" || edited.isNotBlank(), onClick = {
            onAction(selected, if (selected == "edit") edited else null); action = null
        }) { Text(title) } }, dismissButton = { TextButton(onClick = { action = null }) { Text(stringResource(R.string.cancel_link)) } })
    }
    if (sourcesOpen) ModalBottomSheet(onDismissRequest = { sourcesOpen = false }) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(stringResource(R.string.citation_sources), style = MaterialTheme.typography.titleLarge)
            message.citationSources.distinctBy { it.id }.forEach { source ->
                Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(source.title, fontWeight = FontWeight.SemiBold)
                    if (source.snippet.isNotBlank()) Text(source.snippet, maxLines = 5, style = MaterialTheme.typography.bodySmall)
                    if (Uri.parse(source.url).scheme in listOf("http", "https")) TextButton(onClick = {
                        androidx.browser.customtabs.CustomTabsIntent.Builder().build().launchUrl(context, Uri.parse(source.url))
                    }) { Text(stringResource(R.string.citation_read)) }
                }
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
    TextButton(onClick = onClick, modifier = modifier, enabled = enabled, contentPadding = contentPadding,
        colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.onSurface,
            disabledContentColor = MaterialTheme.colorScheme.onSurface.copy(alpha = .45f)), content = content)
}

@Composable
fun SuzentAction(label: String, onClick: () -> Unit, prominent: Boolean = false, enabled: Boolean = true, compact: Boolean = false, quiet: Boolean = false, destructive: Boolean = false) {
    val outline = MaterialTheme.colorScheme.outline
    val shadowColor = suzentShadow
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val shadow = if (quiet) 0.dp else PresentationTokens.shadowOffset.dp
    Box((if (compact) Modifier else Modifier.fillMaxWidth()).alpha(if (enabled) 1f else .45f).drawBehind {
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
            Text(label, fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold,
                color = if (destructive) MaterialTheme.colorScheme.error else if (prominent) Color.White else MaterialTheme.colorScheme.onSurface)
        }
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
fun SuzentNotice(message: String, dismiss: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(Color(PresentationTokens.yellow)).padding(horizontal = 12.dp, vertical = 4.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(message, Modifier.weight(1f), color = Color.Black, fontSize = PresentationTokens.typeCaption.sp)
        Text(stringResource(R.string.dismiss), Modifier.clickable(role = androidx.compose.ui.semantics.Role.Button, onClick = dismiss)
            .heightIn(min = PresentationTokens.controlHeight.dp).wrapContentHeight(), color = Color.Black,
            fontSize = PresentationTokens.typeCaption.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun SuzentToggle(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    val position by animateDpAsState(if (checked) 22.dp else 4.dp, tween(150), label = "toggle")
    Row(Modifier.fillMaxWidth().toggleable(value = checked, role = androidx.compose.ui.semantics.Role.Switch, onValueChange = onCheckedChange)
        .heightIn(min = PresentationTokens.controlHeight.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(label, Modifier.weight(1f), fontSize = PresentationTokens.typeControl.sp)
        Box(Modifier.size(44.dp, 26.dp).background(if (checked) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface.copy(alpha = .2f))
            .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)) {
            Box(Modifier.offset(x = position, y = 4.dp).size(18.dp).background(if (checked) Color.White else MaterialTheme.colorScheme.onSurface))
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
        val shadowColor = suzentShadow
        Box(Modifier.padding(end = 3.dp, bottom = 3.dp).drawBehind {
            drawRect(shadowColor, topLeft = Offset(3.dp.toPx(), 3.dp.toPx()))
        }.size(90.dp, 40.dp).background(MaterialTheme.colorScheme.surface)
            .border(PresentationTokens.borderWidth.dp, outline), contentAlignment = androidx.compose.ui.Alignment.Center) {
            Image(painterResource(R.drawable.suzent_logo), contentDescription = "Suzent", modifier = Modifier.size(26.dp))
        }
    }
}

@Composable
fun ActivityContent(parts: List<MessagePart>, live: Boolean, citationSources: List<CitationSource> = emptyList()) {
    val chunks = remember(parts) { activityChunks(parts) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        chunks.forEachIndexed { index, chunk ->
            key(index) {
                if (chunk.first().type == "text") StreamingMarkdown(chunk.first().text, live && index == chunks.lastIndex, citationSources)
                else ActivityRail(chunk, live)
            }
        }
    }
}

@Composable
private fun ActivityRail(parts: List<MessagePart>, live: Boolean) {
    var expanded by remember { mutableStateOf(false) }
    val waiting = parts.any { it.state == "approval-requested" }
    val running = live && parts.any { it.state == "running" }
    val failed = parts.any { it.state in listOf("error", "denied") }
    val ink = MaterialTheme.colorScheme.onSurface
    val accent = if (failed) MaterialTheme.colorScheme.error else if (running) suzentLink else MaterialTheme.colorScheme.onSurfaceVariant
    val status = stringResource(if (waiting) R.string.approval_required else if (running) R.string.activity_running else if (failed) R.string.activity_failed else R.string.activity_completed)
    Column(Modifier.fillMaxWidth()) {
        SuzentTextButton(onClick = { expanded = !expanded }, contentPadding = PaddingValues(horizontal = 4.dp, vertical = 12.dp), modifier = Modifier.fillMaxWidth()) {
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
    val color = if (error) MaterialTheme.colorScheme.error else if (active) suzentLink else MaterialTheme.colorScheme.onSurfaceVariant
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Column(Modifier.width(16.dp).fillMaxHeight().padding(top = 14.dp), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
            Box(Modifier.size(16.dp).background(if (pending) Color(PresentationTokens.yellow) else color.copy(alpha = 0.08f)), contentAlignment = androidx.compose.ui.Alignment.Center) {
                Text(if (pending) "!" else if (error) "×" else if (active) "·" else "✓", fontSize = 10.sp, lineHeight = 12.sp, color = if (pending) Color.Black else color)
            }
            Box(Modifier.width(1.dp).weight(1f).background(if (last) Color.Transparent else ink.copy(alpha = 0.12f)))
        }
        Column(Modifier.weight(1f)) {
            SuzentTextButton(onClick = { details = !details }, contentPadding = PaddingValues(0.dp), modifier = Modifier.fillMaxWidth().heightIn(min = 44.dp)) {
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
fun SuzentSelectionTrigger(value: String, onClick: () -> Unit, enabled: Boolean = true, prefix: String? = null) {
    val outline = MaterialTheme.colorScheme.outline
    val shadowColor = suzentShadow
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val offset = PresentationTokens.shadowOffset.dp
    Row(Modifier.alpha(if (enabled) 1f else .45f).padding(end = offset, bottom = offset)
        .drawBehind { if (!pressed) drawRect(shadowColor, topLeft = Offset(offset.toPx(), offset.toPx()), size = size) }
        .offset(x = if (pressed) offset else 0.dp, y = if (pressed) offset else 0.dp)
        .background(MaterialTheme.colorScheme.surface).border(PresentationTokens.borderWidth.dp, outline)
        .clickable(interactionSource = interaction, indication = null, enabled = enabled, role = androidx.compose.ui.semantics.Role.Button, onClick = onClick)
        .heightIn(min = PresentationTokens.controlHeight.dp).padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (prefix != null) Text(prefix, fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
        Text(value, Modifier.weight(1f, fill = false), fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.MiddleEllipsis)
        Canvas(Modifier.size(12.dp)) {
            val path = androidx.compose.ui.graphics.Path().apply { moveTo(size.width * .15f, size.height * .35f); lineTo(size.width * .5f, size.height * .7f); lineTo(size.width * .85f, size.height * .35f) }
            drawPath(path, outline, style = Stroke(width = 1.5.dp.toPx()))
        }
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
            drawRect(shadowColor, topLeft = Offset(4.dp.toPx(), 4.dp.toPx()), size = size)
        }.background(MaterialTheme.colorScheme.surface).border(2.dp, outline)) {
            val dismissLabel = stringResource(R.string.dismiss)
            Row(Modifier.fillMaxWidth().background(Color.Black).padding(start = 16.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text(title, Modifier.weight(1f), fontFamily = FontFamily.Monospace, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color.White)
                SuzentTextButton(onClick = dismiss, modifier = Modifier.size(44.dp)) { Text("×", color = Color.White, modifier = Modifier.semantics { contentDescription = dismissLabel }) }
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

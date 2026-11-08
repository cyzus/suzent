package com.suzent.mobile

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import org.json.JSONObject
import java.util.Locale

/** How surfaces in the transcript act; provided once by the conversation so every reply shares it. */
/** [act] reports through its last argument whether the action was delivered. */
class SurfaceHandler(val interactive: (A2UISurface) -> Boolean, val act: (A2UISurface, String, Map<String, Any?>, (Boolean) -> Unit) -> Unit)

val LocalSurfaceHandler = compositionLocalOf<SurfaceHandler?> { null }

@Composable
fun ProvideSurfaceHandler(handler: SurfaceHandler, content: @Composable () -> Unit) =
    CompositionLocalProvider(LocalSurfaceHandler provides handler, content = content)

/** Runs a surface action; the callback says whether it was delivered. */
typealias SurfaceAct = (String, Map<String, Any?>, (Boolean) -> Unit) -> Unit

/** An agent-rendered surface inside a reply, with a slim ruled header like the desktop's inline surfaces. */
@Composable
fun SurfaceBlock(surface: A2UISurface) {
    val handler = LocalSurfaceHandler.current
    val interactive = handler?.interactive?.invoke(surface) ?: false
    val act: SurfaceAct = { action, context, done -> handler?.act?.invoke(surface, action, context, done) ?: done(false) }
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
        .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)) {
        surface.title?.takeIf { it.isNotBlank() }?.let { title ->
            Text(title.uppercase(Locale.getDefault()), Modifier.padding(horizontal = PresentationTokens.spaceMedium.dp, vertical = 8.dp),
                fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold, fontSize = PresentationTokens.typeSidebarSection.sp,
                letterSpacing = 1.4.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
            HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
        }
        Box(Modifier.padding(PresentationTokens.spaceMedium.dp)) { SurfaceComponent(surface.component, interactive, act, root = true) }
    }
}

@Composable
private fun SurfaceComponent(component: A2UIComponent, interactive: Boolean, act: SurfaceAct, root: Boolean = false) {
    when (component) {
        is A2UIComponent.Text -> if (component.markdown) MarkdownText(component.content) else SurfaceText(component)
        is A2UIComponent.Badge -> SurfaceBadge(component)
        is A2UIComponent.Button -> SuzentAction(component.label, onClick = { act(component.action, component.context + ("button_label" to component.label)) {} },
            prominent = component.variant == null || component.variant == "primary", destructive = component.variant == "danger",
            enabled = interactive && !component.disabled)
        is A2UIComponent.Table -> SurfaceTable(component)
        is A2UIComponent.Form -> SurfaceForm(component, interactive) { payload, done -> act(component.action, payload, done) }
        is A2UIComponent.ListItems -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            component.items.forEachIndexed { index, item ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(if (component.ordered) "${index + 1}." else "•", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(item, fontSize = PresentationTokens.typeChat.sp)
                }
            }
        }
        is A2UIComponent.Progress -> SurfaceProgress(component)
        A2UIComponent.Divider -> HorizontalDivider(color = suzentRowDivider)
        is A2UIComponent.Html -> SurfaceHtml(component, interactive, act)
        is A2UIComponent.Card -> Column(Modifier.fillMaxWidth()
            .then(if (root) Modifier else Modifier.border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = .5f)).padding(PresentationTokens.spaceMedium.dp)),
            verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceMedium.dp)) {
            component.title?.takeIf { it.isNotBlank() }?.let { Text(it, fontWeight = FontWeight.Bold, fontSize = PresentationTokens.typeControl.sp) }
            component.children.forEach { SurfaceComponent(it, interactive, act) }
        }
        is A2UIComponent.Columns -> SurfaceColumns(component, interactive, act)
        is A2UIComponent.Stack -> Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(when (component.gap) {
            "sm" -> 6.dp; "lg" -> 20.dp; else -> PresentationTokens.spaceMedium.dp
        })) { component.children.forEach { SurfaceComponent(it, interactive, act) } }
        is A2UIComponent.Unknown -> Unit
    }
}

@Composable
private fun SurfaceText(text: A2UIComponent.Text) = when (text.variant) {
    "heading" -> Text(text.content, fontSize = PresentationTokens.typeSection.sp, fontWeight = FontWeight.Bold)
    "subheading" -> Text(text.content, fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold)
    "caption" -> Text(text.content, fontSize = PresentationTokens.typeCaption.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    "code" -> Box(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant).horizontalScroll(rememberScrollState()).padding(10.dp)) {
        Text(text.content, fontFamily = FontFamily.Monospace, fontSize = PresentationTokens.typeCaption.sp)
    }
    else -> Text(text.content, fontSize = PresentationTokens.typeChat.sp)
}

@Composable
private fun SurfaceBadge(badge: A2UIComponent.Badge) {
    val (fill, ink) = when (badge.color) {
        "success" -> Color(PresentationTokens.green) to Color.Black
        "warning" -> suzentYellow() to Color.Black
        "error" -> MaterialTheme.colorScheme.error to MaterialTheme.colorScheme.onError
        "info" -> Color(PresentationTokens.blue) to Color.White
        else -> suzentSelection to MaterialTheme.colorScheme.onSurface
    }
    Text(badge.label, Modifier.background(fill).border(1.dp, MaterialTheme.colorScheme.outline).padding(horizontal = 8.dp, vertical = 3.dp),
        color = ink, fontSize = PresentationTokens.typeLabel.sp, fontWeight = FontWeight.Bold)
}

@Composable
private fun SurfaceProgress(progress: A2UIComponent.Progress) {
    val clamped = progress.value.coerceIn(0.0, 100.0)
    val percent = "${Math.round(clamped)}%"
    Column(Modifier.fillMaxWidth().clearAndSetSemantics { contentDescription = listOfNotNull(progress.label, percent).joinToString(", ") },
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row {
            Text(progress.label ?: "", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
            Text(percent, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Row(Modifier.fillMaxWidth().height(10.dp).background(suzentSelection).border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)) {
            if (clamped > 0) Box(Modifier.weight(clamped.toFloat()).fillMaxHeight().background(Color(PresentationTokens.blue)))
            if (clamped < 100) Box(Modifier.weight((100 - clamped).toFloat()).fillMaxHeight())
        }
    }
}

/** Tables scroll sideways rather than squeezing columns to a phone's width; each column is as wide as its widest cell. */
@Composable
private fun SurfaceTable(table: A2UIComponent.Table) {
    val measurer = androidx.compose.ui.text.rememberTextMeasurer()
    val density = androidx.compose.ui.platform.LocalDensity.current
    val body = MaterialTheme.typography.bodyMedium
    val header = body.copy(fontWeight = FontWeight.Bold)
    val cells = table.rows.map { row -> table.columns.map { jsonDisplay(row[it.key]) } }
    val widths = table.columns.mapIndexed { index, column ->
        val widest = (listOf(measurer.measure(column.label, header).size.width) +
            cells.map { measurer.measure(it[index], body).size.width }).max()
        (with(density) { widest.toDp() } + 20.dp).coerceIn(72.dp, 260.dp)
    }
    Column(Modifier.horizontalScroll(rememberScrollState()).border(1.dp, MaterialTheme.colorScheme.outline)) {
        Row(Modifier.background(suzentSelection)) {
            table.columns.forEachIndexed { index, column -> TableCell(column.label, widths[index], bold = true) }
        }
        cells.forEach { row ->
            HorizontalDivider(Modifier.width(widths.fold(0.dp) { sum, width -> sum + width }), color = suzentRowDivider)
            Row { row.forEachIndexed { index, text -> TableCell(text, widths[index]) } }
        }
    }
}

@Composable
private fun TableCell(text: String, width: androidx.compose.ui.unit.Dp, bold: Boolean = false) {
    Text(text, Modifier.width(width).padding(horizontal = 10.dp, vertical = 8.dp),
        fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal, style = MaterialTheme.typography.bodyMedium)
}

/** Side by side when each column gets a usable width, stacked on narrow phones. */
@Composable
private fun SurfaceColumns(columns: A2UIComponent.Columns, interactive: Boolean, act: SurfaceAct) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val count = columns.children.size.coerceAtLeast(1)
        val weights = columns.children.indices.map { columns.ratios.getOrNull(it)?.takeIf { r -> r > 0 }?.toFloat() ?: 1f }
        val spacing = PresentationTokens.spaceMedium.dp
        val narrowest = (maxWidth - spacing * (count - 1)) * (weights.minOrNull() ?: 1f) / weights.sum().coerceAtLeast(1f)
        if (narrowest >= 140.dp) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(spacing)) {
            columns.children.forEachIndexed { index, child -> Box(Modifier.weight(weights[index])) { SurfaceComponent(child, interactive, act) } }
        } else Column(verticalArrangement = Arrangement.spacedBy(spacing)) {
            columns.children.forEach { SurfaceComponent(it, interactive, act) }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SurfaceForm(form: A2UIComponent.Form, interactive: Boolean, submit: (Map<String, Any?>, (Boolean) -> Unit) -> Unit) {
    val values = remember(form) { mutableStateMapOf<String, Any?>().apply { form.fields.forEach { f -> f.default?.let { put(f.name, it) } } } }
    val otherText = remember(form) { mutableStateMapOf<String, String>() }
    var submitted by rememberSaveable(form) { mutableStateOf(false) }
    var picking by remember { mutableStateOf<A2UIFormField?>(null) }
    val enabled = interactive && !submitted

    // What the agent receives: each field by name. Typed free text replaces a select's choice and joins a
    // multiselect's choices, as on the desktop; number fields are converted only now, so editing keeps "1.".
    fun payload(): Map<String, Any?> = form.fields.associate { field ->
        val typed = otherText[field.name]?.trim().orEmpty()
        val value = values[field.name]
        field.name to when {
            field.kind == "number" && value is String -> value.replace(',', '.').toDoubleOrNull() ?: value
            field.kind == "multiselect" && typed.isNotEmpty() -> ((value as? List<*>) ?: emptyList<Any?>()) + typed
            field.kind == "select" && typed.isNotEmpty() -> typed
            value != null -> value
            field.kind == "checkbox" -> false
            field.kind == "multiselect" -> emptyList<String>()
            else -> ""
        }
    }
    val complete = form.fields.filter { it.required }.all { field ->
        when (val value = payload()[field.name]) {
            is String -> value.isNotBlank()
            is List<*> -> value.isNotEmpty()
            null -> false
            else -> true
        }
    }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceMedium.dp)) {
        form.fields.forEach { field ->
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                // A checkbox carries its label on the switch row itself.
                if (field.kind != "checkbox") Row {
                    Text(field.label, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                    if (field.required) Text("*", color = MaterialTheme.colorScheme.error, modifier = Modifier.clearAndSetSemantics {})
                }
                when (field.kind) {
                    "checkbox" -> {
                        val checked = values[field.name] == true
                        Row(Modifier.fillMaxWidth().toggleable(checked, enabled, Role.Switch) { values[field.name] = it }.heightIn(min = 44.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            Text(field.label, Modifier.weight(1f), fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                            Switch(checked = checked, onCheckedChange = null, enabled = enabled)
                        }
                    }
                    "select" -> {
                        SuzentSelectionTrigger(jsonDisplay(values[field.name]).ifEmpty { field.placeholder ?: stringResource(R.string.surface_choose) },
                            onClick = { picking = field }, enabled = enabled)
                        if (field.allowFreeText) SurfaceInput(otherText[field.name] ?: "", { otherText[field.name] = it },
                            stringResource(R.string.surface_free_text), enabled)
                    }
                    "multiselect" -> {
                        val chosen = (values[field.name] as? List<*>)?.map { jsonDisplay(it) }?.toSet() ?: emptySet()
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            field.options.forEach { option ->
                                val on = option in chosen
                                Text(option, Modifier.background(if (on) suzentYellow() else MaterialTheme.colorScheme.background)
                                    .border(1.dp, MaterialTheme.colorScheme.outline)
                                    .toggleable(on, enabled, Role.Checkbox) {
                                        val next = if (on) chosen - option else chosen + option
                                        values[field.name] = field.options.filter { it in next }
                                    }.padding(horizontal = 10.dp, vertical = 8.dp),
                                    color = if (on) Color.Black else MaterialTheme.colorScheme.onSurface,
                                    fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal, style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                        if (field.allowFreeText) SurfaceInput(otherText[field.name] ?: "", { otherText[field.name] = it },
                            stringResource(R.string.surface_free_text), enabled)
                    }
                    "number" -> SurfaceInput(jsonDisplay(values[field.name]), { values[field.name] = it }, field.placeholder ?: "", enabled,
                        KeyboardOptions(keyboardType = KeyboardType.Decimal))
                    "textarea" -> SurfaceInput(jsonDisplay(values[field.name]), { values[field.name] = it }, field.placeholder ?: "", enabled, multiline = true)
                    else -> SurfaceInput(jsonDisplay(values[field.name]), { values[field.name] = it }, field.placeholder ?: "", enabled)
                }
            }
        }
        // Locked while sending so a double tap cannot answer twice; a failed send unlocks it to retry.
        SuzentAction(form.submitLabel ?: stringResource(R.string.surface_submit), onClick = { submitted = true; submit(payload()) { ok -> if (!ok) submitted = false } },
            prominent = true, enabled = enabled && complete)
    }
    picking?.let { field ->
        SuzentSelectionPanel(field.label, field.options.map { it to it }, jsonDisplay(values[field.name]), dismiss = { picking = null }) {
            values[field.name] = it; otherText.remove(field.name); picking = null
        }
    }
}

@Composable
private fun SurfaceInput(value: String, onValueChange: (String) -> Unit, placeholder: String, enabled: Boolean,
                         keyboard: KeyboardOptions = KeyboardOptions.Default, multiline: Boolean = false) {
    androidx.compose.foundation.text.BasicTextField(value, onValueChange, enabled = enabled, singleLine = !multiline,
        minLines = if (multiline) 3 else 1, maxLines = if (multiline) 6 else 1, keyboardOptions = keyboard,
        textStyle = MaterialTheme.typography.bodyMedium.copy(color = MaterialTheme.colorScheme.onSurface),
        cursorBrush = androidx.compose.ui.graphics.SolidColor(suzentLink),
        modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.background)
            .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).heightIn(min = 40.dp).padding(10.dp),
        decorationBox = { input -> Box { if (value.isEmpty()) Text(placeholder, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium); input() } })
}

/** Connects a cached page to whichever composition is showing it now. */
private class SurfaceBridge {
    var onHeight: (Float) -> Unit = {}
    var onAction: (String, Map<String, Any?>) -> Unit = { _, _ -> }
}

/**
 * Loaded pages and their content heights, kept while their reply scrolls off screen. The chat list disposes
 * off-screen rows, so without this every return reloaded the page (a blank flash) and re-measured it (a jump).
 */
private object SurfacePages {
    private const val LIMIT = 4
    private val views = LinkedHashMap<String, Pair<WebView, SurfaceBridge>>(LIMIT, .75f, true)
    private val heights = object : LinkedHashMap<String, Float>(32, .75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Float>) = size > 32
    }

    fun height(html: String): Float? = heights[html]
    fun remember(html: String, height: Float) { heights[html] = height }

    fun obtain(context: android.content.Context, html: String): Pair<WebView, SurfaceBridge> {
        views[html]?.let { cached ->
            // A page from an earlier activity (rotation, language change) cannot move into this one.
            if (cached.first.context === context) {
                (cached.first.parent as? android.view.ViewGroup)?.removeView(cached.first)
                return cached
            }
            views.remove(html)?.first?.destroy()
        }
        val bridge = SurfaceBridge()
        val view = createPage(context, html, bridge)
        views[html] = view to bridge
        while (views.size > LIMIT) {
            // Pages on screen stay; the cache may run over its limit until one scrolls away.
            val eldest = views.entries.firstOrNull { it.value.first.parent == null && it.key != html } ?: break
            views.remove(eldest.key)?.first?.destroy()
        }
        return view to bridge
    }

    /** Destroys a page only when it is no longer cached; cached ones wait to be shown again. */
    fun release(view: WebView) {
        if (views.values.none { it.first === view }) view.destroy()
    }
}

/**
 * Agent HTML in an isolated web view: no file or content access, no shared storage, links open outside the app,
 * and `postMessage({type: 'a2ui:action'})` reaches the agent like a button.
 */
@SuppressLint("SetJavaScriptEnabled")
private fun createPage(context: android.content.Context, html: String, bridge: SurfaceBridge): WebView = WebView(context).apply {
    settings.javaScriptEnabled = true
    settings.allowFileAccess = false
    settings.allowContentAccess = false
    settings.domStorageEnabled = false
    settings.setGeolocationEnabled(false)
    isVerticalScrollBarEnabled = false
    setBackgroundColor(android.graphics.Color.TRANSPARENT)
    addJavascriptInterface(object {
        @JavascriptInterface fun post(message: String) {
            val body = runCatching { JSONObject(message) }.getOrNull() ?: return
            when (body.optString("kind")) {
                "height" -> {
                    val height = body.optDouble("height", 0.0).toFloat().coerceIn(40f, 5000f)
                    this@apply.post { SurfacePages.remember(html, height); bridge.onHeight(height) }
                }
                "action" -> {
                    val name = body.optString("action")
                    val context = jsonMap(body.optJSONObject("context"))
                    this@apply.post { if (name.isNotBlank()) bridge.onAction(name, context) }
                }
            }
        }
    }, "SuzentSurface")
    webViewClient = object : WebViewClient() {
        // The surface's own document loads in place; anything the user follows opens in the browser.
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val scheme = request.url.scheme?.lowercase()
            if (request.hasGesture() && scheme in setOf("http", "https", "mailto"))
                runCatching { view.context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(request.url.toString()))) }
            return true
        }
    }
    loadDataWithBaseURL(null, surfaceHtmlDocument(html), "text/html", "UTF-8", null)
}

@Composable
private fun SurfaceHtml(html: A2UIComponent.Html, interactive: Boolean, act: SurfaceAct) {
    var measured by remember(html.html) { mutableStateOf(SurfacePages.height(html.html)) }
    val canAct by rememberUpdatedState(interactive)
    val currentAct by rememberUpdatedState(act)
    // The agent's height is only a first guess until the page reports its content height.
    val height = measured ?: html.height?.toFloat() ?: 120f
    key(html.html) {
        AndroidView(factory = { context ->
            val (view, bridge) = SurfacePages.obtain(context, html.html)
            bridge.onHeight = { measured = it }
            bridge.onAction = { name, context -> if (canAct) currentAct(name, context) {} }
            view
        }, onRelease = SurfacePages::release,
            modifier = Modifier.fillMaxWidth().height(height.dp).border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = .4f)))
    }
}

/** The user's side of a surface action: what was pressed, like the desktop's canvas pill. */
@Composable
fun CanvasActionPill(label: String) {
    val description = stringResource(R.string.surface_chose, label)
    Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = description; stateDescription = "" },
        horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
        Text("↳", color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(end = 6.dp).clearAndSetSemantics {})
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = PresentationTokens.typeCaption.sp,
            fontWeight = FontWeight.SemiBold, maxLines = 2)
    }
}

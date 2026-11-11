package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject

/** An agent-rendered surface (desktop A2UI): a component tree shown in the chat. */
data class A2UISurface(
    val id: String, val title: String?, val component: A2UIComponent, val target: String?,
    val rev: Double?, val deferred: Boolean,
) {
    companion object {
        /** A malformed surface degrades to an empty one instead of failing the message that carries it. */
        fun parse(json: JSONObject): A2UISurface = A2UISurface(
            json.optString("id"), json.opt("title") as? String,
            json.optJSONObject("component")?.let(A2UIComponent::parse) ?: A2UIComponent.Unknown(""),
            json.opt("target") as? String, (json.opt("rev") as? Number)?.toDouble(), json.optBoolean("deferred"),
        )
    }
}

data class A2UITableColumn(val key: String, val label: String)

data class A2UIFormField(
    val name: String, val label: String, val kind: String, val options: List<String>, val allowFreeText: Boolean,
    val required: Boolean, val default: Any?, val placeholder: String?,
)

sealed interface A2UIComponent {
    val typeName: String

    data class Text(val content: String, val variant: String?, val markdown: Boolean) : A2UIComponent { override val typeName = "text" }
    data class Badge(val label: String, val color: String?) : A2UIComponent { override val typeName = "badge" }
    data class Button(val label: String, val action: String, val context: Map<String, Any?>, val variant: String?, val disabled: Boolean) : A2UIComponent { override val typeName = "button" }
    data class Table(val columns: List<A2UITableColumn>, val rows: List<Map<String, Any?>>) : A2UIComponent { override val typeName = "table" }
    data class Form(val fields: List<A2UIFormField>, val submitLabel: String?, val action: String) : A2UIComponent { override val typeName = "form" }
    data class ListItems(val items: List<String>, val ordered: Boolean) : A2UIComponent { override val typeName = "list" }
    data class Progress(val value: Double, val label: String?) : A2UIComponent { override val typeName = "progress" }
    data object Divider : A2UIComponent { override val typeName = "divider" }
    data class Html(val html: String, val height: Double?) : A2UIComponent { override val typeName = "html" }
    data class Card(val title: String?, val children: List<A2UIComponent>) : A2UIComponent { override val typeName = "card" }
    data class Columns(val children: List<A2UIComponent>, val ratios: List<Double>) : A2UIComponent { override val typeName = "columns" }
    data class Stack(val children: List<A2UIComponent>, val gap: String?) : A2UIComponent { override val typeName = "stack" }
    /** A component this app version does not know; it renders nothing rather than failing the whole surface. */
    data class Unknown(val type: String) : A2UIComponent { override val typeName = "unknown" }

    /** Every component in the tree, depth first, this one included. */
    val flattened: List<A2UIComponent>
        get() = when (this) {
            is Card -> listOf(this) + children.flatMap { it.flattened }
            is Columns -> listOf(this) + children.flatMap { it.flattened }
            is Stack -> listOf(this) + children.flatMap { it.flattened }
            else -> listOf(this)
        }

    companion object {
        fun parse(json: JSONObject): A2UIComponent = runCatching { parseStrict(json) }.getOrDefault(Unknown(""))

        private fun children(json: JSONObject): List<A2UIComponent> {
            val array = json.optJSONArray("children") ?: return emptyList()
            return (0 until array.length()).map { array.optJSONObject(it)?.let(::parse) ?: Unknown("") }
        }

        private fun strings(array: JSONArray?): List<String> =
            if (array == null) emptyList() else (0 until array.length()).map { jsonDisplay(array.opt(it)) }

        private fun parseStrict(json: JSONObject): A2UIComponent = when (val type = json.getString("type")) {
            "text" -> Text(json.optString("content"), json.opt("variant") as? String, json.optBoolean("markdown"))
            "badge" -> Badge(json.getString("label"), json.opt("color") as? String)
            "button" -> Button(json.getString("label"), json.getString("action"), jsonMap(json.optJSONObject("context")),
                json.opt("variant") as? String, json.optBoolean("disabled"))
            "table" -> {
                val columns = json.optJSONArray("columns") ?: JSONArray()
                val rows = json.optJSONArray("rows") ?: JSONArray()
                Table((0 until columns.length()).map { columns.getJSONObject(it).let { c -> A2UITableColumn(c.getString("key"), c.getString("label")) } },
                    (0 until rows.length()).map { jsonMap(rows.optJSONObject(it)) })
            }
            "form" -> {
                val fields = json.optJSONArray("fields") ?: JSONArray()
                Form((0 until fields.length()).map { index ->
                    val field = fields.getJSONObject(index)
                    A2UIFormField(field.getString("name"), field.getString("label"), field.optString("type", "text"),
                        strings(field.optJSONArray("options")), field.optBoolean("allow_free_text"), field.optBoolean("required"),
                        field.opt("default")?.let(::jsonValue), field.opt("placeholder") as? String)
                }, json.opt("submit_label") as? String, json.optString("action", "submit"))
            }
            "list" -> ListItems(strings(json.optJSONArray("items")), json.optBoolean("ordered"))
            "progress" -> Progress(json.optDouble("value", 0.0), json.opt("label") as? String)
            "divider" -> Divider
            "html" -> Html(json.optString("html"), (json.opt("height") as? Number)?.toDouble())
            "card" -> Card(json.opt("title") as? String, children(json))
            "columns" -> Columns(children(json), json.optJSONArray("ratios")?.let { r -> (0 until r.length()).map { r.optDouble(it, 1.0) } } ?: emptyList())
            "stack" -> Stack(children(json), json.opt("gap") as? String)
            else -> Unknown(type)
        }
    }
}

/** JSON as plain Kotlin values: maps, lists, strings, numbers, booleans and null. */
fun jsonValue(value: Any?): Any? = when (value) {
    null, JSONObject.NULL -> null
    is JSONObject -> jsonMap(value)
    is JSONArray -> (0 until value.length()).map { jsonValue(value.opt(it)) }
    else -> value
}

fun jsonMap(json: JSONObject?): Map<String, Any?> =
    json?.keys()?.asSequence()?.associateWith { jsonValue(json.opt(it)) } ?: emptyMap()

/** How a value reads in a table cell or a question answer. */
fun jsonDisplay(value: Any?): String = when (val plain = jsonValue(value)) {
    null -> ""
    is Double -> if (plain % 1.0 == 0.0 && kotlin.math.abs(plain) < 1e15) plain.toLong().toString() else plain.toString()
    is Float -> jsonDisplay(plain.toDouble())
    is List<*> -> plain.joinToString(", ") { jsonDisplay(it) }
    is Map<*, *> -> compactJson(plain)
    else -> plain.toString()
}

/** Sorted-key JSON without escaped slashes, so both apps and the fixtures agree byte for byte. */
fun compactJson(value: Any?): String = when (val plain = jsonValue(value)) {
    null -> "null"
    is String -> quoteJson(plain)
    is Boolean -> plain.toString()
    is Number -> jsonDisplay(plain.toDouble())
    is Map<*, *> -> plain.entries.sortedBy { it.key.toString() }.joinToString(",", "{", "}") { quoteJson(it.key.toString()) + ":" + compactJson(it.value) }
    is List<*> -> plain.joinToString(",", "[", "]") { compactJson(it) }
    else -> quoteJson(plain.toString())
}

private fun quoteJson(text: String): String = buildString {
    append('"')
    for (char in text) when {
        char == '"' -> append("\\\"")
        char == '\\' -> append("\\\\")
        char == '\n' -> append("\\n")
        char == '\r' -> append("\\r")
        char == '\t' -> append("\\t")
        char < ' ' -> append("\\u%04x".format(char.code))
        else -> append(char)
    }
    append('"')
}

/** What the agent reads when a button or form on an ordinary surface is used: the desktop's canvas message. */
fun canvasActionMessage(action: String, context: Map<String, Any?>, surfaceId: String): String {
    val rest = context.toMutableMap()
    val label = rest.remove("button_label")?.let(::jsonDisplay)
    if (surfaceId.isNotEmpty() && "surface_id" !in rest) rest["surface_id"] = surfaceId
    return buildString {
        append("[canvas: $action]")
        if (!label.isNullOrEmpty()) append(" \"$label\"")
        if (rest.isNotEmpty()) append(" ").append(compactJson(rest))
    }
}

/** A question form that did not hold the turn open is answered as the user's next message. */
fun questionAnswerText(context: Map<String, Any?>): String {
    context["button_label"]?.let(::jsonDisplay)?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
    return context.filterKeys { it != "button_label" && it != "surface_id" }.toSortedMap()
        .entries.joinToString("\n") { "${it.key}: ${jsonDisplay(it.value).trim()}" }
}

/** What a blocked ask_question receives: the form values, or the pressed button's label as `answer`. */
fun deferredAnswer(context: Map<String, Any?>): Map<String, Any?> {
    val answer = context.toMutableMap()
    answer.remove("button_label")?.let { answer["answer"] = it }
    return answer
}

private val canvasActionPattern = Regex("""^\[canvas: ([^\]]+)\](?: "([^"]*)")?""")

/** The label of a user message that came from a surface action, or null for an ordinary message. */
fun canvasActionLabel(text: String): String? {
    val match = canvasActionPattern.find(text) ?: return null
    return match.groupValues[2].ifEmpty { match.groupValues[1] }
}

/**
 * Agent HTML written for a desktop iframe, made to fit a phone reply: a phone viewport, standards mode, and the
 * desktop's auto-size shim. It reports `{kind: "height"}` as content grows (fonts, images, script output) and
 * forwards `postMessage({type: "a2ui:action"})` as `{kind: "action"}`. Phones always size to content: a fixed
 * height would need scrolling inside the page, which the chat's own scroll takes over.
 */
fun surfaceHtmlDocument(html: String): String {
    var document = html
    if (!Regex("""<meta[^>]+name=["']?viewport""", RegexOption.IGNORE_CASE).containsMatchIn(document))
        document = "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">$document"
    if (!Regex("""^\s*<!doctype\s""", RegexOption.IGNORE_CASE).containsMatchIn(document)) document = "<!DOCTYPE html>\n$document"
    return document + "\n" + surfaceHtmlShim
}

private val surfaceHtmlShim = """
<style>html, body { height: auto !important; min-height: 0 !important; }</style>
<script>
(function () {
  function post(body) {
    var text = JSON.stringify(body);
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.surface) window.webkit.messageHandlers.surface.postMessage(text);
    else if (window.SuzentSurface) window.SuzentSurface.post(text);
  }
  window.addEventListener('message', function (event) {
    var data = event.data;
    if (data && data.type === 'a2ui:action' && typeof data.action === 'string') post({ kind: 'action', action: data.action, context: data.context || {} });
  });
  var pending = false;
  var previous = 0;
  function measure() {
    pending = false;
    var body = document.body;
    if (!body || !document.documentElement.clientWidth) return;
    var style = getComputedStyle(body);
    var height = Math.ceil(Math.max(body.scrollHeight, body.getBoundingClientRect().height) + (parseFloat(style.marginTop) || 0) + (parseFloat(style.marginBottom) || 0));
    if (height > 0 && height !== previous) { previous = height; post({ kind: 'height', height: height }); }
  }
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(measure);
  }
  window.addEventListener('load', schedule);
  window.addEventListener('resize', schedule);
  document.addEventListener('load', schedule, true);
  if (window.ResizeObserver) {
    var observer = new ResizeObserver(schedule);
    observer.observe(document.documentElement);
    observer.observe(document.body);
  }
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
  if (document.fonts) document.fonts.ready.then(schedule);
  schedule();
})();
</script>
""".trimIndent()

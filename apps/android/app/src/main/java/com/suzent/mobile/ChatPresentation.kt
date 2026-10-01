package com.suzent.mobile

data class CitationSource(
    val id: String, val type: String, val title: String, val url: String = "",
    val snippet: String = "", val favicon: String = "",
)

data class MessagePart(
    val type: String, val text: String = "", val toolName: String = "",
    val args: String = "", val output: String = "", val toolCallId: String = "",
    val state: String = "", val messageId: String = "", val citationSources: List<CitationSource> = emptyList(),
)

data class DisplayMessage(val role: String, val parts: List<MessagePart>, val citationSources: List<CitationSource> = emptyList(),
    val model: String? = null, val timestamp: String? = null, val messageIndex: Int = 0) {
    val text: String get() = parts.filter { it.type == "text" }.joinToString("\n\n") { it.text }
}

private val citationPatterns = listOf(
    Regex("\\[\\[cite:\\s*([^\\]\\n]+?)\\s*]]", RegexOption.IGNORE_CASE),
    Regex("\ue200cite\ue202([^\ue201]+)\ue201", RegexOption.IGNORE_CASE),
    Regex("\ufffccite\ufffc([A-Za-z0-9_,\\s\ufffc]+)\ufffc", RegexOption.IGNORE_CASE),
    Regex("\\bcite[-:]((?:t\\d+_src_\\d+)(?:\\s*,\\s*t\\d+_src_\\d+)*)\\b", RegexOption.IGNORE_CASE),
)

fun markdownWithCitationLinks(text: String, sources: List<CitationSource>, badges: Boolean = false): String {
    val byId = sources.associateBy { it.id }
    var occurrence = 0
    return citationPatterns.fold(text) { current, pattern ->
        pattern.replace(current) { match ->
            val ids = match.groupValues[1].split(',', '\ue202', '\ufffc').map { it.trim() }.filter { it.isNotEmpty() }
            val primary = ids.firstNotNullOfOrNull(byId::get) ?: return@replace ""
            val suffix = if (ids.size > 1) " +${ids.size - 1}" else ""
            val host = runCatching { java.net.URI(primary.url).host?.removePrefix("www.") }.getOrNull()
            val name = if (badges) (host ?: primary.title.ifEmpty { primary.id }) else primary.title.ifEmpty { primary.id }
            val compact = if (badges && name.length > 26) name.take(26) + "…" else name
            val label = (if (badges) "↗  " else "") + compact.replace("]", "\\]") + suffix
            val scheme = runCatching { java.net.URI(primary.url).scheme?.lowercase() }.getOrNull()
            val target = if (badges) "suzent-citation://sources/" + ids.joinToString(",") { java.net.URLEncoder.encode(it, "UTF-8") } + "#badge-${occurrence++}" else primary.url.replace(">", "%3E")
            if (scheme in listOf("http", "https")) "[$label](<$target>)" else label
        }
    }
}

private fun citationSourceIds(text: String): Set<String> = citationPatterns.flatMap { pattern ->
    pattern.findAll(text).flatMap { match ->
        match.groupValues[1].split(',', '\ue202', '\ufffc').map(String::trim).filter(String::isNotEmpty)
    }.toList()
}.toSet()

fun presentMessages(messages: List<ChatMessage>, liveToolIds: Set<String> = emptySet()): List<DisplayMessage> {
    val indexedSources = messages.flatMapIndexed { index, message ->
        message.parts.flatMap { part -> part.citationSources.map { index to it } }
    }
    val representedTools = messages.flatMap { it.parts }.filter { it.type == "tool" }
        .map { it.toolCallId }.filter { it.isNotEmpty() }.toSet()
    val rows = messages.mapIndexedNotNull { messageIndex, message ->
        if (PresentationTokens.compactionSummaryMarkers.any { message.content.contains(it) }) return@mapIndexedNotNull null
        if (message.role == "tool" && (message.toolCallId in representedTools || message.toolCallId in liveToolIds)) return@mapIndexedNotNull null
        val rawParts = when {
            message.role == "tool" -> listOf(MessagePart("tool", toolName = message.name, output = message.content, toolCallId = message.toolCallId))
            message.parts.isEmpty() -> listOf(MessagePart("text", text = message.content))
            else -> message.parts.filter { it.type != "tool" || it.toolCallId !in liveToolIds }
        }
        val parts = normalizeParts(rawParts)
        if (parts.isEmpty()) null else {
            val localSources = rawParts.flatMap { it.citationSources }
            val referencedIds = parts.flatMap { citationSourceIds(it.text) }.toSet()
            val nearbySources = referencedIds.mapNotNull { id ->
                indexedSources.filter { it.second.id == id }.minByOrNull { kotlin.math.abs(it.first - messageIndex) }?.second
            }
            DisplayMessage(message.role, parts, (localSources + nearbySources).distinctBy { it.id }, message.model, message.timestamp, messageIndex)
        }
    }
    val grouped = mutableListOf<DisplayMessage>()
    rows.forEach { row ->
        val previous = grouped.lastOrNull()
        // A final text part ends a reply; only unfinished activity joins the next row.
        if (previous != null && previous.role in listOf("assistant", "tool") && row.role in listOf("assistant", "tool") &&
            previous.parts.last().type != "text") {
            grouped[grouped.lastIndex] = DisplayMessage(
                if (previous.role == "assistant" || row.role == "assistant") "assistant" else "tool",
                normalizeParts(previous.parts + row.parts), (previous.citationSources + row.citationSources).distinctBy { it.id },
                row.model ?: previous.model, row.timestamp ?: previous.timestamp, row.messageIndex)
        } else grouped.add(row)
    }
    return grouped
}

fun normalizeParts(parts: List<MessagePart>): List<MessagePart> {
    val result = mutableListOf<MessagePart>()
    parts.forEach { part ->
        if (part.type == "citation-sources") return@forEach
        if (part.type in listOf("text", "reasoning") && part.text.isBlank()) return@forEach
        if (part.type == "tool" && part.toolName.lowercase() in PresentationTokens.ignoredToolNames) return@forEach
        val index = if (part.type == "tool" && part.toolCallId.isNotEmpty()) result.indexOfFirst { it.type == "tool" && it.toolCallId == part.toolCallId } else -1
        if (index < 0) result.add(part) else {
            val old = result[index]
            result[index] = part.copy(toolName = part.toolName.ifEmpty { old.toolName }, args = part.args.ifEmpty { old.args }, output = part.output.ifEmpty { old.output }, state = part.state.ifEmpty { old.state })
        }
    }
    return result
}

// Parts are normalized at the history or live-publication boundary.
fun activityChunks(parts: List<MessagePart>): List<List<MessagePart>> {
    val chunks = mutableListOf<MutableList<MessagePart>>()
    parts.forEach { part ->
        if (part.type == "text" || chunks.isEmpty() || chunks.last().last().type == "text") chunks.add(mutableListOf(part))
        else chunks.last().add(part)
    }
    return chunks
}

class LiveActivityBuffer {
    private val parts = mutableListOf<MessagePart>()
    private var textId = ""
    private var reasonIndex = -1
    private val startedArgs = mutableSetOf<String>()
    private var dirty = false
    fun drain(): List<MessagePart>? = if (!dirty) null else normalizeParts(parts).also { dirty = false }
    fun consume(event: org.json.JSONObject) {
        val type = event.optString("type")
        val id = event.optString("toolCallId")
        val delta = event.optString("delta")
        fun tool(update: (MessagePart) -> MessagePart) {
            if (id.isEmpty()) return
            var index = parts.indexOfFirst { it.type == "tool" && it.toolCallId == id }
            if (index < 0) { index = parts.size; parts.add(MessagePart("tool", toolCallId = id, state = "running")) }
            parts[index] = update(parts[index])
        }
        when (type) {
            "STREAM_RESET" -> { parts.clear(); startedArgs.clear(); reasonIndex = -1; textId = "" }
            "TEXT_MESSAGE_START" -> { textId = event.optString("messageId"); parts.add(MessagePart("text", messageId = textId)) }
            "TEXT_MESSAGE_CONTENT" -> {
                val index = parts.indexOfLast { it.type == "text" && it.messageId == event.optString("messageId", textId) }
                if (index < 0) parts.add(MessagePart("text", delta, messageId = event.optString("messageId", textId)))
                else parts[index] = parts[index].copy(text = parts[index].text + delta)
            }
            "THINKING_START", "THINKING_TEXT_MESSAGE_START", "REASONING_START", "REASONING_MESSAGE_START" -> {
                if (reasonIndex < 0 || parts[reasonIndex].state != "running") { reasonIndex = parts.size; parts.add(MessagePart("reasoning", state = "running")) }
            }
            "THINKING_TEXT_MESSAGE_CONTENT", "REASONING_MESSAGE_CONTENT", "REASONING_MESSAGE_CHUNK" -> {
                if (reasonIndex < 0) { reasonIndex = parts.size; parts.add(MessagePart("reasoning", state = "running")) }
                parts[reasonIndex] = parts[reasonIndex].copy(text = parts[reasonIndex].text + delta)
            }
            "THINKING_END", "THINKING_TEXT_MESSAGE_END", "REASONING_END", "REASONING_MESSAGE_END" -> {
                if (reasonIndex >= 0) parts[reasonIndex] = parts[reasonIndex].copy(state = "completed")
                reasonIndex = -1
            }
            "TOOL_CALL_START" -> { startedArgs.remove(id); tool { it.copy(toolName = event.optString("toolCallName"), state = "running") } }
            "TOOL_CALL_ARGS" -> tool { it.copy(args = (if (startedArgs.add(id)) "" else it.args) + delta) }
            "TOOL_CALL_RESULT" -> tool { it.copy(output = (event.opt("content") ?: event.opt("output") ?: event.opt("result") ?: "").toString(), state = "completed") }
            "CUSTOM" -> {
                val value = event.optJSONObject("value") ?: return
                when (event.optString("name")) {
                    "tool_approval_request" -> {
                        val toolId = value.optString("toolCallId")
                        val index = parts.indexOfFirst { it.type == "tool" && it.toolCallId == toolId }
                        val part = (if (index >= 0) parts[index] else MessagePart("tool", toolCallId = toolId)).copy(toolName = value.optString("toolName"), args = value.opt("args")?.toString() ?: "", state = "approval-requested")
                        if (index < 0) parts.add(part) else parts[index] = part
                    }
                    "tool_approval_result" -> {
                        val index = parts.indexOfFirst { it.type == "tool" && it.toolCallId == value.optString("toolCallId") }
                        if (index >= 0) parts[index] = parts[index].copy(output = (value.opt("output") ?: value.opt("content") ?: value.opt("result") ?: "").toString(), state = if (value.optString("status") == "executed") "completed" else "error")
                    }
                    else -> return
                }
            }
            else -> return
        }
        dirty = true
    }
}

fun streamingMarkdown(text: String, active: Boolean): String {
    if (!active || text.isBlank()) return text
    val lastLine = text.substringAfterLast('\n').trim()
    val blockEnding = lastLine.startsWith("```") || lastLine.startsWith("~~~") || lastLine.contains('|')
    return text + if (blockEnding) "\n\n▍" else " ▍"
}

fun showAssemblyBadge(parts: List<MessagePart>, streaming: Boolean): Boolean =
    streaming && parts.none { it.type != "text" || it.text.isNotBlank() }

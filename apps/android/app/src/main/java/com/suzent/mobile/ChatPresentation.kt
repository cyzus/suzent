package com.suzent.mobile

data class MessagePart(
    val type: String, val text: String = "", val toolName: String = "",
    val args: String = "", val output: String = "", val toolCallId: String = "",
    val state: String = "", val messageId: String = ""
)

data class DisplayMessage(val role: String, val text: String, val activities: List<MessagePart>, val parts: List<MessagePart> = emptyList())

fun presentMessages(messages: List<ChatMessage>, liveToolIds: Set<String> = emptySet()): List<DisplayMessage> {
    val representedTools = messages.flatMap { it.parts }.filter { it.type == "tool" }
        .map { it.toolCallId }.filter { it.isNotEmpty() }.toSet()
    return messages.mapNotNull { message ->
        if (PresentationTokens.compactionSummaryMarkers.any { message.content.contains(it) }) return@mapNotNull null
        if (message.role == "tool" && (message.toolCallId in representedTools || message.toolCallId in liveToolIds)) return@mapNotNull null
        val parts = if (message.role == "tool") listOf(MessagePart("tool", toolName = message.name,
            output = message.content, toolCallId = message.toolCallId)) else message.parts.filter { it.type != "tool" || it.toolCallId !in liveToolIds }
        val textParts = parts.filter { it.type == "text" }
        val text = if (textParts.isNotEmpty()) textParts.joinToString("\n\n") { it.text }
            else if (parts.isEmpty() && message.parts.isEmpty()) message.content else ""
        val activities = normalizeParts(parts).filter { it.type != "text" &&
            !(it.type == "tool" && it.toolName.lowercase() in PresentationTokens.ignoredToolNames) }
        if (text.isBlank() && activities.isEmpty()) null else DisplayMessage(message.role, text, activities, normalizeParts(if (parts.isEmpty()) listOf(MessagePart("text", text)) else parts))
    }
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

fun activityChunks(parts: List<MessagePart>): List<List<MessagePart>> {
    val chunks = mutableListOf<MutableList<MessagePart>>()
    normalizeParts(parts).forEach { part ->
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

package com.suzent.mobile

data class MessagePart(
    val type: String, val text: String = "", val toolName: String = "",
    val args: String = "", val output: String = "", val toolCallId: String = "",
    val state: String = ""
)

data class DisplayMessage(val role: String, val text: String, val activities: List<MessagePart>)

fun presentMessages(messages: List<ChatMessage>): List<DisplayMessage> {
    val representedTools = messages.flatMap { it.parts }.filter { it.type == "tool" }
        .map { it.toolCallId }.filter { it.isNotEmpty() }.toSet()
    return messages.mapNotNull { message ->
        if (PresentationTokens.compactionSummaryMarkers.any { message.content.contains(it) }) return@mapNotNull null
        if (message.role == "tool" && message.toolCallId in representedTools) return@mapNotNull null
        val parts = if (message.role == "tool") listOf(MessagePart("tool", toolName = message.name,
            output = message.content, toolCallId = message.toolCallId)) else message.parts
        val textParts = parts.filter { it.type == "text" }
        val text = if (textParts.isNotEmpty()) textParts.joinToString("\n\n") { it.text }
            else if (parts.isEmpty()) message.content else ""
        val activities = parts.filter { it.type != "text" &&
            !(it.type == "tool" && it.toolName.lowercase() in PresentationTokens.ignoredToolNames) }
        if (text.isBlank() && activities.isEmpty()) null else DisplayMessage(message.role, text, activities)
    }
}

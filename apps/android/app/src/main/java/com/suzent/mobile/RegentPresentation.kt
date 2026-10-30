package com.suzent.mobile

import org.json.JSONObject

private val regentReactions = setOf("👍", "❤️", "👀", "✅", "🎉", "😂", "🤔", "🙏", "")

private fun isQuietRegentReply(text: String): Boolean {
    val trimmed = text.trim()
    val token = "HEARTBEAT_OK"
    val aside = when {
        trimmed.startsWith(token) -> trimmed.removePrefix(token)
        trimmed.endsWith(token) -> trimmed.removeSuffix(token)
        else -> return false
    }
    return aside.trim().length <= 300
}

private fun regentMetadata(part: MessagePart): JSONObject? {
    if (part.type != "tool" || part.state !in listOf("completed", "") || part.outcome.isNotEmpty()) return null
    val result = runCatching { JSONObject(part.output) }.getOrNull() ?: return null
    return if (result.opt("success") == true) result.optJSONObject("metadata") else null
}

fun regentReaction(parts: List<MessagePart>): String? = normalizeParts(parts).mapNotNull { part ->
    if (part.toolName == "react_to_message") (regentMetadata(part)?.opt("regent_reaction") as? String)?.takeIf { it in regentReactions } else null
}.lastOrNull()

fun regentDisplayParts(parts: List<MessagePart>, live: Boolean = false): List<MessagePart> = normalizeParts(parts).flatMap { part ->
    val text = part.text.trim()
    when {
        part.type == "text" && (isQuietRegentReply(text) || live && text.isNotEmpty() && "HEARTBEAT_OK".startsWith(text)) -> emptyList()
        part.toolName == "send_message" && regentMetadata(part)?.optJSONArray("regent_messages") != null -> {
            val items = regentMetadata(part)!!.getJSONArray("regent_messages")
            val texts = (0 until items.length()).map { items.opt(it) }
            if (texts.isNotEmpty() && texts.all { it is String && it.isNotBlank() }) texts.mapIndexedNotNull { index, item ->
                val value = item as String
                if (isQuietRegentReply(value)) null else MessagePart("text", text = value, messageId = "${part.toolCallId}:$index", regentBubble = true)
            } else listOf(part)
        }
        part.toolName == "react_to_message" && regentReaction(listOf(part)) != null -> emptyList()
        part.toolName in listOf("send_message", "react_to_message") && part.state == "running" && part.output.isEmpty() -> emptyList()
        else -> listOf(part)
    }
}

fun regentMessages(rows: List<DisplayMessage>, liveParts: List<MessagePart> = emptyList()): List<DisplayMessage> {
    val result = mutableListOf<DisplayMessage>()
    var userIndex: Int? = null
    for (row in rows) {
        if (row.role == "user") { userIndex = result.size; result.add(row); continue }
        if (row.role in listOf("system_triggered", "trigger")) userIndex = null
        userIndex?.let { index -> regentReaction(row.parts)?.let { result[index] = result[index].copy(reaction = it) } }
        val parts = regentDisplayParts(row.parts)
        if (parts.isNotEmpty()) result.add(row.copy(parts = parts))
    }
    userIndex?.let { index -> regentReaction(liveParts)?.let { result[index] = result[index].copy(reaction = it) } }
    return result
}

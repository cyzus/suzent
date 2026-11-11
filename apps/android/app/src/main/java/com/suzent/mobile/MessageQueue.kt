package com.suzent.mobile

import java.util.UUID

/** A message held until its conversation's running turn ends, as Cmd/Ctrl+Enter does on desktop. */
data class QueuedMessage(val text: String, val attachments: List<PendingAttachment> = emptyList(), val id: String = UUID.randomUUID().toString())

/** Each conversation's queued messages, oldest first. */
data class MessageQueues(private val byChat: Map<String, List<QueuedMessage>> = emptyMap()) {
    fun of(chatId: String?): List<QueuedMessage> = chatId?.let(byChat::get).orEmpty()
    fun add(chatId: String, item: QueuedMessage) = MessageQueues(byChat + (chatId to of(chatId) + item))
    fun remove(chatId: String, id: String) = MessageQueues(byChat + (chatId to of(chatId).filterNot { it.id == id }))
    fun clear(chatId: String) = MessageQueues(byChat - chatId)
    val attachments: List<PendingAttachment> get() = byChat.values.flatten().flatMap { it.attachments }
}

/** The assistant's partial reply, kept on screen when a redirect cuts its turn short. */
fun interruptedReply(parts: List<MessagePart>, model: String?): ChatMessage? {
    if (parts.isEmpty()) return null
    // As desktop does: a tool cut off mid-run or awaiting approval did not finish.
    val settled = parts.map { part ->
        when {
            part.type == "tool" && part.state in listOf("running", "approval-requested") -> part.copy(state = "error")
            part.state == "running" -> part.copy(state = "completed")
            else -> part
        }
    }
    return ChatMessage("assistant", settled.filter { it.type == "text" }.joinToString("\n\n") { it.text }, settled, model = model)
}

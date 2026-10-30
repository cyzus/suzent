package com.suzent.mobile

import org.json.JSONObject

/** Conversation operations shared by the real transport and the offline demonstration. */
interface MobileClient {
    val supportsAttachments: Boolean
    val supportsScheduledTasks: Boolean
    fun close()
    fun cancelLive()
    suspend fun session(): ClientDevice
    suspend fun chats(): List<Chat>
    suspend fun chatPage(query: ChatPageQuery, offset: Int = 0, limit: Int = 30): ChatPage = localChatPage(chats(), query, offset, limit)
    suspend fun navigationMetadata(): NavigationMetadata {
        val rows = chats()
        return NavigationMetadata(rows.firstOrNull { it.isRegent }, projects().map { project ->
            project.copy(chatCount = rows.count { it.projectId == project.id && !it.isRegent && !it.isScheduled && !it.pinned })
        })
    }
    suspend fun chatStatuses(ids: List<String>): List<Chat> = chats().filter { it.id in ids.toSet() }
    suspend fun projects(): List<Project>
    suspend fun scheduledTasks(): List<ScheduledTask>
    suspend fun composer(): Chat
    suspend fun create(title: String, projectId: String? = null): Chat
    suspend fun chat(id: String): Chat
    suspend fun markRead(id: String)
    suspend fun manageChat(id: String, action: String, value: String? = null)
    suspend fun messageAction(id: String, index: Int, action: String, text: String? = null, model: String? = null): String
    suspend fun upload(id: String, attachments: List<PendingAttachment>): List<String>
    suspend fun send(id: String, text: String, model: String? = null, attachments: List<String> = emptyList())
    suspend fun stop(id: String)
    suspend fun approvals(id: String): ApprovalState
    suspend fun decideApprovals(id: String, pending: List<ApprovalRequest>, choices: Map<String, String>)
    suspend fun observe(id: String, event: suspend (JSONObject) -> Unit)
}

package com.suzent.mobile

import java.io.File
import org.json.JSONObject

/** Conversation operations shared by the real transport and the offline demonstration. */
interface MobileClient {
    val supportsAttachments: Boolean
    val supportsScheduledTasks: Boolean
    val supportsChatOverview: Boolean
    val supportsSurfaces: Boolean
    val supportsSteer: Boolean
    fun close()
    fun cancelLive()
    suspend fun session(): ClientDevice
    suspend fun chats(): List<Chat>
    suspend fun chatPage(query: ChatPageQuery, offset: Int = 0, limit: Int = 30): ChatPage = localChatPage(chats(), query, offset, limit)
    suspend fun navigationMetadata(): NavigationMetadata {
        val rows = chats()
        return NavigationMetadata(rows.firstOrNull { it.isRegent }, projects().map { project ->
            val members = rows.filter { it.projectId == project.id && !it.isRegent }
            project.copy(chatCount = members.count { !it.isScheduled && !it.pinned },
                running = members.any { it.running }, unread = members.any { it.unread > 0 })
        })
    }
    suspend fun chatStatuses(ids: List<String>): List<Chat> = chats().filter { it.id in ids.toSet() }
    suspend fun projects(): List<Project>
    suspend fun scheduledTasks(): List<ScheduledTask>
    suspend fun composer(): Chat
    suspend fun create(title: String, projectId: String? = null): Chat
    suspend fun chat(id: String): Chat
    suspend fun markRead(id: String)
    suspend fun overview(id: String): ChatOverview
    suspend fun manageChat(id: String, action: String, value: String? = null)
    suspend fun messageAction(id: String, index: Int, action: String, text: String? = null, model: String? = null): String
    suspend fun upload(id: String, attachments: List<PendingAttachment>): List<String>
    suspend fun send(id: String, text: String, model: String? = null, attachments: List<String> = emptyList())
    suspend fun stop(id: String)
    /** Interrupts the running turn and continues it with [text]; a turn that already ended simply gets [text] next. */
    suspend fun steer(id: String, text: String, model: String? = null)
    suspend fun approvals(id: String): ApprovalState
    suspend fun answerSurface(id: String, surfaceId: String, answer: Map<String, Any?>)
    suspend fun decideApprovals(id: String, pending: List<ApprovalRequest>, choices: Map<String, String>)
    suspend fun observe(id: String, event: suspend (JSONObject) -> Unit)
    /** Downloads a tool's image, video or audio into [destination]. */
    suspend fun media(chatId: String, mediaId: String, destination: File): Unit = throw UnsupportedOperationException()
}

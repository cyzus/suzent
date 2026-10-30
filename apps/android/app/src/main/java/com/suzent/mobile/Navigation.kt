package com.suzent.mobile

import org.json.JSONObject

data class ChatPageQuery(val kind: String = "recent", val value: String = "")
data class ChatPage(val chats: List<Chat>, val total: Int, val nextOffset: Int?) {
    fun appending(page: ChatPage): ChatPage {
        val incoming = page.chats.map { it.id }.toSet()
        return ChatPage(chats.filterNot { it.id in incoming } + page.chats, page.total, page.nextOffset)
    }
    companion object {
        fun parse(value: JSONObject): ChatPage {
            val array = value.getJSONArray("chats")
            return ChatPage((0 until array.length()).map { Chat.parse(array.getJSONObject(it)) },
                value.getInt("total"), if (value.isNull("nextOffset")) null else value.getInt("nextOffset"))
        }
    }
}
data class NavigationMetadata(val regent: Chat?, val projects: List<Project>)
data class InitialNavigation(val metadata: NavigationMetadata, val recent: ChatPage, val pinned: ChatPage) {
    val chats get() = listOfNotNull(metadata.regent) + pinned.chats + recent.chats
}
fun localChatPage(chats: List<Chat>, query: ChatPageQuery, offset: Int, limit: Int): ChatPage {
    val rows = chats.filter { chat ->
        !chat.isRegent && when (query.kind) {
            "search" -> chat.title.contains(query.value, ignoreCase = true)
            "pinned" -> !chat.isScheduled && chat.pinned
            "project" -> !chat.isScheduled && !chat.pinned && chat.projectId == query.value
            else -> !chat.isScheduled && !chat.pinned
        }
    }
    val page = rows.drop(offset).take(limit)
    val next = offset + page.size
    return ChatPage(page, rows.size, next.takeIf { it < rows.size })
}
suspend fun MobileClient.initialNavigation(): InitialNavigation = InitialNavigation(
    navigationMetadata(), chatPage(ChatPageQuery()), chatPage(ChatPageQuery("pinned")))

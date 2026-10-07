package com.suzent.mobile

val Chat.isSubagent: Boolean get() = platform.equals("subagent", ignoreCase = true)
val Chat.isScheduled: Boolean get() = platform.equals("cron", ignoreCase = true)

data class SidebarChatEntry(val chat: Chat, val depth: Int, val childCount: Int)

fun scheduledChatIds(chats: List<Chat>): Set<String> {
    val byId = chats.associateBy { it.id }
    return chats.filter { chat ->
        var current: Chat? = chat
        val seen = mutableSetOf<String>()
        var scheduled = false
        while (current != null && seen.add(current.id)) {
            if (current.isScheduled) { scheduled = true; break }
            current = if (current.isSubagent) byId[current.parentChatId] else null
        }
        scheduled
    }.map { it.id }.toSet()
}

fun sidebarChats(chats: List<Chat>, search: String, expanded: Set<String>): List<SidebarChatEntry> {
    val byId = chats.associateBy { it.id }
    val order = chats.mapIndexed { index, chat -> chat.id to index }.toMap()
    fun root(chat: Chat): String {
        var current = chat
        val path = mutableListOf<String>()
        while (true) {
            val cycle = path.indexOf(current.id)
            if (cycle >= 0) return path.drop(cycle).minBy { order.getValue(it) }
            path.add(current.id)
            current = if (current.isSubagent) byId[current.parentChatId] ?: return current.id else return current.id
        }
    }
    val roots = chats.associate { it.id to root(it) }
    val children = chats.filter { roots[it.id] != it.id }.groupBy { roots[it.id] }
    val query = search.trim()
    val result = mutableListOf<SidebarChatEntry>()
    for (chat in chats.filter { roots[it.id] == it.id }) {
        val descendants = children[chat.id].orEmpty()
        val matches = descendants.filter { it.title.contains(query, ignoreCase = true) }
        if (!chat.title.contains(query, ignoreCase = true) && matches.isEmpty()) continue
        result.add(SidebarChatEntry(chat, 0, descendants.size))
        if (query.isNotEmpty() || chat.id in expanded) matches.forEach { result.add(SidebarChatEntry(it, 1, 0)) }
    }
    return result
}

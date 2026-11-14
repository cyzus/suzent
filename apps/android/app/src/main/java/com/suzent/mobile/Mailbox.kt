package com.suzent.mobile

import org.json.JSONObject

data class MailboxItem(val id: Int, val source: String, val eventType: String, val summary: String,
    val payload: String, val status: String, val chatId: String?, val createdAt: String, val readAt: String?, val presentation: MailboxPresentation? = null) {
    val unread: Boolean get() = status == "notified" && readAt == null
    companion object {
        fun parse(value: JSONObject) = MailboxItem(value.getInt("id"), value.getString("source"),
            value.getString("eventType"), value.getString("summary"), value.getString("payload"),
            value.getString("status"), value.opt("chatId") as? String, value.getString("createdAt"), value.opt("readAt") as? String, value.optJSONObject("presentation")?.let(MailboxPresentation::parse))
    }
}

data class MailboxPage(val items: List<MailboxItem> = emptyList(), val unread: Int = 0, val hasMore: Boolean = false) {
    companion object {
        fun parse(value: JSONObject): MailboxPage {
            val items = value.getJSONArray("items")
            return MailboxPage((0 until items.length()).map { MailboxItem.parse(items.getJSONObject(it)) },
                value.getInt("unread"), value.getBoolean("hasMore"))
        }
    }
}

internal suspend fun mailboxWindow(lastOffset: Int, fetch: suspend (Int) -> MailboxPage): MailboxPage {
    val items = linkedMapOf<Int, MailboxItem>()
    var page = MailboxPage()
    for (offset in 0..lastOffset step 50) {
        page = fetch(offset)
        page.items.forEach { items.putIfAbsent(it.id, it) }
        if (!page.hasMore) break
    }
    return MailboxPage(items.values.toList(), page.unread, page.hasMore)
}

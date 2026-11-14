package com.suzent.mobile

import org.json.JSONObject

data class MailboxPresentation(val threadKey: String?, val title: String, val context: String?, val source: String,
                               val activity: String?, val icon: String, val detail: String? = null) {
    companion object {
        fun parse(value: JSONObject) = MailboxPresentation(value.opt("threadKey") as? String, value.getString("title"),
            value.opt("context") as? String, value.getString("source"), value.opt("activity") as? String,
            value.optString("icon", "inbox"), value.opt("detail") as? String)
    }
}

val MailboxItem.display: MailboxPresentation get() = presentation
    ?: MailboxPresentation(null, summary, null, source, null, "inbox")

data class MailboxThread(val key: String, val items: List<MailboxItem>) {
    val latest: MailboxItem get() = items.first()
    val unreadIds: List<Int> get() = items.filter { it.unread }.map { it.id }
}

fun mailboxThreads(items: List<MailboxItem>): List<MailboxThread> = items.distinctBy { it.id }.sortedByDescending { it.id }
    .groupBy { it.presentation?.threadKey?.takeIf(String::isNotBlank) ?: "item:${it.id}" }
    .map { (key, group) -> MailboxThread(key, group) }

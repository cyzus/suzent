package com.suzent.mobile

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MailboxTest {
    @Test fun serverCountIsAuthoritativeAndEventsAreNotUnreadNotifications() {
        val page = MailboxPage.parse(JSONObject(javaClass.getResource("/mailbox-fixture.json")!!.readText()))
        assertEquals(7, page.unread)
        assertTrue(page.hasMore)
        assertEquals(listOf(true, false, false), page.items.map { it.unread })
        assertNull(page.items[0].chatId)
        assertEquals("shared", page.items[1].chatId)
        assertEquals(listOf("schedule", "agent_inbox", "webhook"), page.items.map { it.sourceKind })
    }
    @Test fun rendersBackendPresentationAndGroupsOnlyByServerKey() {
        val fixtures = org.json.JSONArray(javaClass.getResource("/mailbox-thread-fixtures.json")!!.readText())
        for (index in 0 until fixtures.length()) {
            val fixture = fixtures.getJSONObject(index).getJSONObject("presentation")
            val result = MailboxPresentation.parse(fixture)
            assertEquals(fixture.getString("title"), result.title)
            assertEquals(fixture.getString("threadKey"), result.threadKey)
            assertEquals(fixture.opt("detail") as? String, result.detail)
        }
        val base = MailboxPage.parse(JSONObject(javaClass.getResource("/mailbox-fixture.json")!!.readText())).items.first()
        val presentation = MailboxPresentation("thread-a", "Subject", null, "any-webhook", null, "inbox")
        val first = base.copy(id = 1, presentation = presentation)
        val latest = base.copy(id = 6, readAt = "read", presentation = presentation)
        val other = base.copy(id = 2, presentation = presentation.copy(threadKey = "thread-b"))
        val legacy = base.copy(id = 3)
        val threads = mailboxThreads(listOf(first, latest, latest, other, legacy))
        assertEquals(3, threads.size)
        assertEquals(listOf(6, 1), threads.first().items.map { it.id })
        assertEquals(listOf(1), threads.first().unreadIds)
        assertEquals(2, mailboxThreads(listOf(legacy, legacy.copy(id = 4))).size)
    }
    @Test fun continuousInboxKeepsLoadedEventsAndDeduplicatesPageOverlap() = kotlinx.coroutines.runBlocking {
        val fixture = MailboxPage.parse(JSONObject(javaClass.getResource("/mailbox-fixture.json")!!.readText())).items.first()
        val calls = mutableListOf<Int>()
        val result = mailboxWindow(100) { offset ->
            calls.add(offset)
            when (offset) {
                0 -> MailboxPage(listOf(fixture.copy(id = 3), fixture.copy(id = 2)), 7, true)
                else -> MailboxPage(listOf(fixture.copy(id = 2), fixture.copy(id = 1)), 6, false)
            }
        }
        assertEquals(listOf(0, 50), calls)
        assertEquals(listOf(3, 2, 1), result.items.map { it.id })
        assertEquals(6, result.unread)
        assertFalse(result.hasMore)
    }
}

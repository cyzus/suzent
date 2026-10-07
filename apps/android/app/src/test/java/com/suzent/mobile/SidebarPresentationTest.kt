package com.suzent.mobile

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SidebarPresentationTest {
    @Test fun sharedHierarchyFixtures() {
        val fixture = JSONObject(requireNotNull(javaClass.classLoader?.getResourceAsStream("sidebar-fixtures.json"))
            .bufferedReader().use { it.readText() })
        val source = fixture.getJSONArray("chats")
        val chats = (0 until source.length()).map { Chat.parse(source.getJSONObject(it)) }
        val cases = fixture.getJSONArray("cases")
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val expanded = case.getJSONArray("expanded")
            val rows = sidebarChats(chats, case.getString("search"), (0 until expanded.length()).map { expanded.getString(it) }.toSet())
            val ids = case.getJSONArray("ids")
            val depths = case.getJSONArray("depths")
            assertEquals((0 until ids.length()).map { ids.getString(it) }, rows.map { it.chat.id })
            assertEquals((0 until depths.length()).map { depths.getInt(it) }, rows.map { it.depth })
        }
        assertTrue(chats.first().isSubagent)
        assertTrue(chats.last().isScheduled)
        assertEquals(2, sidebarChats(chats, "", emptySet()).first().childCount)
    }

    @Test fun cyclesRemainVisibleAndFinite() {
        val chats = listOf(Chat("a", "A", false, emptyList(), platform = "subagent", parentChatId = "b"),
            Chat("b", "B", false, emptyList(), platform = "subagent", parentChatId = "a"))
        assertEquals(listOf("a", "b"), sidebarChats(chats, "", setOf("a", "b")).map { it.chat.id })
    }

    @Test fun taskWithoutConversationIsNotOpenable() {
        val task = ScheduledTask.parse(JSONObject("""{"id":"7","name":"Report","active":true,"chatId":null,"nextRunAt":null,"isRunning":false,"hasError":false}"""))
        assertNull(task.chatId)
        assertNull(task.nextRunAt)
        assertFalse(task.hasError)
    }

    @Test fun scheduledDescendantsStayInTheTaskSection() {
        val chats = listOf(Chat("cron-1", "Report", false, emptyList(), platform = "cron"),
            Chat("child", "Check sources", false, emptyList(), platform = "subagent", parentChatId = "cron-1"),
            Chat("regular", "Regular", false, emptyList()))
        assertEquals(setOf("cron-1", "child"), scheduledChatIds(chats))
    }
}

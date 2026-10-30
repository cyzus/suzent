package com.suzent.mobile

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class NavigationTest {
    @Test fun demoPagesSearchAndPinsIndependently() = runBlocking {
        val fixture = requireNotNull(javaClass.classLoader?.getResource("demo.json")).readText()
        val client = DemoClient(fixture, language = "en")
        repeat(35) { client.create("Page $it", "demo-home") }
        val initial = client.initialNavigation()
        assertEquals(30, initial.recent.chats.size)
        assertEquals(30, initial.recent.nextOffset)
        assertEquals(listOf("demo-welcome"), initial.pinned.chats.map { it.id })
        assertTrue(initial.metadata.regent?.isRegent == true)
        val second = client.chatPage(ChatPageQuery(), 30)
        assertNull(second.nextOffset)
        assertTrue(initial.recent.chats.map { it.id }.toSet().intersect(second.chats.map { it.id }.toSet()).isEmpty())
        assertEquals(listOf("demo-failure"), client.chatPage(ChatPageQuery("search", "unavailable")).chats.map { it.id })
        assertEquals(39, initial.metadata.projects.first { it.id == "demo-home" }.chatCount)
    }
    @Test fun appendedPagesDeduplicateUpdatedRows() {
        val first = ChatPage(listOf(Chat("a", "Old", false, emptyList()), Chat("b", "B", false, emptyList())), 3, 2)
        val next = ChatPage(listOf(Chat("a", "New", false, emptyList()), Chat("c", "C", false, emptyList())), 3, null)
        val merged = first.appending(next)
        assertEquals(3, merged.chats.map { it.id }.toSet().size)
        assertEquals("New", merged.chats.first { it.id == "a" }.title)
        assertNull(merged.nextOffset)
    }
}

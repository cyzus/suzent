package com.suzent.mobile

import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ChatDetailsTest {
    private val fixture = JSONObject(File("../../../packages/mobile-contract/chat-details-fixtures.json").readText())

    @Test fun detailsDecodeTheSharedFixture() {
        val details = ChatDetails.parse(fixture.getJSONObject("details"))
        assertEquals("auto", details.permissionMode.mode)
        assertTrue(details.permissionMode.canChange)
        assertEquals(24, details.context?.percent)
        assertEquals("Plan the Kyoto trip", details.goal?.objective)
        assertEquals(listOf("completed", "in_progress", "blocked"), details.tasks.map { it.status })
        assertEquals("Finding a ryokan", details.tasks[1].activeForm)
        assertNull(details.tasks[0].activeForm)
        assertEquals(listOf(true, false), details.agents.map { it.isActive })
        assertNull(details.agents[1].chatId)
        assertEquals("Travelling to Kyoto in April", details.memory?.saved?.first()?.content)
        assertTrue(details.files)

        val minimal = ChatDetails.parse(fixture.getJSONObject("minimal"))
        assertNull(minimal.context)
        assertNull(minimal.goal)
        assertNull(minimal.memory)
        assertFalse(minimal.files)
        assertFalse(minimal.permissionMode.canChange)

        val listing = WorkspaceListing.parse(fixture.getJSONObject("files"))
        assertEquals("uploads", listing.path)
        assertEquals(listOf(true, false), listing.entries.map { it.isDir })
        assertEquals(204800L, listing.entries[1].size)
    }

    @Test fun sharedHelpersMatchIos() {
        val percents = fixture.getJSONArray("contextPercent")
        for (index in 0 until percents.length()) {
            val item = percents.getJSONObject(index)
            assertEquals(item.getInt("percent"), contextPercent(item.getInt("tokens"), item.getInt("limit")))
        }
        assertEquals(0, contextPercent(10, 0))
        val paths = fixture.getJSONArray("paths")
        for (index in 0 until paths.length()) {
            val item = paths.getJSONObject(index)
            val child = workspaceChildPath(item.getString("parent"), item.getString("name"))
            assertEquals(item.getString("child"), child)
            assertEquals(item.getString("parent"), workspaceParentPath(child))
        }
        assertEquals("photo.png", workspaceDisplayName("uploads/photo.png"))
        assertEquals("file", workspaceDisplayName(""))
    }
}

package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class ChatPresentationTest {
    @Test fun nativePresentationContract() {
        val cases = JSONArray(requireNotNull(javaClass.classLoader?.getResourceAsStream("presentation-fixtures.json"))
            .bufferedReader().use { it.readText() })
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val chat = Chat.parse(JSONObject().put("id", "fixture").put("messages", case.getJSONArray("messages")))
            val rows = presentMessages(chat.messages)
            val texts = case.getJSONArray("texts")
            val activities = case.getJSONArray("activities")
            assertEquals(case.getString("name"), texts.length(), rows.size)
            rows.forEachIndexed { row, message ->
                assertEquals(case.getString("name"), texts.getString(row), message.text)
                assertEquals(case.getString("name"), activities.getInt(row), message.parts.count { it.type != "text" })
            }
        }
    }

    @Test fun sharedActivityReplayContract() {
        val cases = JSONArray(requireNotNull(javaClass.classLoader?.getResourceAsStream("activity-fixtures.json")).bufferedReader().use { it.readText() })
        for (index in 0 until cases.length()) {
            val fixture = cases.getJSONObject(index)
            val buffer = LiveActivityBuffer()
            val events = fixture.getJSONArray("events")
            for (i in 0 until events.length()) buffer.consume(events.getJSONObject(i))
            val parts = requireNotNull(buffer.drain())
            fun strings(key: String) = fixture.getJSONArray(key).let { a -> (0 until a.length()).map { a.getString(it) } }
            assertEquals(fixture.getString("name"), strings("types"), parts.map { it.type })
            assertEquals(strings("args"), parts.map { it.args })
            assertEquals(strings("outputs"), parts.map { it.output })
            assertEquals(strings("texts"), parts.map { it.text })
            assertEquals(strings("states"), parts.map { it.state })
            val chunks = fixture.getJSONArray("chunks")
            assertEquals((0 until chunks.length()).map { chunks.getInt(it) }, activityChunks(parts).map { it.size })
            assertEquals(null, buffer.drain())
        }
    }

    @Test fun batchesDeltasAndFlushesFinalChunk() {
        val buffer = LiveActivityBuffer()
        repeat(100) { buffer.consume(JSONObject().put("type", "TEXT_MESSAGE_CONTENT").put("delta", "a")) }
        assertEquals("a".repeat(100), buffer.drain()?.single()?.text)
        assertEquals(null, buffer.drain())
        buffer.consume(JSONObject().put("type", "TEXT_MESSAGE_CONTENT").put("delta", "尾"))
        assertEquals("a".repeat(100) + "尾", buffer.drain()?.single()?.text)
        buffer.consume(JSONObject().put("type", "STREAM_RESET"))
        assertEquals(emptyList<MessagePart>(), buffer.drain())
    }
}

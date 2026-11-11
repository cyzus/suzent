package com.suzent.mobile

import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test

class ProtocolTest {
    @Test fun originsAreValidated() {
        listOf("http://desktop:25314", "https://user:secret@desktop", "https://desktop/api",
            "https://desktop?q=1", "https://desktop#fragment", "file:///etc/passwd").forEach {
            assertTrue(it, runCatching { Backend.parse(it) }.isFailure)
        }
        assertEquals("http://[::1]:25314/chats", Backend.parse("http://[::1]:25314/", true).endpoint("chats").toString())
    }

    @Test fun sharedFixturesMatchBackend() {
        val fixture = JSONObject(requireNotNull(javaClass.classLoader?.getResourceAsStream("fixtures.json"))
            .bufferedReader().use { it.readText() })
        val decoder = SSEDecoder()
        val events = fixture.getString("sse").split("\n").mapNotNull { decoder.consume(it) }
        assertEquals(2, events.size)
        assertEquals(fixture.getString("delta"), JSONObject(events.first()).getString("delta"))
        assertEquals(normalize(fixture.getJSONObject("connect")), normalize(NodeProtocol.connect("Suzent Mobile", "ios", "")))
        assertEquals(normalize(fixture.getJSONObject("result")), normalize(NodeProtocol.reply(fixture.getJSONObject("invoke"), "ios")))
    }

    @Test fun rejectsUnadvertisedCapabilities() {
        val result = NodeProtocol.reply(JSONObject().put("type", "invoke").put("request_id", "one")
            .put("command", "camera.snap"), "android")
        assertFalse(requireNotNull(result).getBoolean("success"))
        assertEquals("pong", NodeProtocol.reply(JSONObject().put("type", "ping"), "android")?.getString("type"))
        assertNull(NodeProtocol.reply(JSONObject().put("type", "invoke"), "android"))
    }

    @Test fun toolMediaIsParsedAndValidated() {
        val id = "0123456789abcdef0123456789abcdef"
        val chat = Chat.parse(JSONObject("""{"id":"c","messages":[{"role":"assistant","parts":[{"type":"tool","toolName":"check_video",
            "media":[{"id":"$id","kind":"video","name":"clip.MP4"},{"id":"../x","kind":"video","name":"bad.mp4"},{"id":"$id","kind":"script","name":"x.js"}]}]}]}"""))
        val media = chat.messages.single().parts.single().media
        assertEquals(listOf(MediaItem(id, "video", "clip.MP4")), media)
        assertEquals("mp4", media.single().extension)
        assertEquals("a_b.pdf", MediaItem(id, "file", "a/b.pdf").safeName)
        assertEquals("file.bin", MediaItem(id, "file", "..").safeName)
    }

    private fun normalize(value: Any?): Any? = when (value) {
        is JSONObject -> value.keys().asSequence().associateWith { normalize(value.get(it)) }
        is JSONArray -> (0 until value.length()).map { normalize(value.get(it)) }
        else -> value
    }
}

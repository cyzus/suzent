package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.MockResponse

class StreamRecoveryTest {
    @Test fun sharedRecoveryContract() {
        val fixtures = JSONArray(requireNotNull(javaClass.classLoader?.getResourceAsStream("recovery-fixtures.json"))
            .bufferedReader().use { it.readText() })
        val recovery = StreamRecovery()
        var text = ""
        for (index in 0 until fixtures.length()) {
            val fixture = fixtures.getJSONObject(index)
            val result = runCatching { recovery.consume(fixture.getJSONObject("frame")) }
            assertEquals("frame $index", fixture.getBoolean("error"), result.isFailure)
            result.getOrNull()?.forEach { event ->
                if (event.optString("type") == "STREAM_RESET") text = ""
                if (event.optString("type") == "TEXT_MESSAGE_CONTENT") text += event.optString("delta")
            }
            assertEquals(fixture.getString("text"), text)
            assertEquals(fixture.getBoolean("ended"), recovery.ended)
            assertEquals(fixture.getBoolean("persisted"), recovery.persisted)
        }
    }

    @Test fun failedSaveIsNotTreatedAsCompletionOrRetried() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setHeader("Content-Type", "text/event-stream").setBody(
            "data: {\"type\":\"STREAM_SNAPSHOT\",\"run_id\":\"r\",\"seq\":0,\"events\":[]}\n\ndata: {\"type\":\"STREAM_END\",\"run_id\":\"r\",\"seq\":0,\"persisted\":false}\n\n"))
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "fixture")
        try {
            assertTrue(runCatching { client.observe("chat") {} }.isFailure)
            assertEquals(1, server.requestCount)
        } finally { client.close(); server.shutdown() }
    }

    @Test fun interruptedObserverResumesCursorWithoutResending() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setHeader("Content-Type", "text/event-stream").setBody(
            "data: {\"type\":\"STREAM_SNAPSHOT\",\"run_id\":\"run\",\"seq\":1,\"events\":[{\"type\":\"TEXT_MESSAGE_CONTENT\",\"delta\":\"hello\"}]}\n\n"))
        server.enqueue(MockResponse().setHeader("Content-Type", "text/event-stream").setBody(
            "data: {\"type\":\"STREAM_EVENT\",\"run_id\":\"run\",\"seq\":2,\"event\":{\"type\":\"TEXT_MESSAGE_CONTENT\",\"delta\":\" world\"}}\n\ndata: {\"type\":\"STREAM_END\",\"run_id\":\"run\",\"seq\":2,\"persisted\":true}\n\n"))
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "fixture")
        try {
            var text = ""
            client.observe("chat") { event ->
                if (event.optString("type") == "STREAM_RESET") text = ""
                if (event.optString("type") == "TEXT_MESSAGE_CONTENT") text += event.optString("delta")
            }
            assertEquals("hello world", text)
            assertEquals("/mobile/client/live", server.takeRequest().path)
            val resumed = server.takeRequest()
            assertEquals("/mobile/client/live", resumed.path)
            assertEquals(1, JSONObject(resumed.body.readUtf8()).getInt("after_seq"))
            assertEquals(2, server.requestCount)
        } finally { client.close(); server.shutdown() }
    }
}

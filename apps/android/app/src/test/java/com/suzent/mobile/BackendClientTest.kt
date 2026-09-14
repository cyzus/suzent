package com.suzent.mobile

import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class BackendClientTest {
    @Test fun readRecoversFromClosedPooledConnection() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("""{"chats":[]}"""))
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
        server.enqueue(MockResponse().setBody("""{"chats":[]}"""))
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "fixture-token")
        try {
            client.chats()
            assertTrue(client.chats().isEmpty())
            assertEquals(3, server.requestCount)
        } finally { client.close(); server.shutdown() }
    }

    @Test fun sendIsNotRetriedAfterLostAcknowledgment() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
        server.enqueue(MockResponse().setBody("{}"))
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "fixture-token")
        try {
            assertTrue(runCatching { client.send("test", "hello") }.isFailure)
            assertEquals(1, server.requestCount)
        } finally { client.close(); server.shutdown() }
    }

    @Test fun authenticatedChatLifecycleAndUnicodeStream() = runBlocking {
        val server = MockWebServer()
        val chat = """{"id":"test","title":"Phone","messages":[{"role":"assistant","content":"你好 🌱"}]}"""
        server.enqueue(MockResponse().setBody("""{"chats":[$chat]}"""))
        server.enqueue(MockResponse().setResponseCode(201).setBody(chat))
        server.enqueue(MockResponse().setResponseCode(202).setBody("""{"chat_id":"test"}"""))
        server.enqueue(MockResponse().setHeader("Content-Type", "text/event-stream").setBody(
            "data: {\"type\":\"STREAM_SNAPSHOT\",\"run_id\":\"r\",\"seq\":1,\r\ndata: \"events\":[{\"type\":\"TEXT_MESSAGE_CONTENT\",\"delta\":\"你好 🌱\"}]}\r\n\r\ndata: {\"type\":\"STREAM_END\",\"run_id\":\"r\",\"seq\":1,\"persisted\":true}\n\n"))
        server.enqueue(MockResponse().setBody("""{"status":"stopping"}"""))
        server.enqueue(MockResponse().setBody(chat))
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "fixture-token")
        try {
            assertEquals("test", client.chats().first().id)
            val created = client.create("Phone")
            client.send(created.id, "hello")
            var text = ""
            client.observe(created.id) { event ->
                if (event.optString("type") == "TEXT_MESSAGE_CONTENT") text += event.getString("delta")
            }
            assertEquals("你好 🌱", text)
            client.stop(created.id)
            assertEquals(text, client.chat(created.id).messages.first().content)
            val expected = listOf("GET /mobile/client/chats", "POST /mobile/client/chats", "POST /mobile/client/send", "POST /mobile/client/live",
                "POST /mobile/client/stop", "GET /mobile/client/chats/test")
            expected.forEach { route ->
                val request = requireNotNull(server.takeRequest(1, TimeUnit.SECONDS))
                assertEquals(route, "${request.method} ${request.path}")
                assertEquals("Bearer fixture-token", request.getHeader("Authorization"))
                if (request.path == "/mobile/client/live") assertEquals(1, JSONObject(request.body.readUtf8()).getInt("protocol"))
                if (request.path == "/mobile/client/send") {
                    val body = JSONObject(request.body.readUtf8())
                    assertEquals("hello", body.getString("message"))
                    assertEquals("test", body.getString("chat_id"))
                }
            }
        } finally { client.close(); server.shutdown() }
    }

    @Test fun redirectsAreNotFollowed() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "/elsewhere"))
        server.enqueue(MockResponse().setBody("""{"chats":[]}"""))
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "fixture-token")
        try {
            assertTrue(runCatching { client.chats() }.isFailure)
            assertEquals(1, server.requestCount)
        } finally { client.close(); server.shutdown() }
    }
    @Test fun revokedStreamFailsWithoutRetry() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(401))
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "revoked")
        try {
            val error = runCatching { client.observe("test") {} }.exceptionOrNull()
            assertTrue(error is BackendClient.HttpFailure && error.code == 401)
            assertEquals(1, server.requestCount)
        } finally { client.close(); server.shutdown() }
    }

}

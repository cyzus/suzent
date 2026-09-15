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


    @Test fun pairingProbeFallsBackWithoutCredentialsOrMutations() = runBlocking {
        val first = MockWebServer()
        val second = MockWebServer()
        first.enqueue(MockResponse().setResponseCode(503))
        second.enqueue(MockResponse().setBody("""{"client_protocol":1,"pairing_protocol":1,"stream_protocols":[1]}"""))
        first.start(); second.start()
        try {
            val origins = listOf(first.url("/").toString(), second.url("/").toString())
            val invitation = PairingInvitation(origins.first(), "a".repeat(32), "b".repeat(43),
                System.currentTimeMillis() / 1000.0 + 300, origins)
            val selected = resolvePairingInvitation(invitation) { origin ->
                val probe = BackendClient(Backend.parse(origin, true), "", probeOnly = true)
                try { probe.capabilities() } finally { probe.close() }
            }
            assertEquals(origins[1], selected.first.origin)
            for (server in listOf(first, second)) {
                assertEquals(1, server.requestCount)
                val request = server.takeRequest(1, TimeUnit.SECONDS)!!
                assertEquals("GET", request.method)
                assertEquals("/mobile/capabilities", request.path)
                assertNull(request.getHeader("Authorization"))
                assertEquals(0L, request.bodySize)
            }
        } finally { first.shutdown(); second.shutdown() }
    }

    @Test fun phoneConfirmationReadsServerScopeThenExplicitlyAcceptsIt() = runBlocking {
        val server = MockWebServer()
        val id = "a".repeat(32)
        val expiry = System.currentTimeMillis() / 1000.0 + 300
        server.enqueue(MockResponse().setBody("""{"pairing_id":"$id","approval":"phone","desktop_name":"Test desktop","expires_at":$expiry,"permissions":{"chat_ids":["one"],"all_chats":false,"create_chats":false,"send":true,"stop":false}}"""))
        repeat(2) { server.enqueue(MockResponse().setBody("""{"pickup_secret":"test","expires_at":$expiry}""")) }
        server.start()
        val api = BackendClient(Backend.parse(server.url("/").toString(), true), "")
        val invitation = PairingInvitation(server.url("/").toString(), id, "b".repeat(43), expiry, phoneConfirmation = true)
        try {
            val selected = resolvePairingInvitation(invitation) { api.pairingPreview(invitation) }
            val preview = selected.second
            assertEquals(invitation.origin, selected.first.origin)
            assertEquals(1, server.requestCount)
            assertEquals("Test desktop", preview.desktopName)
            assertEquals(listOf("one"), preview.permissions.chatIds)
            assertFalse(preview.permissions.stop)
            val request = server.takeRequest(1, TimeUnit.SECONDS)!!
            assertNull(request.getHeader("Authorization"))
            assertEquals(setOf("pairing_id"), JSONObject(request.body.readUtf8()).keys().asSequence().toSet())
            api.claim(invitation, "Phone", confirmPermissions = true)
            val claim = JSONObject(server.takeRequest(1, TimeUnit.SECONDS)!!.body.readUtf8())
            assertTrue(claim.getBoolean("confirm_permissions"))
            assertFalse(claim.has("permissions"))
            api.claim(invitation.copy(phoneConfirmation = false), "Phone")
            val legacy = JSONObject(server.takeRequest(1, TimeUnit.SECONDS)!!.body.readUtf8())
            assertFalse(legacy.has("confirm_permissions"))
        } finally { api.close(); server.shutdown() }
    }

    @Test fun approvalUsesScopedEndpointWithoutPolicyFieldsOrRetries() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("""{"pending":[{"id":"one","kind":"tool","tool_name":"read_file","args":"{}","reason":"","actions":[{"id":"allow_once","behavior":"allow"}]}],"isRunning":false}"""))
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
        server.enqueue(MockResponse().setBody("{}"))
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "fixture-token")
        try {
            val state = client.approvals("shared")
            assertEquals("read_file", state.pending.single().toolName)
            assertTrue(runCatching { client.decideApprovals("shared", state.pending, mapOf("one" to "allow_once")) }.isFailure)
            assertEquals(2, server.requestCount)
            assertEquals("/mobile/client/chats/shared/approvals", server.takeRequest().path)
            val request = server.takeRequest()
            assertEquals("/mobile/client/approvals", request.path)
            val body = JSONObject(request.body.readUtf8())
            assertEquals("shared", body.getString("chat_id"))
            val choice = body.getJSONArray("decisions").getJSONObject(0)
            assertEquals(setOf("chat_id", "request_id", "kind", "action_id"), choice.keys().asSequence().toSet())
            assertEquals("allow_once", choice.getString("action_id"))
        } finally { client.close(); server.shutdown() }
    }
}

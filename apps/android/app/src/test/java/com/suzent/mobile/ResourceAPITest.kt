package com.suzent.mobile

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ResourceAPITest {
    @Test fun generatedDtosPreserveAllowedUnknownFields() {
        val source = JSONObject("""{"id":"chat","title":"Title","futureField":{"enabled":true}}""")
        val value = WireApiChat.fromJson(source)
        assertEquals(mapOf("enabled" to true), value.extraFields["futureField"])
        assertTrue(value.json().getJSONObject("futureField").getBoolean("enabled"))
    }

    @Test fun generatedRequestsKeepTypesAndEncodeIdentifiersOnce() {
        val page = ResourceRequests.chatPage(WireChatPageRequest("search", "旧会话", 30, 50))
        assertEquals(30, page.body!!.get("offset"))
        assertEquals("api/v1/chat-page", page.path(true))
        assertEquals("mobile/client/chat-page", page.path(false))
        val backend = Backend.parse("https://example.com")
        val call = ResourceRequests.chat("chat + 中文%2F")
        assertEquals("chat + 中文%2F", backend.endpoint(call.path).pathSegments.last())
        for (id in listOf("", ".", "..", "one/two")) {
            assertTrue(runCatching { ResourceRequests.chat(id) }.exceptionOrNull() is IllegalArgumentException)
        }
    }

    @Test(timeout = 5000) fun newBackendNegotiatesCommonRoutesBeforeMutations() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("""{"client_protocol":1,"stream_protocols":[1],"resource_api":1,"device":{"device_id":"phone","display_name":"Phone","permissions":{"chat_ids":[],"all_chats":true,"send":true,"stop":true,"create_chats":true}}}"""))
        server.enqueue(MockResponse().setBody("""{"models":["test/model"],"starredModels":[],"canManage":true}"""))
        server.enqueue(MockResponse().setBody("""{"models":["test/model"],"starredModels":[],"canManage":true}"""))
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "device-token")
        try {
            client.session()
            assertEquals(listOf("test/model"), client.resourceAPI.models().models)
            client.starModel("test/model", false)
            assertEquals("/mobile/client/session", server.takeRequest().path)
            assertEquals("/api/v1/models", server.takeRequest().path)
            val star = server.takeRequest()
            assertEquals("/api/v1/models/star", star.path)
            assertEquals(false, JSONObject(star.body.readUtf8()).get("starred"))
            assertEquals("Bearer device-token", star.getHeader("Authorization"))
        } finally { client.close(); server.shutdown() }
    }
}

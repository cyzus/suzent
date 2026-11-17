package com.suzent.mobile

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ModelCatalogClientTest {
    @Test(timeout = 5000) fun favoritesAndRefreshUsePairedEndpointsAndBooleanIntent() = runBlocking {
        val server = MockWebServer()
        val catalog = """{"models":["openrouter/org/model"],"starredModels":["openrouter/org/model"],"canManage":true}"""
        repeat(4) { server.enqueue(MockResponse().setBody(catalog)) }
        server.start()
        val client = BackendClient(Backend.parse(server.url("/").toString(), true), "paired-token")
        try {
            val result = client.modelCatalog()
            assertEquals(listOf("openrouter/org/model"), result.models)
            assertEquals(setOf("openrouter/org/model"), result.starredModels)
            assertTrue(result.canManage)
            client.starModel("openrouter/org/model", true)
            client.starModel("openrouter/org/model", false)
            client.modelCatalog(refresh = true)
            val read = server.takeRequest()
            assertEquals("GET", read.method)
            assertEquals("/mobile/client/models", read.path)
            for (starred in listOf(true, false)) {
                val request = server.takeRequest()
                assertEquals("POST", request.method)
                assertEquals("/mobile/client/models/star", request.path)
                assertEquals("Bearer paired-token", request.getHeader("Authorization"))
                val body = JSONObject(request.body.readUtf8())
                assertEquals("openrouter/org/model", body.getString("model"))
                assertEquals(starred, body.get("starred"))
            }
            val refresh = server.takeRequest()
            assertEquals("POST", refresh.method)
            assertEquals("/mobile/client/models/refresh", refresh.path)
            assertEquals("{}", refresh.body.readUtf8())
        } finally { client.close(); server.shutdown() }
    }
}

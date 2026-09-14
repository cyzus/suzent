package com.suzent.mobile

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

class BackendClient(val backend: Backend, private val token: String) {
    private val http = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS).build()
    private val reads = http.newBuilder().retryOnConnectionFailure(true).build()
    @Volatile private var liveCall: Call? = null

    private fun request(path: String, body: JSONObject? = null): Request = Request.Builder()
        .url(backend.endpoint(path)).header("Authorization", "Bearer $token")
        .apply { if (body != null) post(body.toString().toRequestBody("application/json".toMediaType())) }
        .build()

    private suspend fun json(path: String, body: JSONObject? = null): JSONObject = withContext(Dispatchers.IO) {
        val transport = if (body == null) reads else http
        transport.newCall(request(path, body)).execute().use { response ->
            if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
            JSONObject(response.body?.string() ?: throw IOException("Empty response"))
        }
    }

    suspend fun chats(): List<Chat> {
        val array = json("chats").getJSONArray("chats")
        return (0 until array.length()).map { Chat.parse(array.getJSONObject(it)) }
    }
    suspend fun create(title: String): Chat = Chat.parse(json("chats", JSONObject().put("title", title)))
    suspend fun chat(id: String): Chat {
        require(!id.contains('/') && id != "." && id != "..")
        return Chat.parse(json("chats/$id"))
    }
    suspend fun send(id: String, text: String) {
        json("chat/send", JSONObject().put("chat_id", id).put("message", text))
    }
    suspend fun stop(id: String) { json("chat/stop", JSONObject().put("chat_id", id)) }

    suspend fun observe(id: String, event: suspend (JSONObject) -> Unit) = withContext(Dispatchers.IO) {
        val call = http.newCall(request("chat/live", JSONObject().put("chat_id", id).put("wait_ms", 1000).put("replay", true)))
        liveCall = call
        try {
            call.execute().use { response ->
                if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
                if (response.code == 204) return@withContext
                if (response.body?.contentType()?.subtype != "event-stream") throw IOException("Invalid stream")
                val source = response.body?.source() ?: throw IOException("Empty stream")
                val decoder = SSEDecoder()
                var terminal = false
                while (!call.isCanceled()) {
                    val line = source.readUtf8Line() ?: break
                    val payload = decoder.consume(line) ?: continue
                    if (payload == "[DONE]") continue
                    val value = runCatching { JSONObject(payload) }.getOrNull() ?: continue
                    if (value.optString("type") in listOf("RUN_FINISHED", "RUN_ERROR")) terminal = true
                    event(value)
                }
                if (!terminal && !call.isCanceled()) throw IOException("Interrupted stream")
            }
        } finally { if (liveCall === call) liveCall = null }
    }

    fun node(listener: WebSocketListener): WebSocket = http.newWebSocket(
        Request.Builder().url(backend.endpoint("ws/node")).build(), listener)

    fun cancelLive() { liveCall?.cancel() }
    fun close() {
        http.dispatcher.cancelAll()
        http.connectionPool.evictAll()
    }
}

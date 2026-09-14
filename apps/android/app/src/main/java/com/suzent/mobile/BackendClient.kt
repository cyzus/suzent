package com.suzent.mobile

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
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
        var recovery = StreamRecovery()
        repeat(5) { attempt ->
            currentCoroutineContext().ensureActive()
            val call = http.newCall(request("chat/live", recovery.request(id)))
            liveCall = call
            try {
                call.execute().use { response ->
                    if (!response.isSuccessful) {
                        if (response.code < 500) throw StreamRejected("HTTP ${response.code}")
                        throw IOException("HTTP ${response.code}")
                    }
                    if (response.code == 204) return@withContext
                    if (response.body?.contentType()?.subtype != "event-stream") throw IOException("Invalid stream")
                    val source = response.body?.source() ?: throw IOException("Empty stream")
                    val decoder = SSEDecoder()
                    while (!call.isCanceled()) {
                        val line = source.readUtf8Line() ?: break
                        val payload = decoder.consume(line) ?: continue
                        recovery.consume(JSONObject(payload)).forEach { event(it) }
                        if (recovery.ended) break
                    }
                    if (call.isCanceled()) throw CancellationException("Observer detached")
                    if (recovery.ended) {
                        if (recovery.superseded) recovery = StreamRecovery()
                        else if (recovery.persisted) return@withContext
                        else throw StreamRejected("Response was not saved")
                    } else throw IOException("Interrupted stream")
                }
            } catch (error: Exception) {
                if (call.isCanceled() || error is CancellationException) throw CancellationException("Observer detached", error)
                if (error is StreamRejected || attempt == 4) throw error
            } finally { if (liveCall === call) liveCall = null }
            delay(250L * (1L shl attempt))
        }
        throw IOException("Interrupted stream")
    }

    private class StreamRejected(message: String) : IOException(message)

    fun node(listener: WebSocketListener): WebSocket = http.newWebSocket(
        Request.Builder().url(backend.endpoint("ws/node")).build(), listener)

    fun cancelLive() { liveCall?.cancel() }
    fun close() {
        http.dispatcher.cancelAll()
        http.connectionPool.evictAll()
    }
}

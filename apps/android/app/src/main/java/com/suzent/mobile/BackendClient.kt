package com.suzent.mobile

import java.io.IOException
import java.util.concurrent.TimeUnit
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import okhttp3.Callback
import okhttp3.Response
import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

class BackendClient(val backend: Backend, private val token: String, probeOnly: Boolean = false, deviceTrust: DeviceTrust? = null) {
    init { require(deviceTrust == null || backend.origin.isHttps) { "Device trust requires HTTPS" } }
    private val http = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS).callTimeout(if (probeOnly) 3 else 0, TimeUnit.SECONDS)
        .apply { deviceTrust?.configure(this) }.build()
    private val reads = http.newBuilder().retryOnConnectionFailure(true).build()
    @Volatile private var liveCall: Call? = null

    private fun request(path: String, body: JSONObject? = null): Request = Request.Builder()
        .url(backend.endpoint(path)).apply { if (token.isNotEmpty()) header("Authorization", "Bearer $token") }
        .apply { if (body != null) post(body.toString().toRequestBody("application/json".toMediaType())) }
        .build()

    private suspend fun json(path: String, body: JSONObject? = null): JSONObject =
        execute(request(path, body), if (body == null) reads else http)

    private suspend fun execute(request: Request, transport: OkHttpClient): JSONObject = withContext(Dispatchers.IO) {
        suspendCancellableCoroutine { continuation ->
            val call = transport.newCall(request)
            continuation.invokeOnCancellation {
                transport.dispatcher.executorService.execute { call.cancel() }
            }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, error: IOException) {
                    continuation.resumeWithException(error)
                }
                override fun onResponse(call: Call, response: Response) {
                    runCatching {
                        response.use {
                            if (!it.isSuccessful) throw HttpFailure(it.code)
                            JSONObject(it.body?.string() ?: throw IOException("Empty response"))
                        }
                    }.fold(continuation::resume, continuation::resumeWithException)
                }
            })
        }
    }

    class HttpFailure(val code: Int) : IOException("HTTP $code")

    var supportsPairingRepair = false
        private set

    suspend fun capabilities() {
        try {
            val value = json("mobile/capabilities")
            validateMobileCapabilities(value, pairing = true)
            supportsPairingRepair = value.optInt("pairing_repair") == 1
        }
        catch (failure: HttpFailure) {
            if (failure.code == 404 || failure.code == 405) throw PairingFailure(PairingFailure.Reason.INCOMPATIBLE)
            throw failure
        } catch (_: org.json.JSONException) { throw PairingFailure(PairingFailure.Reason.INCOMPATIBLE) }
    }
    var supportsAttachments = false
        private set

    var supportsScheduledTasks = false
        private set

    suspend fun session(): ClientDevice {
        val value = json("mobile/client/session")
        validateMobileCapabilities(value)
        supportsAttachments = value.optInt("attachments") == 1
        supportsScheduledTasks = value.optInt("scheduled_tasks") == 1
        return ClientDevice.parse(value.getJSONObject("device"))
    }
    suspend fun pairingPreview(invitation: PairingInvitation): PairingPreview = PairingPreview.parse(
        json("mobile/pairing/preview", JSONObject().put("pairing_id", invitation.id)), invitation)

    suspend fun claim(invitation: PairingInvitation, name: String, confirmPermissions: Boolean = false, repairProof: String? = null, rotate: Boolean = false): JSONObject = json("mobile/pairing/claim",
        JSONObject().put("pairing_id", invitation.id).put("invitation", invitation.secret)
            .put("display_name", name).put("platform", "android").apply { if (confirmPermissions) put("confirm_permissions", true); repairProof?.let { put("repair_proof", it); put("rotate", rotate) } })
    suspend fun collect(id: String, pickupSecret: String): JSONObject = json("mobile/pairing/collect",
        JSONObject().put("pairing_id", id).put("pickup_secret", pickupSecret))

    suspend fun confirmPairing() { json("mobile/client/pairing/confirm", JSONObject()) }

    suspend fun chats(): List<Chat> {
        val array = json("mobile/client/chats").getJSONArray("chats")
        return (0 until array.length()).map { Chat.parse(array.getJSONObject(it)) }
    }
    suspend fun scheduledTasks(): List<ScheduledTask> {
        if (!supportsScheduledTasks) return emptyList()
        val array = json("mobile/client/scheduled-tasks").getJSONArray("tasks")
        return (0 until array.length()).map { ScheduledTask.parse(array.getJSONObject(it)) }
    }
    suspend fun projects(): List<Project> {
        val array = json("mobile/client/projects").getJSONArray("projects")
        return (0 until array.length()).map { val item = array.getJSONObject(it); Project(item.getString("id"), item.getString("name")) }
    }
    suspend fun composer(): Chat = Chat.parse(json("mobile/client/composer"))
    suspend fun create(title: String, projectId: String? = null): Chat = Chat.parse(json("mobile/client/chats", JSONObject().put("title", title).apply { if (projectId != null) put("project_id", projectId) }))
    suspend fun manageChat(id: String, action: String, value: String? = null) {
        json("mobile/client/manage", JSONObject().put("chat_id", id).put("action", action).apply { if (value != null) put("value", value) })
    }

    suspend fun messageAction(id: String, index: Int, action: String, text: String? = null, model: String? = null): String {
        val result = json("mobile/client/message-action", JSONObject().put("chat_id", id)
            .put("message_index", index).put("action", action).apply {
                if (text != null) put("text", text)
                if (model != null) put("model", model)
            })
        return result.optString("chat_id", id)
    }

    suspend fun chat(id: String): Chat {
        require(!id.contains('/') && id != "." && id != "..")
        return Chat.parse(json("mobile/client/chats/$id"))
    }
    suspend fun upload(id: String, attachments: List<PendingAttachment>): List<String> {
        require(!id.contains('/') && id != "." && id != "..")
        val form = MultipartBody.Builder().setType(MultipartBody.FORM).apply {
            attachments.forEach { addFormDataPart("files", it.name, it.file.asRequestBody(it.mimeType.toMediaTypeOrNull())) }
        }.build()
        val url = backend.endpoint("mobile/client/upload").newBuilder().addQueryParameter("chat_id", id).build()
        val request = Request.Builder().url(url).apply { if (token.isNotEmpty()) header("Authorization", "Bearer $token") }.post(form).build()
        val issued = execute(request, http).getJSONArray("attachments")
        return (0 until issued.length()).map { issued.getJSONObject(it).getString("id") }
    }

    suspend fun send(id: String, text: String, model: String? = null, attachments: List<String> = emptyList()) {
        val messageId = UUID.randomUUID().toString()
        val body = JSONObject().put("chat_id", id).put("message", text)
            .put("client_message_id", messageId)
            .apply { if (model != null) put("model", model) }
            .apply { if (attachments.isNotEmpty()) put("attachments", org.json.JSONArray(attachments)) }
        try {
            json("mobile/client/send", body)
        } catch (failure: Exception) {
            if (failure is HttpFailure || failure is CancellationException) throw failure
            json("mobile/client/send", body)
        }
    }
    suspend fun approvals(id: String): ApprovalState {
        require(!id.contains('/') && id != "." && id != "..")
        val value = json("mobile/client/chats/$id/approvals")
        val pending = value.getJSONArray("pending")
        return ApprovalState((0 until pending.length()).map { ApprovalRequest.parse(pending.getJSONObject(it)) }, value.optBoolean("isRunning"))
    }
    suspend fun decideApprovals(id: String, pending: List<ApprovalRequest>, choices: Map<String, String>) {
        val decisions = org.json.JSONArray()
        pending.forEach { item -> decisions.put(JSONObject().put("chat_id", id).put("request_id", item.id).put("kind", item.kind).put("action_id", choices.getValue(item.id))) }
        json("mobile/client/approvals", JSONObject().put("chat_id", id).put("decisions", decisions))
    }
    suspend fun stop(id: String) { json("mobile/client/stop", JSONObject().put("chat_id", id)) }

    suspend fun observe(id: String, event: suspend (JSONObject) -> Unit) = withContext(Dispatchers.IO) {
        var recovery = StreamRecovery()
        repeat(5) { attempt ->
            currentCoroutineContext().ensureActive()
            val call = http.newCall(request("mobile/client/live", recovery.request(id)))
            liveCall = call
            try {
                call.execute().use { response ->
                    if (!response.isSuccessful) {
                        throw HttpFailure(response.code)
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
                if (error is HttpFailure && error.code < 500) throw error
                if (error is StreamRejected || attempt == 4) throw error
            } finally { if (liveCall === call) liveCall = null }
            delay(250L * (1L shl attempt))
        }
        throw IOException("Interrupted stream")
    }

    private class StreamRejected(message: String) : IOException(message)

    fun node(listener: WebSocketListener): WebSocket = http.newWebSocket(
        Request.Builder().url(backend.endpoint("ws/node")).build(), listener)

    fun cancelNode(socket: WebSocket) {
        http.dispatcher.executorService.execute { socket.cancel() }
    }

    fun cancelLive() {
        val call = liveCall ?: return
        http.dispatcher.executorService.execute { call.cancel() }
    }
    fun close() {
        // TLS shutdown can write close_notify, including when evicting an idle socket.
        http.dispatcher.executorService.execute {
            http.dispatcher.cancelAll()
            http.connectionPool.evictAll()
        }
    }
}

data class ApprovalAction(val id: String, val behavior: String)
data class ApprovalRequest(val id: String, val kind: String, val toolName: String, val args: String, val reason: String, val actions: List<ApprovalAction>) {
    companion object {
        fun parse(value: JSONObject): ApprovalRequest {
            val actions = value.getJSONArray("actions")
            return ApprovalRequest(value.getString("id"), value.getString("kind"), value.getString("tool_name"), value.getString("args"), value.optString("reason"),
                (0 until actions.length()).map { val action = actions.getJSONObject(it); ApprovalAction(action.getString("id"), action.getString("behavior")) })
        }
    }
}
data class ApprovalState(val pending: List<ApprovalRequest>, val running: Boolean)

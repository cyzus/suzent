package com.suzent.mobile

import java.io.File
import java.time.Instant
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.delay
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONArray
import org.json.JSONObject

/** A local workspace with scripted replies. It has no HTTP client, model key, or pairing token. */
class DemoClient(fixture: String, private val storage: File? = null, language: String = Locale.getDefault().language,
                 private val streamDurationMillis: Long = 4000) : MobileClient {
    private data class Run(val id: String = UUID.randomUUID().toString(), var text: String,
        var started: Long = System.nanoTime(), var pending: Boolean, val tool: Boolean,
        var decision: Boolean? = null, var visible: Int = 0)
    private val strings = JSONObject(fixture).getJSONObject(if (language.startsWith("zh")) "zh" else "en")
    private var records = JSONArray(strings.getJSONArray("chats").toString())
    private val runs = mutableMapOf<String, Run>()
    private val uploads = mutableMapOf<String, Pair<String, JSONObject>>()
    override val supportsAttachments = true
    override val supportsScheduledTasks = true
    val prompts: List<String> get() = listOf(label("prompt"), label("tool_prompt"))

    init {
        if (storage?.exists() == true) {
            val saved = JSONObject(storage.readText())
            require(saved.getInt("version") == 1)
            records = saved.getJSONArray("chats")
            objects(records).forEach { item ->
                Chat.parse(item)
                if (item.optBoolean("isRunning")) {
                    item.getJSONArray("messages").put(message("assistant", label("interrupted"), item.optString("model")))
                    item.put("isRunning", false)
                }
            }
        }
    }

    override fun close() {}
    override fun cancelLive() {}

    fun reset() {
        runs.clear(); uploads.clear()
        records = JSONArray(strings.getJSONArray("chats").toString())
        save()
    }

    override suspend fun session() = ClientDevice("offline-demo", "Suzent Demo",
        ClientPermissions(emptyList(), true, true, true, true, approveTools = true, manageChats = true))
    override suspend fun projects(): List<Project> = objects(strings.getJSONArray("projects")).map { Project(it.getString("id"), it.getString("name")) }
    override suspend fun scheduledTasks(): List<ScheduledTask> = objects(strings.getJSONArray("tasks")).map(ScheduledTask::parse)

    override suspend fun chats(): List<Chat> {
        runs.keys.toList().forEach(::advance)
        return objects(records).map { Chat.parse(it).copy(messages = emptyList()) }
    }
    override suspend fun composer() = Chat("", "", false, emptyList(), "demo-home", label("home"), label("model"), models())
    override suspend fun create(title: String, projectId: String?): Chat {
        val project = objects(strings.getJSONArray("projects")).firstOrNull { it.getString("id") == (projectId ?: "demo-home") }
            ?: throw BackendClient.HttpFailure(400)
        val item = JSONObject().put("id", UUID.randomUUID().toString()).put("title", title).put("messages", JSONArray())
            .put("isRunning", false).put("projectId", project.getString("id")).put("projectName", project.getString("name"))
            .put("model", label("model")).put("models", JSONArray(models()))
        records = JSONArray(listOf(item) + objects(records)); save()
        return Chat.parse(item)
    }
    override suspend fun markRead(id: String) { record(id).optJSONObject("regent")?.put("unread", 0); save() }
    override suspend fun chat(id: String): Chat { advance(id); return Chat.parse(record(id)) }

    override suspend fun manageChat(id: String, action: String, value: String?) {
        advance(id)
        val item = record(id)
        if (runs.containsKey(id)) throw BackendClient.HttpFailure(409)
        when (action) {
            "pin", "unpin" -> item.put("pinned", action == "pin")
            "rename" -> { require(!value.isNullOrBlank()); item.put("title", value) }
            "move" -> {
                val project = objects(strings.getJSONArray("projects")).firstOrNull { it.getString("id") == value }
                    ?: throw BackendClient.HttpFailure(400)
                item.put("projectId", value).put("projectName", project.getString("name"))
            }
            "delete" -> records = JSONArray(objects(records).filter { it.getString("id") != id })
            else -> throw BackendClient.HttpFailure(400)
        }
        save()
    }

    override suspend fun upload(id: String, attachments: List<PendingAttachment>): List<String> {
        record(id); require(attachments.size <= MAX_ATTACHMENTS)
        return attachments.map { item ->
            val token = UUID.randomUUID().toString()
            uploads[token] = id to JSONObject().put("filename", item.name).put("mime_type", item.mimeType)
            token
        }
    }

    override suspend fun send(id: String, text: String, model: String?, attachments: List<String>) {
        advance(id)
        val item = record(id)
        if (runs.containsKey(id)) throw BackendClient.HttpFailure(409)
        require(text.isNotBlank() || attachments.isNotEmpty())
        require(attachments.all { uploads[it]?.first == id })
        if (model != null) { require(model in models()); item.put("model", model) }
        val messages = item.getJSONArray("messages")
        messages.put(message("user", text).put("files", JSONArray(attachments.map { uploads.getValue(it).second })))
        if (messages.length() == 1 && text.isNotEmpty()) item.put("title", text.take(60))
        val tool = item.optString("platform") != "focal" && matches(text, "keywords_tool")
        val reply = label(if (item.optString("platform") == "focal") "regent_reply" else if (attachments.isNotEmpty()) "attachment" else if (matches(text, "keywords_trip")) "plan" else "generic")
        runs[id] = Run(text = reply, pending = tool, tool = tool)
        item.put("isRunning", true)
        attachments.forEach(uploads::remove)
        records = JSONArray(listOf(item) + objects(records).filter { it.getString("id") != id })
        save()
    }

    override suspend fun approvals(id: String): ApprovalState {
        record(id); advance(id)
        val run = runs[id]
        return ApprovalState(if (run?.pending == true) listOf(approval(run)) else emptyList(), run != null)
    }
    override suspend fun decideApprovals(id: String, pending: List<ApprovalRequest>, choices: Map<String, String>) {
        val run = runs[id] ?: throw BackendClient.HttpFailure(409)
        val action = choices[run.id]
        require(run.pending && pending.map { it.id } == listOf(run.id) && action in listOf("allow", "reject"))
        run.pending = false; run.decision = action == "allow"
        run.text = label(if (action == "allow") "allowed" else "denied"); run.started = System.nanoTime()
    }
    override suspend fun stop(id: String) {
        record(id)
        val run = runs[id] ?: return
        run.text = run.text.take(run.visible) + label("stopped")
        finish(id)
    }

    override suspend fun messageAction(id: String, index: Int, action: String, text: String?, model: String?): String {
        val item = record(id)
        advance(id)
        require(!runs.containsKey(id))
        val messages = objects(item.getJSONArray("messages"))
        require(index in messages.indices)
        if (action == "fork") {
            val target = create(item.getString("title") + " · " + label("branch"), item.opt("projectId") as? String)
            record(target.id).put("messages", JSONArray(messages.take(index + 1)))
            save(); return target.id
        }
        require(action in listOf("edit", "retry"))
        val user = messages.indexOfLast { it.optString("role") == "user" }
        require(user >= 0)
        val original = messages[user]
        val outgoing = if (action == "edit") text.orEmpty() else original.optString("content")
        val issued = objects(original.optJSONArray("files") ?: JSONArray()).map { file ->
            val token = UUID.randomUUID().toString(); uploads[token] = id to file; token
        }
        item.put("messages", JSONArray(messages.take(user)))
        send(id, outgoing, model, issued)
        return id
    }

    override suspend fun observe(id: String, event: suspend (JSONObject) -> Unit) {
        val initial = runs[id]?.copy() ?: return
        var emitted = 0
        var decision: Boolean? = null
        event(JSONObject().put("type", "STREAM_RESET"))
        event(JSONObject().put("type", "THINKING_TEXT_MESSAGE_CONTENT").put("delta", label("reasoning")))
        event(JSONObject().put("type", "THINKING_END"))
        if (initial.tool) event(JSONObject().put("type", "CUSTOM").put("name", "tool_approval_request")
            .put("value", JSONObject().put("toolCallId", initial.id).put("toolName", "write_file").put("args", "{\"path\":\"weekend-plan.md\"}")))
        while (true) {
            currentCoroutineContext().ensureActive()
            val run = runs[id]?.copy()?.takeIf { it.id == initial.id } ?: break
            if (run.pending) { delay(80); continue }
            if (run.tool && run.decision != decision) {
                decision = run.decision
                event(JSONObject().put("type", "CUSTOM").put("name", "tool_approval_result")
                    .put("value", JSONObject().put("toolCallId", run.id).put("status", if (run.decision == true) "executed" else "rejected")
                        .put("output", label(if (run.decision == true) "allowed" else "denied"))))
            }
            val count = ((System.nanoTime() - run.started) / 1_000_000.0 / streamDurationMillis.coerceAtLeast(1) * run.text.length).toInt().coerceIn(0, run.text.length)
            if (count > emitted) {
                event(JSONObject().put("type", "TEXT_MESSAGE_CONTENT").put("messageId", run.id).put("delta", run.text.substring(emitted, count)))
                emitted = count
                runs[id]?.visible = count
            }
            if (count >= run.text.length) { finish(id); break }
            delay(60)
        }
    }

    private fun advance(id: String) {
        val run = runs[id] ?: return
        if (!run.pending && (System.nanoTime() - run.started) / 1_000_000 >= streamDurationMillis) finish(id)
    }
    private fun finish(id: String) {
        val run = runs.remove(id) ?: return
        val item = record(id)
        val parts = JSONArray().put(JSONObject().put("type", "reasoning").put("text", label("reasoning")).put("state", "completed"))
        if (run.tool) parts.put(JSONObject().put("type", "tool").put("toolCallId", run.id).put("toolName", "write_file")
            .put("args", "{\"path\":\"weekend-plan.md\"}").put("output", label(if (run.decision == null) "stopped" else if (run.decision == true) "allowed" else "denied"))
            .put("state", if (run.decision == true) "completed" else "error"))
        val source = JSONObject().put("id", "demo-source").put("type", "web").put("title", label("source_title"))
            .put("url", "https://suzent.com/docs").put("snippet", label("source_snippet"))
        parts.put(JSONObject().put("type", "text").put("text", run.text).put("citationSources", JSONArray().put(source)))
        val elapsed = ((System.nanoTime() - run.started) / 1_000_000_000.0).coerceAtLeast(0.0)
        val finished = Instant.now()
        item.getJSONArray("messages").put(message("assistant", run.text, item.optString("model")).put("parts", parts)
            .put("_streaming_run_id", run.id).put("run_started_at", finished.minusMillis((elapsed * 1000).toLong()).toString())
            .put("run_finished_at", finished.toString()).put("run_active_seconds", elapsed))
        item.put("isRunning", false); save()
    }
    private fun approval(run: Run) = ApprovalRequest(run.id, "tool", "write_file", "{\"path\":\"weekend-plan.md\"}", label("approval_reason"),
        listOf(ApprovalAction("allow", "allow"), ApprovalAction("reject", "deny")))
    private fun label(key: String): String = strings.getString(key)
    private fun matches(text: String, key: String) = strings.getJSONArray(key).let { keys ->
        (0 until keys.length()).any { text.lowercase(Locale.ROOT).contains(keys.getString(it)) }
    }
    private fun models() = listOf(label("model"), label("alternate_model"))
    private fun record(id: String): JSONObject = objects(records).firstOrNull { it.getString("id") == id } ?: throw BackendClient.HttpFailure(404)
    private fun message(role: String, text: String, model: String? = null) = JSONObject().put("role", role).put("content", text)
        .put("timestamp", Instant.now().toString()).apply { if (model != null) put("model", model) }
    private fun objects(array: JSONArray): List<JSONObject> = (0 until array.length()).map(array::getJSONObject)
    private fun save() {
        val target = storage ?: return
        target.parentFile?.mkdirs()
        val temporary = File(target.path + ".tmp")
        temporary.writeText(JSONObject().put("version", 1).put("chats", records).toString())
        check(temporary.renameTo(target)) { "Could not save demo workspace" }
    }
}

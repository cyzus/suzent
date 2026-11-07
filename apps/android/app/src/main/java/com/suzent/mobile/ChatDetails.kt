package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.roundToInt

/** The phone's version of the desktop chat side panel. */
data class ChatDetails(
    val permissionMode: PermissionMode,
    val context: ContextUsage?,
    val goal: Goal?,
    val tasks: List<PlanTask>,
    val agents: List<Agent>,
    val memory: Memory?,
    val files: Boolean,
) {
    data class PermissionMode(val mode: String, val available: List<String>, val canChange: Boolean)
    data class ContextUsage(val tokens: Int, val limit: Int) {
        val percent: Int get() = contextPercent(tokens, limit)
    }
    data class Goal(val objective: String, val status: String)
    data class PlanTask(val id: String, val title: String, val status: String, val activeForm: String?)
    data class Agent(val id: String, val description: String, val status: String, val chatId: String?) {
        val isActive: Boolean get() = status == "running" || status == "queued"
    }
    data class MemoryItem(val content: String, val category: String?)
    data class Memory(val recalled: List<MemoryItem>, val saved: List<MemoryItem>)

    companion object {
        fun parse(json: JSONObject): ChatDetails {
            val mode = json.getJSONObject("permissionMode")
            return ChatDetails(
                PermissionMode(mode.getString("mode"), mode.getJSONArray("available").strings(), mode.optBoolean("canChange")),
                json.optJSONObject("context")?.let { ContextUsage(it.getInt("tokens"), it.getInt("limit")) },
                json.optJSONObject("goal")?.let { Goal(it.getString("objective"), it.getString("status")) },
                json.getJSONArray("tasks").objects().map {
                    PlanTask(it.getString("id"), it.getString("title"), it.getString("status"), it.opt("activeForm") as? String)
                },
                json.getJSONArray("agents").objects().map {
                    Agent(it.getString("id"), it.optString("description"), it.getString("status"), it.opt("chatId") as? String)
                },
                json.optJSONObject("memory")?.let { memory ->
                    Memory(memory.getJSONArray("recalled").memoryItems(), memory.getJSONArray("saved").memoryItems())
                },
                json.optBoolean("files"),
            )
        }
    }
}

data class WorkspaceEntry(val name: String, val isDir: Boolean, val size: Long)

data class WorkspaceListing(val path: String, val entries: List<WorkspaceEntry>, val truncated: Boolean) {
    companion object {
        fun parse(json: JSONObject): WorkspaceListing = WorkspaceListing(
            json.getString("path"),
            json.getJSONArray("entries").objects().map { WorkspaceEntry(it.getString("name"), it.getBoolean("isDir"), it.optLong("size")) },
            json.optBoolean("truncated"),
        )
    }
}

fun contextPercent(tokens: Int, limit: Int): Int {
    if (limit <= 0 || tokens <= 0) return 0
    return (tokens * 100.0 / limit).roundToInt().coerceIn(1, 100)
}

/** Paths are relative to the conversation's project workspace; "" is its root. */
fun workspaceChildPath(parent: String, name: String): String = if (parent.isEmpty()) name else "$parent/$name"

fun workspaceParentPath(path: String): String = path.substringBeforeLast('/', "")

private fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }

private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }

private fun JSONArray.memoryItems(): List<ChatDetails.MemoryItem> =
    objects().map { ChatDetails.MemoryItem(it.getString("content"), it.opt("category") as? String) }

fun workspaceDisplayName(path: String): String = path.substringAfterLast('/').ifBlank { "file" }

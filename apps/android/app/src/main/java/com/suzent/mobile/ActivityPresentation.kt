package com.suzent.mobile

import org.json.JSONObject
import org.json.JSONTokener
import java.time.Instant

 data class RunTiming(val runID: String, val startedAt: String, val finishedAt: String,
    val activeSeconds: Double? = null, val unknownWait: Boolean = false) {
    companion object {
        fun parse(json: JSONObject) = RunTiming(json.optString("run_id"), json.optString("started_at"), json.optString("finished_at"),
            (json.opt("active_seconds") as? Number)?.toDouble(), json.optBoolean("unknown_wait"))
    }
}
private fun activityDate(value: String?): Instant? = value?.let { runCatching { Instant.parse(it) }.getOrNull() }
private fun collectedTimings(messages: List<ChatMessage>): List<RunTiming> {
    val runs = linkedMapOf<String, RunTiming>()
    for (message in messages) {
        val candidates = message.runTimings.ifEmpty {
            if (message.runStartedAt != null && message.runFinishedAt != null) listOf(RunTiming(message.runID ?: "${message.runStartedAt}/${message.runFinishedAt}", message.runStartedAt, message.runFinishedAt, message.runActiveSeconds)) else emptyList()
        }
        for (run in candidates) {
            val start = activityDate(run.startedAt) ?: continue
            val end = activityDate(run.finishedAt) ?: continue
            if (run.runID.isEmpty() || end < start) continue
            val previous = runs[run.runID]
            val active = run.activeSeconds ?: (if (run.runID == message.runID) message.runActiveSeconds else null) ?: previous?.activeSeconds
            runs[run.runID] = run.copy(activeSeconds = active, unknownWait = run.unknownWait || previous?.unknownWait == true ||
                (run.runID == message.runID && active == null && message.parts.any { it.toolName == "ask_question" }))
        }
    }
    return runs.values.toList()
}
fun hasRecordedTiming(messages: List<ChatMessage>): Boolean = collectedTimings(messages).isNotEmpty()
fun recordedWorkedSeconds(messages: List<ChatMessage>): Int? {
    val runs = collectedTimings(messages)
    if (runs.isEmpty() || runs.any { it.unknownWait && it.activeSeconds == null }) return null
    val seconds = runs.sumOf { run -> run.activeSeconds?.takeIf { it.isFinite() && it >= 0 }
        ?: ((activityDate(run.finishedAt)!!.toEpochMilli() - activityDate(run.startedAt)!!.toEpochMilli()) / 1000.0) }
    return seconds.takeIf { it.isFinite() && it >= 0 && it < Int.MAX_VALUE }?.toInt()
}
fun legacyWorkedSeconds(messages: List<ChatMessage>): Map<Int, Int> {
    val result = mutableMapOf<Int, Int>()
    var boundary: Int? = null
    val indices = mutableListOf<Int>()
    fun finish() {
        val start = boundary?.let { activityDate(messages[it].timestamp) } ?: return
        val end = indices.flatMap { index ->
            val message = messages[index]
            val stamp = activityDate(message.timestamp)
            val last = activityDate(message.lastActivityAt)
            if (message.runID != null && message.runFinishedAt == null) listOfNotNull(last?.takeIf { stamp != null && it > stamp })
            else listOfNotNull(stamp, last)
        }.maxOrNull() ?: return
        if (end >= start) indices.forEach { result[it] = ((end.toEpochMilli() - start.toEpochMilli()) / 1000).toInt() }
    }
    messages.forEachIndexed { index, message ->
        if (message.role in listOf("system_triggered", "trigger") || message.role == "user" && (message.content.isNotBlank() || message.files.isNotEmpty())) {
            finish(); boundary = index; indices.clear()
        } else indices.add(index)
    }
    finish()
    return result
}
fun activityDuration(seconds: Int): String = if (seconds < 60) "${seconds}s" else if (seconds % 60 == 0) "${seconds / 60}m" else "${seconds / 60}m ${seconds % 60}s"
fun activityFailed(part: MessagePart): Boolean = part.state in listOf("error", "denied", "rejected") || toolCallFailed(part)

/** Desktop's toolCallFailed: the tool itself reported failure; a denial is not one. */
fun toolCallFailed(part: MessagePart): Boolean {
    if (part.outcome.isNotEmpty()) return true
    val output = runCatching { JSONObject(part.output) }.getOrNull() ?: return false
    return output.opt("success") == false || (output.opt("error") as? String)?.isNotEmpty() == true
}

/** Desktop's AgentBadge BADGE_WEIGHTS: the resting personality, picked once per badge from [roll] in 0..1. */
fun robotPersonality(roll: Double): RobotVariant {
    val weights = listOf(RobotVariant.IDLE to 20, RobotVariant.OBSERVER to 20, RobotVariant.PEEKER to 10, RobotVariant.JUMPER to 5,
        RobotVariant.PARTY to 5, RobotVariant.LOVE to 2, RobotVariant.DJ to 2)
    var left = roll * weights.sumOf { it.second }
    for ((variant, weight) in weights) {
        left -= weight
        if (left <= 0) return variant
    }
    return RobotVariant.IDLE
}

/** The tool the badge reacts to: the first still without output, else the turn's last part when it is a tool. */
fun robotCurrentTool(parts: List<MessagePart>): String? =
    (parts.firstOrNull { it.type == "tool" && it.output.isEmpty() } ?: parts.lastOrNull()?.takeIf { it.type == "tool" })?.toolName

/** Desktop's AgentBadge variant: a fresh failure startles it, approval makes it skeptical, each tool has its face. */
fun robotBadgeVariant(base: RobotVariant, startled: Boolean, pending: Boolean, streaming: Boolean, tool: String?): RobotVariant = when {
    startled -> RobotVariant.SHAKER
    pending -> RobotVariant.SKEPTIC
    tool != null -> when (canonicalActivityTool(tool)) {
        "read_file", "webpage_fetch" -> RobotVariant.EATER
        "glob_search", "grep_search" -> RobotVariant.SCANNER
        "web_search" -> RobotVariant.PEEKER
        "run_command", "start_command", "write_file", "edit_file" -> RobotVariant.WORKOUT
        "agent" -> RobotVariant.PORTAL
        "skill_execute" -> RobotVariant.DJ
        else -> RobotVariant.OBSERVER
    }
    streaming -> RobotVariant.OBSERVER
    else -> base
}
fun activityDetail(raw: String, output: Boolean = false): String {
    val value = runCatching { JSONTokener(raw).nextValue() }.getOrNull() ?: return raw
    if (output && value is JSONObject) {
        if (value.opt("success") == false && value.opt("error") is String) return value.getString("error")
        (value.opt("message") as? String)?.takeIf { it.isNotEmpty() }?.let { return it }
    }
    return when (value) {
        is JSONObject -> value.toString(2)
        is org.json.JSONArray -> value.toString(2)
        is String -> value
        else -> raw
    }
}
fun activityFinalStart(parts: List<MessagePart>): Int {
    var start = parts.size
    while (start > 0 && parts[start - 1].type == "text") start--
    return start
}

fun activityRows(parts: List<MessagePart>): List<MessagePart> {
    val rows = mutableListOf<MessagePart>()
    for (part in normalizeParts(parts)) {
        if (part.type == "reasoning" && rows.lastOrNull()?.type == "reasoning") rows[rows.lastIndex] = part.copy(text = rows.last().text + "\n\n" + part.text)
        else rows.add(part)
    }
    return rows
}

private val exactToolIcons = mapOf(
    "read_file" to "document-text", "write_file" to "document-plus", "edit_file" to "pencil-square", "glob_search" to "folder-open",
    "grep_search" to "magnifying-glass", "run_command" to "command-line", "start_command" to "play", "check_command" to "signal",
    "stop_command" to "stop", "web_search" to "globe-alt", "webpage_fetch" to "arrow-down-on-square", "browser_action" to "cursor-arrow-rays",
    "memory_search" to "cpu-chip", "memory_update" to "cpu-chip", "session_search" to "chat-bubble-left-right", "manage_goal" to "flag",
    "create_tasks" to "clipboard-document-list", "update_task" to "clipboard-document-check", "list_tasks" to "clipboard-document-list", "schedule_cron" to "calendar-days",
    "skill_execute" to "bolt", "search_tools" to "magnifying-glass", "render_ui" to "squares-2x2", "ask_question" to "question-mark-circle",
    "generate_image" to "photo", "edit_image" to "paint-brush", "analyze_image" to "eye", "analyze_visual" to "eye",
    "generate_video" to "film", "check_video_status" to "film", "speak" to "speaker-wave", "social_message" to "paper-airplane",
    "agent" to "user-group", "agent_list" to "user-group", "agent_read" to "user-group", "agent_send" to "user-group",
    "agent_dispatch" to "user-group", "agent_stop" to "user-group",
)

/** Desktop's pickToolIcon (toolGroupIcon.tsx): the Heroicon each tool row shows. [approval] is "pending" or "denied". */
fun activityToolIcon(toolName: String, approval: String? = null): String {
    if (approval == "pending") return "clock"
    if (approval == "denied") return "no-symbol"
    val name = canonicalActivityTool(toolName)
    exactToolIcons[name]?.let { return it }
    return when {
        listOf("agent", "subagent").any { it in name } -> "user-group"
        "memory" in name -> "cpu-chip"
        listOf("session", "chat").any { it in name } -> "chat-bubble-left-right"
        "browser" in name -> "cursor-arrow-rays"
        listOf("fetch", "scrape").any { it in name } -> "arrow-down-on-square"
        "web" in name -> "globe-alt"
        listOf("glob", "dir").any { it in name } -> "folder-open"
        listOf("search", "grep", "find").any { it in name } -> "magnifying-glass"
        listOf("edit", "patch", "replace").any { it in name } -> "pencil-square"
        listOf("write", "create_file").any { it in name } -> "document-plus"
        "read" in name -> "document-text"
        listOf("file", "folder").any { it in name } -> "folder"
        listOf("bash", "shell", "python", "command", "cmd", "exec").any { it in name } -> "command-line"
        listOf("database", "sql", "db").any { it in name } -> "circle-stack"
        "goal" in name -> "flag"
        listOf("task", "plan", "todo").any { it in name } -> "clipboard-document-list"
        listOf("schedule", "cron").any { it in name } -> "calendar-days"
        "skill" in name -> "bolt"
        listOf("image", "photo").any { it in name } -> "photo"
        "video" in name -> "film"
        listOf("speak", "audio", "voice").any { it in name } -> "speaker-wave"
        else -> "wrench-screwdriver"
    }
}

/** Desktop's pickToolAnimationKind: how a running tool's icon moves; "none" once it has output. */
fun activityToolAnimation(toolName: String, approval: String? = null, running: Boolean = false, hasOutput: Boolean = false): String {
    if (approval == "denied") return "none"
    if (approval == "pending") return "pending"
    if (!running || hasOutput) return "none"
    val name = canonicalActivityTool(toolName)
    return when (name) {
        "run_command", "start_command", "stop_command" -> "terminal"
        "check_command", "speak", "social_message" -> "signal"
        "read_file", "webpage_fetch", "analyze_image", "analyze_visual", "agent_read" -> "scan"
        "write_file", "edit_file", "create_tasks", "update_task", "manage_goal", "edit_image", "generate_image", "generate_video", "render_ui" -> "typewriter"
        "glob_search", "grep_search", "web_search", "search_tools", "list_tasks", "agent_list" -> "radar"
        "memory_search", "session_search", "agent", "agent_send", "agent_dispatch" -> "memory"
        "skill_execute", "schedule_cron" -> "snap"
        "browser_action" -> "cursor"
        else -> when {
            listOf("bash", "shell", "command", "cmd").any { it in name } -> "terminal"
            listOf("read", "fetch").any { it in name } -> "scan"
            listOf("write", "edit").any { it in name } -> "typewriter"
            listOf("search", "grep", "glob").any { it in name } -> "radar"
            "memory" in name -> "memory"
            "browser" in name -> "cursor"
            else -> "terminal"
        }
    }
}

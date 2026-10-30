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
fun activityFailed(part: MessagePart): Boolean {
    if (part.state in listOf("error", "denied", "rejected") || part.outcome.isNotEmpty()) return true
    val output = runCatching { JSONObject(part.output) }.getOrNull() ?: return false
    return output.opt("success") == false || (output.opt("error") as? String)?.isNotEmpty() == true
}
fun activityKind(part: MessagePart): String {
    if (part.type == "reasoning") return "reasoning"
    val name = canonicalActivityTool(part.toolName)
    return when {
        name.contains("command") || name.contains("shell") -> "terminal"
        name.contains("search") || name.contains("fetch") -> "search"
        name.contains("write") || name.contains("edit") -> "edit"
        name.contains("read") -> "read"
        name.contains("agent") || name.contains("dispatch") -> "agent"
        else -> "tool"
    }
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

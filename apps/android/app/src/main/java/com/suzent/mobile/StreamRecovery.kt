package com.suzent.mobile

import java.io.IOException
import org.json.JSONObject

class StreamRecovery {
    var runId: String? = null
        private set
    var sequence = 0L
        private set
    var ended = false
        private set
    var persisted = false
        private set
    var superseded = false
        private set

    fun request(chatId: String): JSONObject = JSONObject().put("chat_id", chatId)
        .put("wait_ms", 1000).put("protocol", 1).apply {
            runId?.let { put("run_id", it); put("after_seq", sequence) }
        }

    fun consume(frame: JSONObject): List<JSONObject> {
        val run = frame.optString("run_id")
        val seq = frame.optLong("seq", -1)
        if (run.isEmpty() || seq < 0) throw IOException("Invalid recovery frame")
        return when (frame.optString("type")) {
            "STREAM_SNAPSHOT" -> {
                val events = frame.optJSONArray("events") ?: throw IOException("Invalid snapshot")
                val decoded = (0 until events.length()).map { events.getJSONObject(it) }
                runId = run; sequence = seq
                listOf(JSONObject().put("type", "STREAM_RESET")) + decoded
            }
            "STREAM_EVENT" -> {
                if (run != runId) throw IOException("Unexpected stream run")
                if (seq <= sequence) emptyList() else {
                    if (seq != sequence + 1) throw IOException("Missing stream event")
                    val event = frame.getJSONObject("event")
                    sequence = seq
                    listOf(event)
                }
            }
            "STREAM_END" -> {
                if (run != runId || seq != sequence) throw IOException("Invalid stream completion")
                ended = true
                persisted = frame.optBoolean("persisted")
                superseded = frame.optBoolean("superseded")
                emptyList()
            }
            else -> throw IOException("Unsupported recovery protocol")
        }
    }
}

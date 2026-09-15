package com.suzent.mobile

import org.json.JSONObject

internal class LiveTextBuffer {
    private val text = StringBuilder()
    private var dirty = false

    fun consume(event: JSONObject) {
        when (event.optString("type")) {
            "STREAM_RESET" -> { text.clear(); dirty = true }
            "TEXT_MESSAGE_CONTENT" -> { text.append(event.optString("delta")); dirty = true }
        }
    }

    fun drain(): String? {
        if (!dirty) return null
        dirty = false
        return text.toString()
    }
}

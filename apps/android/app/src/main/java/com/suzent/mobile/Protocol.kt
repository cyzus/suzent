package com.suzent.mobile

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import org.json.JSONArray
import org.json.JSONObject

data class Backend(val origin: HttpUrl) {
    companion object {
        fun parse(raw: String, allowHttp: Boolean = false): Backend {
            val url = requireNotNull(raw.trim().toHttpUrlOrNull())
            require(url.isHttps || allowHttp)
            require(url.username.isEmpty() && url.password.isEmpty())
            require(url.encodedPath == "/" && url.query == null && url.fragment == null)
            return Backend(url)
        }
    }
    fun endpoint(path: String): HttpUrl = origin.newBuilder().addPathSegments(path).build()
}

data class ChatMessage(val role: String, val content: String, val parts: List<MessagePart> = emptyList(),
    val name: String = "", val toolCallId: String = "")
data class Chat(val id: String, val title: String, val running: Boolean, val messages: List<ChatMessage>) {
    companion object {
        fun parse(json: JSONObject): Chat {
            val messages = json.optJSONArray("messages") ?: JSONArray()
            return Chat(json.getString("id"), json.optString("title"), json.optBoolean("isRunning"),
                (0 until messages.length()).mapNotNull { index ->
                    val item = messages.optJSONObject(index) ?: return@mapNotNull null
                    val parts = item.optJSONArray("parts") ?: JSONArray()
                    ChatMessage(item.optString("role", "assistant"), item.opt("content") as? String ?: "",
                        (0 until parts.length()).mapNotNull { partIndex ->
                            val part = parts.optJSONObject(partIndex) ?: return@mapNotNull null
                            MessagePart(part.optString("type"), part.optString("text"), part.optString("toolName"),
                                part.optString("args"), part.optString("output"), part.optString("toolCallId"), part.optString("state"))
                        }, item.optString("name"), item.optString("tool_call_id"))
                })
        }
    }
}

class SSEDecoder {
    private val lines = mutableListOf<String>()
    fun consume(raw: String): String? {
        val line = raw.removeSuffix("\r")
        if (line.isEmpty()) {
            val payload = if (lines.isEmpty()) null else lines.joinToString("\n")
            lines.clear()
            return payload
        }
        if (line.startsWith("data:")) lines.add(line.drop(5).removePrefix(" "))
        return null
    }
}

object NodeProtocol {
    fun connect(name: String, platform: String, token: String): JSONObject = JSONObject()
        .put("type", "connect").put("display_name", name).put("platform", platform)
        .put("device_token", token).put("capabilities", JSONArray().put(JSONObject()
            .put("name", "device.status").put("description", "Foreground device availability")
            .put("params_schema", JSONObject())))

    fun reply(message: JSONObject, platform: String): JSONObject? = when (message.optString("type")) {
        "ping" -> JSONObject().put("type", "pong")
        "invoke" -> if (!message.has("request_id")) null else {
            val result = JSONObject().put("type", "result").put("request_id", message.getString("request_id"))
            if (message.optString("command") == "device.status") {
                result.put("success", true).put("result", JSONObject().put("platform", platform).put("foreground", true))
            } else result.put("success", false).put("error", "Unsupported capability")
        }
        else -> null
    }
}

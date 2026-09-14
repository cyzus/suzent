package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class ChatPresentationTest {
    @Test fun nativePresentationContract() {
        val cases = JSONArray(requireNotNull(javaClass.classLoader?.getResourceAsStream("presentation-fixtures.json"))
            .bufferedReader().use { it.readText() })
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val chat = Chat.parse(JSONObject().put("id", "fixture").put("messages", case.getJSONArray("messages")))
            val rows = presentMessages(chat.messages)
            val texts = case.getJSONArray("texts")
            val activities = case.getJSONArray("activities")
            assertEquals(case.getString("name"), texts.length(), rows.size)
            rows.forEachIndexed { row, message ->
                assertEquals(case.getString("name"), texts.getString(row), message.text)
                assertEquals(case.getString("name"), activities.getInt(row), message.activities.size)
            }
        }
    }
}

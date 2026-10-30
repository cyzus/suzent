package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ActivityPresentationTest {
    @Test fun sharedTimingContract() {
        val fixtures = JSONArray(javaClass.getResource("/activity-timing-fixtures.json")!!.readText())
        for (i in 0 until fixtures.length()) {
            val fixture = fixtures.getJSONObject(i)
            val chat = Chat.parse(JSONObject().put("id", "test").put("messages", fixture.getJSONArray("messages")))
            assertEquals(fixture.getString("name"), fixture.opt("seconds") as? Int, presentMessages(chat.messages).last().workedSeconds)
        }
    }
    @Test fun disclosurePreservesAnswerAndFailedOutput() {
        val parts = listOf(MessagePart("text", text = "Checking"), MessagePart("tool", toolName = "read_file", output = """{"success":false,"error":"File missing"}""", state = "completed"), MessagePart("text", text = "Final answer"))
        assertEquals(2, activityFinalStart(parts))
        assertTrue(activityFailed(parts[1]))
        assertEquals("File missing", activityDetail(parts[1].output, true))
        assertEquals("read", activityKind(parts[1]))
        assertEquals("1m 5s", activityDuration(65))
        assertEquals("0s", activityDuration(0))
        assertEquals("Saved", activityDetail("""{"message":"Saved","success":true}""", true))
        assertEquals(0, activityFinalStart(listOf(MessagePart("text", text = "Answer"))))
    }
}

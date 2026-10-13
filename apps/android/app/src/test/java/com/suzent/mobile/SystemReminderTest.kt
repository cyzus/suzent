package com.suzent.mobile

import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class SystemReminderTest {
    @Test fun remindersFollowDesktopPresentation() {
        val fixtures = JSONArray(File("../../../packages/mobile-contract/system-reminder-fixtures.json").readText())
        for (index in 0 until fixtures.length()) {
            val fixture = fixtures.getJSONObject(index)
            val reminder = systemReminder(fixture.getString("content"))
            assertEquals(fixture.getString("name"), fixture.opt("title").takeUnless { it == JSONObject.NULL }, reminder?.title)
            assertEquals(fixture.opt("body").takeUnless { it == JSONObject.NULL }, reminder?.body)
            assertEquals(fixture.opt("collapsed").takeUnless { it == JSONObject.NULL }, reminder?.initiallyCollapsed)
        }
    }

    @Test fun hiddenRemindersPreserveTurnBoundaries() {
        val chat = Chat.parse(JSONObject("""{"id":"test","messages":[
            {"role":"assistant","parts":[{"type":"reasoning","text":"Thinking"}]},
            {"role":"system_triggered","content":"<!-- suzent-agent-inbox:hidden -->"},
            {"role":"assistant","content":"New turn"}
        ]}"""))
        val rows = presentMessages(chat.messages)
        assertEquals(listOf(0, 2), rows.map { it.messageIndex })
        assertEquals("New turn", rows[1].text)
    }

    @Test fun metadataIsRemovedOnlyFromReminderRows() {
        val chat = Chat.parse(JSONObject("""{"id":"test","messages":[
            {"role":"user","content":"<!-- suzent-agent-inbox:literal -->"},
            {"role":"system_triggered","parts":[{"type":"text","text":"<!-- suzent-agent-inbox:private -->\n**Agent done**\nResult"}]}
        ]}"""))
        val rows = presentMessages(chat.messages)
        assertEquals(listOf("user", "system_triggered"), rows.map { it.role })
        assertEquals("<!-- suzent-agent-inbox:literal -->", rows[0].text)
        assertEquals("**Agent done**\nResult", rows[1].text)
    }
}

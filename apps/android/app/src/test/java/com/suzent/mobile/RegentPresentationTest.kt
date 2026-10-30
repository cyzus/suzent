package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RegentPresentationTest {
    @Test fun sharedRegentDeliveryContract() {
        val fixtures = JSONArray(javaClass.getResource("/regent-fixtures.json")!!.readText())
        for (i in 0 until fixtures.length()) {
            val fixture = fixtures.getJSONObject(i)
            val chat = Chat.parse(JSONObject().put("id", "focal-suzent").put("messages", JSONArray().put(JSONObject()
                .put("role", "assistant").put("parts", fixture.getJSONArray("parts")))))
            val parts = regentDisplayParts(chat.messages.single().parts, fixture.getBoolean("live"))
            val texts = fixture.getJSONArray("texts")
            assertEquals(fixture.getString("name"), (0 until texts.length()).map { texts.getString(it) }, parts.filter { it.type == "text" }.map { it.text })
            assertEquals(fixture.getString("name"), fixture.getInt("activities"), parts.count { it.type != "text" })
            assertEquals(fixture.opt("reaction") as? String, regentReaction(chat.messages.single().parts))
        }
    }

    @Test fun reactionsStayWithTheirUserTurnAndResetWithLiveParts() {
        val reaction = MessagePart("tool", toolName = "react_to_message", output = """{"success":true,"metadata":{"regent_reaction":"✅"}}""", toolCallId = "reaction", state = "completed")
        val user = DisplayMessage("user", listOf(MessagePart("text", text = "HEARTBEAT_OK")))
        val rows = regentMessages(listOf(user, DisplayMessage("assistant", listOf(reaction))))
        assertEquals(1, rows.size)
        assertEquals("HEARTBEAT_OK", rows.single().text)
        assertEquals("✅", rows.single().reaction)
        val background = DisplayMessage("system_triggered", listOf(MessagePart("text", text = "Check-in")))
        assertNull(regentMessages(listOf(user, background), listOf(reaction)).first().reaction)
        assertEquals("✅", regentMessages(listOf(user), listOf(reaction)).first().reaction)
        assertNull(regentMessages(listOf(user)).first().reaction)
    }

    @Test fun metadataIsOptionalForOlderBackends() {
        val old = Chat.parse(JSONObject("""{"id":"old","title":"Old"}"""))
        assertFalse(old.isRegent)
        assertNull(old.regent)
        val regent = Chat.parse(JSONObject("""{"id":"focal-suzent","platform":"focal","regent":{"waiting":2,"unread":1}}"""))
        assertTrue(regent.isRegent)
        assertEquals(2, regent.regent?.waiting)
    }
}

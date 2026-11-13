package com.suzent.mobile

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TriggerRowsTest {
    private fun rows(messages: String) = presentMessages(Chat.parse(JSONObject("""{"id":"test","messages":[$messages]}""")).messages)

    @Test fun readsEachKindOfTrigger() {
        val agent = parseTrigger("[Agent message from Release check 每日 (ea0f)]\n<!-- suzent-agent-inbox:x -->\n## Report\nAll good")
        assertEquals(ParsedTrigger(TriggerKind.Agent, "Release check 每日", "## Report\nAll good", "agent:ea0f", "ea0f"), agent)
        assertEquals(ParsedTrigger(TriggerKind.Scheduled, "Stand-up", "Remind", "scheduled:Stand-up"), parseTrigger("**Scheduled Task: Stand-up**\n\nRemind"))
        assertEquals(ParsedTrigger(TriggerKind.Goal, "", "Keep going", "goal"), parseTrigger("[Goal mode] Keep going"))
        assertEquals(ParsedTrigger(TriggerKind.Other, "Sub-agent finished", "Result", "other:Sub-agent finished"), parseTrigger("**Sub-agent finished**\nResult"))
    }

    @Test fun previewPrefersProseOverHeadings() {
        assertEquals("v0.14.2 shipped notes", triggerPreview("\n---\n- **v0.14.2** shipped [notes](https://x)\nmore"))
        assertEquals("All green", triggerPreview("## Daily report\nAll green"))
        assertEquals("Daily report", triggerPreview("## Daily report"))
    }

    @Test fun repeatsWithNoReplyMergeIntoOneRow() {
        val cron = """{"role":"system_triggered","content":"**Scheduled Task: Check**\n\nDo it"}"""
        val quiet = """{"role":"assistant","parts":[{"type":"reasoning","text":"thinking"},{"type":"text","text":"HEARTBEAT_OK"}]}"""
        val result = rows(listOf(cron, quiet, cron, quiet, cron, quiet).joinToString(","))
        assertEquals(listOf("system_triggered"), result.map { it.role })
        assertEquals(3, result.single().triggers.size)
        assertEquals(4, result.single().messageIndex)
    }

    @Test fun anAnsweredRunMovesOntoItsReply() {
        val result = rows("""
            {"role":"system_triggered","content":"[Agent message from A (a)]\none"},
            {"role":"assistant","content":"HEARTBEAT_OK"},
            {"role":"system_triggered","content":"[Agent message from A (a)]\ntwo"},
            {"role":"assistant","content":"Done"}""")
        assertEquals(listOf("assistant"), result.map { it.role })
        assertEquals(listOf("one", "two"), result.single().triggers.map { it.trigger.body })
        assertEquals("Done", result.single().text)
    }

    @Test fun differentSendersStayApart() {
        val result = rows("""
            {"role":"system_triggered","content":"[Agent message from A (a)]\none"},
            {"role":"assistant","content":"HEARTBEAT_OK"},
            {"role":"system_triggered","content":"[Agent message from B (b)]\ntwo"},
            {"role":"assistant","content":"HEARTBEAT_OK"}""")
        assertEquals(listOf("A", "B"), result.map { it.triggers.single().trigger.source })
    }

    @Test fun aTriggerAnsweredOnlyByAQuietReplyKeepsItsRow() {
        val result = rows("""
            {"role":"user","content":"hi"},
            {"role":"system_triggered","content":"**Scheduled Task: Check**"},
            {"role":"assistant","content":"HEARTBEAT_OK"},
            {"role":"assistant","content":"Later"}""")
        assertEquals(listOf("user", "system_triggered", "assistant"), result.map { it.role })
        assertEquals(emptyList<TriggerEntry>(), result[2].triggers)
    }

    @Test fun aRegentReplyToATriggerNeverReactsToTheUser() {
        val reaction = MessagePart("tool", toolName = "react_to_message", output = """{"success":true,"metadata":{"regent_reaction":"✅"}}""", toolCallId = "reaction", state = "completed")
        val user = DisplayMessage("user", listOf(MessagePart("text", text = "hi")))
        val reply = DisplayMessage("assistant", listOf(reaction, MessagePart("text", text = "Checked")),
            triggers = listOf(TriggerEntry(parseTrigger("**Scheduled Task: Check**"), null)))
        assertNull(regentMessages(listOf(user, reply)).first().reaction)
    }
}

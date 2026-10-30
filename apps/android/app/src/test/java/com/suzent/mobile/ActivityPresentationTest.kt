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
    @Test fun toolIconsAndMotionFollowDesktop() {
        assertEquals("document-text", activityToolIcon("Read"))
        assertEquals("cpu-chip", activityToolIcon("mcp__server__memory_search"))
        assertEquals("circle-stack", activityToolIcon("query_database"))
        assertEquals("wrench-screwdriver", activityToolIcon("mystery"))
        assertEquals("clock", activityToolIcon("run_command", "pending"))
        assertEquals("no-symbol", activityToolIcon("run_command", "denied"))
        assertEquals("terminal", activityToolAnimation("Bash", running = true))
        assertEquals("radar", activityToolAnimation("grep_search", running = true))
        assertEquals("cursor", activityToolAnimation("browser_action", running = true))
        assertEquals("none", activityToolAnimation("grep_search", running = true, hasOutput = true))
        assertEquals("pending", activityToolAnimation("grep_search", "pending"))
        assertEquals(.5, Curve.linear.at(.5), 1e-6)
        assertEquals("scan", activityRunningSurface("grep_search"))
        assertEquals("dots", activityRunningSurface("Read"))
        assertEquals("mono", activityRunningSurface("Bash"))
        assertEquals("scan", activityRunningSurface("vision_describe"))
        assertEquals("mono", activityRunningSurface("mystery"))
        assertEquals(.25, runningSurfaceFrame("mono", 1.35 * .25).wave, 1e-9)
        assertEquals(6.0, runningSurfaceFrame("dots", .7).gridShift, 1e-9)
        assertEquals(.5, Curve.easeInOut.at(.5), 1e-3)
        assertEquals(12.0, toolIconPose("pending", 1.4 * .3).rotation, 1e-6)
        assertEquals(-7.0, toolIconPose("scan", 0.0).sweepY, 1e-9)
        assertEquals(.35, toolIconPose("terminal", .5).alpha, 1e-6)
        assertEquals(.25, cycle(2.25, 1.0), 1e-9)
        assertEquals(.75, cycle(1.25, 1.0, alternate = true), 1e-9)
    }
    @Test fun disclosurePreservesAnswerAndFailedOutput() {
        val parts = listOf(MessagePart("text", text = "Checking"), MessagePart("tool", toolName = "read_file", output = """{"success":false,"error":"File missing"}""", state = "completed"), MessagePart("text", text = "Final answer"))
        assertEquals(2, activityFinalStart(parts))
        assertTrue(activityFailed(parts[1]))
        assertEquals("File missing", activityDetail(parts[1].output, true))
        assertEquals("1m 5s", activityDuration(65))
        assertEquals("0s", activityDuration(0))
        assertEquals("Saved", activityDetail("""{"message":"Saved","success":true}""", true))
        assertEquals(0, activityFinalStart(listOf(MessagePart("text", text = "Answer"))))
    }
}

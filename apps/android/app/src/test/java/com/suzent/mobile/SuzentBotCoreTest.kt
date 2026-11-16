package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SuzentBotCoreTest {
    private val script = javaClass.getResource("/suzent-bot-core.js")!!.readText()
    private val host = SuzentBotHost(script)

    @After fun close() { host.close() }

    @Test fun resolveStageMatchesDesktop() {
        assertEquals("approval", host.resolveStage(true, true, false, "run_command", true))
        assertEquals("error", host.resolveStage(false, true, false, "write_file", true))
        assertEquals("thinking", host.resolveStage(false, false, true, null, true))
        assertEquals("reading", host.resolveStage(false, false, false, "read_file", true))
        assertEquals("searching", host.resolveStage(false, false, false, "WebSearch", true))
        assertEquals("bash", host.resolveStage(false, false, false, "run_command", true))
        assertEquals("idle", host.resolveStage(false, false, false, null, false))
    }

    @Test fun pathAndTransformPrimitives() {
        val path = parseSvgPath("M0 0L10 0L10 10Z")
        assertEquals(4, path.size)
        assertTrue(path[0] is SvgCmd.Move)
        assertTrue(path[3] is SvgCmd.Close)
        val moved = parseSvgTransform("translate(4 5) scale(2)")
        assertEquals(8.0, moved.x(2.0, 0.0), 1e-9)
        assertEquals(5.0, moved.y(2.0, 0.0), 1e-9)
    }

    @Test fun framesMatchTheSharedFixture() {
        val fixture = JSONObject(javaClass.getResource("/suzent-bot-frames.json")!!.readText())
        val times = fixture.getJSONArray("times")
        val scenarios = fixture.getJSONArray("scenarios")
        for (index in 0 until scenarios.length()) {
            val scenario = scenarios.getJSONObject(index)
            val stage = scenario.getString("stage")
            val morph = scenario.opt("morph")
            val id = host.create(1, JSONObject()
                .put("stage", stage)
                .put("size", 36)
                .put("isPending", stage == "approval")
                .put("holdWhenIdle", false)
                .put("particlesEnabled", true)
                .put("autoMorphCycle", false)
                .put("reducedMotion", false)
                .put("dark", false)
                .put("svgId", "suzent-bot-test")
                .put("clipId", "suzent-bot-clip-test")
                .toString())
            val frames = scenario.getJSONArray("frames")
            for (frameIndex in 0 until times.length()) {
                val at = times.getDouble(frameIndex)
                val input = JSONObject()
                    .put("stage", stage)
                    .put("time", at)
                    .put("size", 36)
                    .put("isPending", stage == "approval")
                    .put("reducedMotion", false)
                    .put("dark", false)
                    .put("particlesEnabled", true)
                    .put("autoMorphCycle", false)
                    .put("holdWhenIdle", false)
                    .put("svgId", "suzent-bot-test")
                    .put("clipId", "suzent-bot-clip-test")
                if (at == 1000.0 && morph is String) {
                    input.put("morph", morph).put("morphDuration", if (morph == "pencil") 3200 else 1750)
                }
                val actual = JSONObject(host.step(id, input.toString()))
                assertJsonEqual("$stage@$at", frames.getJSONObject(frameIndex).getJSONObject("scene"), actual)
            }
            host.destroy(id)
        }
    }
}

private fun assertJsonEqual(label: String, expected: Any?, actual: Any?) {
    when {
        expected is JSONObject && actual is JSONObject -> {
            val keys = expected.keys().asSequence().toSet() + actual.keys().asSequence().toSet()
            for (key in keys) assertJsonEqual("$label.$key", expected.opt(key), actual.opt(key))
        }
        expected is JSONArray && actual is JSONArray -> {
            assertEquals("$label length", expected.length(), actual.length())
            for (index in 0 until expected.length()) assertJsonEqual("$label[$index]", expected.get(index), actual.get(index))
        }
        expected is Number && actual is Number -> assertEquals(label, expected.toDouble(), actual.toDouble(), 0.0)
        else -> assertEquals(label, expected?.toString(), actual?.toString())
    }
}

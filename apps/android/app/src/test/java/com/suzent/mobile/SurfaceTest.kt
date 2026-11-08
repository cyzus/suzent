package com.suzent.mobile

import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SurfaceTest {
    private val fixtures = JSONObject(requireNotNull(javaClass.classLoader?.getResourceAsStream("surface-fixtures.json"))
        .bufferedReader().use { it.readText() })

    private fun strings(array: JSONArray) = (0 until array.length()).map { array.getString(it) }

    @Test fun surfaceTreeDecodesEveryComponent() {
        val surface = A2UISurface.parse(fixtures.getJSONObject("surface"))
        assertEquals(strings(fixtures.getJSONArray("component_types")), surface.component.flattened.map { it.typeName })
        assertFalse(surface.deferred)
        val card = surface.component as A2UIComponent.Card
        val table = card.children[4] as A2UIComponent.Table
        val cells = fixtures.getJSONObject("cell_text")
        assertEquals(cells.getString("19:00"), jsonDisplay(table.rows[0]["time"]))
        assertEquals(cells.getString("2"), jsonDisplay(table.rows[0]["seats"]))
        assertEquals(cells.getString("null"), jsonDisplay(table.rows[1]["seats"]))
        val form = card.children[6] as A2UIComponent.Form
        assertEquals(listOf("text", "number", "select", "multiselect", "checkbox", "textarea"), form.fields.map { it.kind })
        assertTrue(form.fields[2].allowFreeText)
        assertEquals("Save", form.submitLabel)
    }

    @Test fun surfaceActionsMatchTheDesktopMessages() {
        val actions = fixtures.getJSONArray("actions")
        for (index in 0 until actions.length()) {
            val case = actions.getJSONObject(index)
            assertEquals(case.getString("name"), case.getString("message"),
                canvasActionMessage(case.getString("action"), jsonMap(case.getJSONObject("context")), case.getString("surface_id")))
        }
        val questions = fixtures.getJSONArray("question_answers")
        for (index in 0 until questions.length()) {
            val case = questions.getJSONObject(index)
            assertEquals(case.getString("text"), questionAnswerText(jsonMap(case.getJSONObject("context"))))
        }
        val deferred = fixtures.getJSONArray("deferred_answers")
        for (index in 0 until deferred.length()) {
            val case = deferred.getJSONObject(index)
            assertEquals(jsonMap(case.getJSONObject("answer")), deferredAnswer(jsonMap(case.getJSONObject("context"))))
        }
        val messages = fixtures.getJSONArray("canvas_messages")
        for (index in 0 until messages.length()) {
            val case = messages.getJSONObject(index)
            assertEquals(case.opt("label") as? String, canvasActionLabel(case.getString("text")))
        }
    }

    @Test fun liveSurfacesUpsertAndAnsweredQuestionsLeave() {
        val live = fixtures.getJSONObject("live")
        val buffer = LiveActivityBuffer()
        val events = live.getJSONArray("events")
        for (index in 0 until events.length()) buffer.consume(events.getJSONObject(index))
        val parts = requireNotNull(buffer.drain())
        assertEquals(strings(live.getJSONArray("part_types")), parts.map { it.type })
        assertEquals(strings(live.getJSONArray("surface_ids")), parts.mapNotNull { it.surface?.id })
        assertEquals(live.getString("latest_text"), (parts.last().surface?.component as A2UIComponent.Text).content)
    }

    @Test fun surfacesFormTheirOwnChunks() {
        val chunks = fixtures.getJSONObject("chunks")
        val parts = strings(chunks.getJSONArray("parts")).map {
            MessagePart(it, text = if (it in setOf("text", "reasoning")) "Answer" else "", toolCallId = if (it == "tool") "t" else "")
        }
        val kinds = chunks.getJSONArray("kinds")
        assertEquals((0 until kinds.length()).map { strings(kinds.getJSONArray(it)) }, activityChunks(parts).map { chunk -> chunk.map { it.type } })
    }

    @Test fun malformedSurfacesDegradeWithoutFailingTheMessage() {
        val surface = A2UISurface.parse(JSONObject("""{"id":"s","component":{"type":"stack","children":[{"type":"badge"},{"type":"divider"}]}}"""))
        assertEquals(listOf("stack", "unknown", "divider"), surface.component.flattened.map { it.typeName })
        assertEquals(A2UIComponent.Unknown(""), A2UISurface.parse(JSONObject("""{"id":"x"}""")).component)
    }

    @Test fun htmlDocumentFitsAPhoneAndSizesToContent() {
        val fragment = surfaceHtmlDocument("<p>Hi</p>")
        assertTrue(fragment.startsWith("<!DOCTYPE html>\n<meta name=\"viewport\""))
        assertTrue("body.scrollHeight" in fragment && "SuzentSurface.post" in fragment && "a2ui:action" in fragment)
        val own = surfaceHtmlDocument("<!doctype html><meta name='viewport' content='width=400'><p>Hi</p>")
        assertTrue(own.startsWith("<!doctype html><meta name='viewport'"))
    }

    @Test fun demoTripReplyCarriesASurface() = runBlocking {
        val demo = DemoClient(requireNotNull(javaClass.classLoader?.getResource("demo.json")).readText(), language = "en")
        val reply = presentMessages(demo.chat("demo-trip").messages).last()
        assertEquals(listOf("text", "a2ui"), reply.parts.map { it.type })
        assertEquals("demo-fado", reply.parts.last().surface?.id)
        assertEquals(0, activityFinalStart(reply.parts))
        assertTrue(demo.supportsSurfaces)
        assertNull(reply.parts.first().surface)
    }
}

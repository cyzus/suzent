package com.suzent.mobile

import java.io.File
import java.net.URLDecoder
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CitationFixturesTest {
    private fun strings(array: JSONArray): List<String> = (0 until array.length()).map(array::getString)

    @Test fun citationsFollowSharedFixtures() {
        val fixtures = JSONObject(File("../../../packages/mobile-contract/citation-fixtures.json").readText())
        val sourceRows = fixtures.getJSONArray("sources")
        val sources = (0 until sourceRows.length()).map { index ->
            val row = sourceRows.getJSONObject(index)
            CitationSource(row.getString("id"), row.getString("type"), row.getString("title"), row.getString("url"))
        }
        val cases = fixtures.getJSONArray("cases")
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val name = case.getString("name")
            val output = markdownWithCitationLinks(case.getString("text"), sources, badges = true)
            val cites = Regex("""suzent-citation://sources/([^#>]+)#""").findAll(output)
                .map { match -> match.groupValues[1].split(',').map { URLDecoder.decode(it, "UTF-8") } }
                .sortedBy { it.joinToString(",") }.toList()
            val expected = case.getJSONArray("cites").let { rows ->
                (0 until rows.length()).map { strings(rows.getJSONArray(it)) }.sortedBy { it.joinToString(",") }
            }
            assertEquals(name, expected, cites)
            strings(case.getJSONArray("keeps")).forEach { assertTrue("$name keeps $it in $output", output.contains(it)) }
            strings(case.getJSONArray("drops")).forEach { assertFalse("$name drops $it in $output", output.contains(it)) }
        }
    }
}

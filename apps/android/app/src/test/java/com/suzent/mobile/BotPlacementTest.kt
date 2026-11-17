package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Test

class BotPlacementTest {
    private val tool = MessagePart("tool", toolName = "read_file", state = "running")
    @Test fun botMovesFromThinkingToRailToReply() {
        assertEquals(BotPlacement.Assembly, botPlacement(emptyList(), true, true, false))
        assertEquals(BotPlacement.Rail, botPlacement(listOf(tool), true, true, false))
        assertEquals(BotPlacement.Footer, botPlacement(listOf(tool, MessagePart("text", text = "Answer")), true, true, false))
        assertEquals(BotPlacement.Footer, botPlacement(listOf(tool), false, true, false))
        assertEquals(BotPlacement.None, botPlacement(listOf(tool), false, false, false))
    }
    @Test fun pendingApprovalStaysInRailAndRegentHasNoDuplicateIdentity() {
        val pending = tool.copy(state = "approval-requested")
        assertEquals(BotPlacement.Rail, botPlacement(listOf(pending), false, false, false))
        assertEquals(BotPlacement.None, botPlacement(listOf(pending), true, true, true))
    }
    @Test fun metadataDoesNotMoveBotAwayFromTrailingProse() {
        val parts = listOf(tool, MessagePart("text", text = "Answer"), MessagePart("citation-sources"), MessagePart("text", text = " "))
        assertEquals(BotPlacement.Footer, botPlacement(parts, true, true, false))
    }
}

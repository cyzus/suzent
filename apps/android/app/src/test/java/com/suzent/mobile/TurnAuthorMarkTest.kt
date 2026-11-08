package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TurnAuthorMarkTest {
    @Test fun regentChatLeavesIdentityToTheHeader() {
        assertNull(turnAuthorMark(regentChat = true, live = false, compact = true, pendingApproval = false))
        assertNull(turnAuthorMark(regentChat = true, live = true, compact = false, pendingApproval = false))
        assertNull(turnAuthorMark(regentChat = true, live = false, compact = false, pendingApproval = true))
    }

    @Test fun anotherChatKeepsALiveOrPendingMark() {
        assertEquals(TurnAuthorMark.Assembly, turnAuthorMark(regentChat = false, live = true, compact = true, pendingApproval = false))
        assertEquals(TurnAuthorMark.Assembly, turnAuthorMark(regentChat = false, live = false, compact = true, pendingApproval = true))
        assertEquals(TurnAuthorMark.Assembly, turnAuthorMark(regentChat = false, live = false, compact = false, pendingApproval = false))
    }

    @Test fun aFinishedTurnInAnotherChatKeepsTheCompactAssistantMark() {
        assertEquals(TurnAuthorMark.Assistant, turnAuthorMark(regentChat = false, live = false, compact = true, pendingApproval = false))
    }
}

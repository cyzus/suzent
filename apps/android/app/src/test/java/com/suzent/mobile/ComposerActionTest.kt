package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Test

class ComposerActionTest {
    @Test fun emptyComposerStartsVoiceAndContentSendsOutsideCalls() {
        assertEquals(ComposerAction.VOICE, ComposerAction.resolve(false, false, false, false, false))
        assertEquals(ComposerAction.SEND, ComposerAction.resolve(true, false, false, false, false))
    }
    @Test fun activeCallHasOneHangUpActionEvenWhileTaskRuns() {
        for (content in listOf(false, true)) for (busy in listOf(false, true)) {
            assertEquals(ComposerAction.HANG_UP, ComposerAction.resolve(content, busy, true, true, false))
        }
        for (busy in listOf(false, true)) assertEquals(ComposerAction.STOP, ComposerAction.resolve(false, busy, true, false, false))
    }
    @Test fun connectingCanBeCancelledAndConnectedCallsCanHangUp() {
        assertEquals(ComposerAction.CONNECTING, ComposerAction.resolve(false, false, false, true, true))
        assertEquals(ComposerAction.HANG_UP, ComposerAction.resolve(false, false, false, true, false))
    }
    @Test fun runningTasksKeepStopWhileOtherWorkShowsProgress() {
        assertEquals(ComposerAction.CONNECTING, ComposerAction.resolve(true, true, true, true, true))
        assertEquals(ComposerAction.LOADING, ComposerAction.resolve(true, true, false, false, false))
    }
    @Test fun typingDuringATurnRedirectsOrQueuesInsteadOfStopping() {
        assertEquals(ComposerAction.REDIRECT, ComposerAction.resolve(true, false, true, false, false, canRedirect = true))
        assertEquals(ComposerAction.QUEUE, ComposerAction.resolve(true, false, true, false, false, canRedirect = false))
        assertEquals(ComposerAction.LOADING, ComposerAction.resolve(true, true, true, false, false, canRedirect = true))
        assertEquals(ComposerAction.STOP, ComposerAction.resolve(false, false, true, false, false, canRedirect = true))
    }
}

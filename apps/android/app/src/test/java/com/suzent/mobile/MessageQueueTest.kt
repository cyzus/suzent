package com.suzent.mobile

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MessageQueueTest {
    @Test fun queuesAreKeptPerConversationInOrder() {
        val first = QueuedMessage("first")
        val second = QueuedMessage("second", listOf(PendingAttachment(File("a.png"), "a.png", "image/png")))
        var queues = MessageQueues().add("a", first).add("a", second).add("b", QueuedMessage("other"))
        assertEquals(listOf(first, second), queues.of("a"))
        assertEquals(listOf("a.png"), queues.attachments.map { it.name })
        queues = queues.remove("a", first.id)
        assertEquals(listOf(second), queues.of("a"))
        queues = queues.clear("a")
        assertEquals(emptyList<QueuedMessage>(), queues.of("a"))
        assertEquals(1, queues.of("b").size)
        assertEquals(emptyList<QueuedMessage>(), queues.of(null))
    }

    @Test fun redirectKeepsThePartialReplyAndEndsUnfinishedTools() {
        assertNull(interruptedReply(emptyList(), "m"))
        val reply = interruptedReply(listOf(
            MessagePart("reasoning", "thinking", state = "running"),
            MessagePart("tool", toolName = "bash", toolCallId = "t1", state = "running"),
            MessagePart("tool", toolName = "write", toolCallId = "t2", state = "approval-requested"),
            MessagePart("tool", toolName = "read", toolCallId = "t3", state = "completed"),
            MessagePart("text", "Halfway"),
        ), "m")!!
        assertEquals("assistant", reply.role)
        assertEquals("Halfway", reply.content)
        assertEquals("m", reply.model)
        assertEquals(listOf("completed", "error", "error", "completed", ""), reply.parts.map { it.state })
    }
}

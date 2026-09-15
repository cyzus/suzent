package com.suzent.mobile

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LiveTextBufferTest {
    @Test fun batchesDeltasAndFlushesTheLastChunk() {
        val buffer = LiveTextBuffer()
        repeat(100) { buffer.consume(JSONObject().put("type", "TEXT_MESSAGE_CONTENT").put("delta", "a")) }
        assertEquals("a".repeat(100), buffer.drain())
        assertNull(buffer.drain())
        buffer.consume(JSONObject().put("type", "TEXT_MESSAGE_CONTENT").put("delta", "尾"))
        assertEquals("a".repeat(100) + "尾", buffer.drain())
    }

    @Test fun snapshotReplacesPendingTextWithoutDuplicatingIt() {
        val buffer = LiveTextBuffer()
        buffer.consume(JSONObject().put("type", "TEXT_MESSAGE_CONTENT").put("delta", "old"))
        buffer.consume(JSONObject().put("type", "STREAM_RESET"))
        buffer.consume(JSONObject().put("type", "TEXT_MESSAGE_CONTENT").put("delta", "snapshot"))
        assertEquals("snapshot", buffer.drain())
        buffer.consume(JSONObject().put("type", "STREAM_RESET"))
        assertEquals("", buffer.drain())
    }
}

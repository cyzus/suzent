package com.suzent.mobile

import java.io.File
import java.nio.file.Files
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import org.junit.Assert.*
import org.junit.Test

class DemoClientTest {
    private fun client(storage: File? = null, language: String = "en", duration: Long = 10) = DemoClient(
        requireNotNull(javaClass.classLoader?.getResource("demo.json")).readText(), storage, language, duration)

    @Test fun examplesIncludeSuccessfulAndFailedActivities() = runBlocking {
        for (language in listOf("en", "zh")) {
            val demo = client(language = language)
            assertEquals(2, demo.chat("demo-ui").messages.last().parts.count { it.type == "tool" })
            assertTrue(demo.chat("demo-failure").messages.last().parts.any(::activityFailed))
            assertTrue(demo.chat("demo-note").messages.last().content.isNotEmpty())
        }
    }

    @Test fun streamsAndPersistsWithoutAConnection() = runBlocking {
        val directory = Files.createTempDirectory("suzent-demo").toFile()
        try {
            val storage = File(directory, "workspace.json")
            val demo = client(storage)
            val chat = demo.create("Test", "demo-travel")
            val buffer = LiveActivityBuffer()
            demo.send(chat.id, "Plan a trip")
            demo.observe(chat.id) { buffer.consume(it) }
            val saved = demo.chat(chat.id)
            assertFalse(saved.running)
            assertEquals(2, saved.messages.size)
            assertTrue(saved.messages.last().content.contains("London"))
            assertTrue(requireNotNull(buffer.drain()).any { it.type == "text" })
            assertEquals(saved.messages.last().content, client(storage).chat(chat.id).messages.last().content)
        } finally { directory.deleteRecursively() }
    }

    @Test fun approvalCanBeAllowedRejectedAndStopped() = runBlocking {
        val demo = client()
        val chat = demo.create("Tools")
        for (allowed in listOf(true, false)) {
            demo.send(chat.id, "tool approval")
            val state = demo.approvals(chat.id)
            val request = state.pending.single()
            assertEquals("allow", request.actions.first().behavior)
            demo.decideApprovals(chat.id, state.pending, mapOf(request.id to if (allowed) "allow" else "reject"))
            demo.observe(chat.id) {}
            assertTrue(demo.chat(chat.id).messages.last().content.contains(if (allowed) "Approved" else "rejected"))
            assertTrue(demo.approvals(chat.id).pending.isEmpty())
        }
        demo.send(chat.id, "tool")
        demo.stop(chat.id)
        assertTrue(demo.chat(chat.id).messages.last().content.contains("stopped"))
        assertTrue(demo.approvals(chat.id).pending.isEmpty())
    }

    @Test fun retryAfterApprovalRequestsAFreshDecision() = runBlocking {
        val demo = client()
        val chat = demo.create("Approval retry")
        demo.send(chat.id, "tool")
        var previous = ""
        for ((index, decision) in listOf("allow", "reject", "allow").withIndex()) {
            val state = demo.approvals(chat.id)
            val request = state.pending.single()
            assertNotEquals(previous, request.id)
            previous = request.id
            demo.decideApprovals(chat.id, state.pending, mapOf(request.id to decision))
            kotlinx.coroutines.withTimeout(5000) { demo.observe(chat.id) {} }
            assertFalse(demo.chat(chat.id).running)
            assertTrue(demo.approvals(chat.id).pending.isEmpty())
            if (index < 2) {
                demo.messageAction(chat.id, 1, "retry")
            }
        }
    }

    @Test fun managementReplayAndResetStayLocal() = runBlocking {
        val demo = client()
        val chat = demo.create("Original")
        demo.manageChat(chat.id, "pin")
        demo.manageChat(chat.id, "rename", "Renamed")
        demo.manageChat(chat.id, "move", "demo-travel")
        val managed = demo.chat(chat.id)
        assertTrue(managed.pinned)
        assertEquals("Renamed", managed.title)
        assertEquals("demo-travel", managed.projectId)
        demo.send(chat.id, "hello")
        demo.observe(chat.id) {}
        val fork = demo.messageAction(chat.id, 1, "fork")
        assertEquals(2, demo.chat(fork).messages.size)
        demo.messageAction(chat.id, 0, "edit", "trip")
        demo.observe(chat.id) {}
        assertEquals("trip", demo.chat(chat.id).messages.first().content)
        demo.messageAction(chat.id, 1, "retry")
        demo.observe(chat.id) {}
        assertEquals(2, demo.chat(chat.id).messages.size)
        demo.manageChat(chat.id, "delete")
        assertFalse(demo.chats().any { it.id == chat.id })
        demo.reset()
        assertEquals(7, demo.chats().size)
    }

    @Test fun attachmentsUseOnlyMetadataAndAreScoped() = runBlocking {
        val demo = client()
        val chat = demo.create("Attachments")
        // A missing file proves that the demo does not open or upload attachment bytes.
        val ids = demo.upload(chat.id, listOf(PendingAttachment(File("/nonexistent/demo-photo.png"), "photo.png", "image/png")))
        try {
            demo.send("demo-welcome", "", attachments = ids)
            fail("Cross-chat attachment accepted")
        } catch (_: IllegalArgumentException) {}
        demo.send(chat.id, "", attachments = ids)
        demo.observe(chat.id) {}
        val saved = demo.chat(chat.id)
        assertEquals("photo.png", saved.messages.first().files.single().filename)
        assertTrue(saved.messages.last().content.contains("nothing is uploaded"))
    }

    @Test fun observerDetachRecoversWithoutResending() = runBlocking {
        val demo = client(duration = 80)
        val chat = demo.create("Background")
        demo.send(chat.id, "hello")
        val observer = launch { demo.observe(chat.id) {} }
        delay(10)
        observer.cancel(); observer.join()
        assertTrue(demo.composer().id.isEmpty())
        val independent = demo.create("Independent")
        demo.send(independent.id, "New work")
        demo.observe(independent.id) {}
        assertEquals("New work", demo.chat(independent.id).messages.first().content)
        delay(100)
        val saved = demo.chat(chat.id)
        assertFalse(saved.running)
        assertEquals(2, saved.messages.size)
        assertTrue(demo.approvals(chat.id).pending.isEmpty())
    }

    @Test fun reopeningMarksUnfinishedTurnsAndLoadsChineseSamples() = runBlocking {
        val directory = Files.createTempDirectory("suzent-demo").toFile()
        try {
            val storage = File(directory, "workspace.json")
            val demo = client(storage, "zh-Hans")
            assertTrue(demo.prompts.first().contains("旅行"))
            val chat = demo.create("测试")
            demo.send(chat.id, "工具审批")
            val reopened = client(storage, "zh-Hans")
            assertFalse(reopened.chat(chat.id).running)
            assertTrue(reopened.chat(chat.id).messages.last().content.contains("中断"))
            reopened.reset()
            assertEquals(7, reopened.chats().size)
        } finally { directory.deleteRecursively() }
    }
}

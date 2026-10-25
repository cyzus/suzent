package com.suzent.mobile

import androidx.lifecycle.ViewModelProvider
import android.content.Intent
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ApprovalRetryTest {
    @Test(timeout = 120_000) fun retryInTheSameChatPublishesANewApprovalAndFinishes() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.startActivity(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        await("activity resumed") {
            ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).any { it is MainActivity }
        }
        val activity = onMain {
            ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<MainActivity>().single()
        }
        val model = onMain { ViewModelProvider(activity)[MobileModel::class.java].also { it.startDemo() } }
        await("demo ready") { model.isDemo && !model.busy }
        onMain { model.draft = "tool"; model.send() }
        await("first approval") { model.pendingApprovals.isNotEmpty() }
        val first = onMain { model.pendingApprovals.single().id }
        approve(model, "allow")
        await("first answer") { !model.streaming && model.selected?.running == false && model.pendingApprovals.isEmpty() }
        val chatID = onMain { model.selected!!.id }
        try {
            for (decision in listOf("reject", "allow")) {
                onMain { model.messageAction(presentMessages(model.selected!!.messages).last(), "retry") }
                await("approval after retry") { model.pendingApprovals.isNotEmpty() && model.pendingApprovals.single().id != first }
                assertNotEquals(first, onMain { model.pendingApprovals.single().id })
                assertTrue(onMain { model.selected!!.id == chatID })
                approve(model, decision)
                await("retried answer") { !model.busy && !model.streaming && model.selected?.running == false && model.pendingApprovals.isEmpty() }
            }
        } finally {
            onMain { model.selected?.let { model.manageChat(it, "delete") } }
            await("test chat removed") { !model.busy && model.chats.none { it.id == chatID } }
        }
    }

    private fun approve(model: MobileModel, action: String) = onMain {
        val request = model.pendingApprovals.single()
        model.chooseApproval(request, request.actions.first { it.id == action })
    }

    private fun await(label: String, condition: () -> Boolean) {
        val deadline = System.nanoTime() + 20_000_000_000L
        while (System.nanoTime() < deadline) {
            if (onMain(condition)) return
            Thread.sleep(50)
        }
        throw AssertionError("Timed out waiting for $label")
    }

    private fun <T> onMain(block: () -> T): T {
        var value: Result<T>? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync { value = runCatching(block) }
        return value!!.getOrThrow()
    }
}

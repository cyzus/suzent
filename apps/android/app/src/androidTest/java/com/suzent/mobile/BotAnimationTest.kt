package com.suzent.mobile

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.view.FrameMetrics
import android.view.Window
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.mutableStateOf
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class BotAnimationTest {
    @Test(timeout = 60_000) fun animationSettlesAndResumes() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val activity = launchActivity()
        val streaming = mutableStateOf(true)
        val durations = mutableListOf<Long>()
        val listener = Window.OnFrameMetricsAvailableListener { _, metrics, _ ->
            durations += metrics.getMetric(FrameMetrics.TOTAL_DURATION)
        }
        onMain {
            activity.window.addOnFrameMetricsAvailableListener(listener, Handler(Looper.getMainLooper()))
            activity.setContent { SuzentTheme { AssemblyBadge(thinking = false, streaming = streaming.value) } }
        }
        fun sample(label: String, milliseconds: Long): Int {
            onMain { durations.clear() }
            Thread.sleep(milliseconds)
            val frames = onMain { durations.sorted() }
            fun percentile(fraction: Double): Double = if (frames.isEmpty()) 0.0 else
                frames[((frames.size - 1) * fraction).toInt()] / 1_000_000.0
            instrumentation.sendStatus(0, Bundle().apply {
                putString("stream", "$label: frames=${frames.size}, p50=${percentile(.5)}ms, p95=${percentile(.95)}ms, p99=${percentile(.99)}ms\n")
            })
            return frames.size
        }
        try {
            Thread.sleep(3000)
            assertTrue("Active animation should produce frames", sample("active", 6000) > 30)
            onMain { streaming.value = false }
            Thread.sleep(5000)
            val idleFrames = sample("settled", 2000)
            if (InstrumentationRegistry.getArguments().getString("baseline") != "true") {
                assertTrue("Settled animation must stop drawing ($idleFrames frames)", idleFrames < 5)
            }
            onMain { streaming.value = true }
            Thread.sleep(1000)
            assertTrue("Stage changes must restart animation", sample("resumed", 2000) > 10)
        } finally {
            onMain {
                activity.window.removeOnFrameMetricsAvailableListener(listener)
                activity.finish()
            }
        }
    }

    @Test(timeout = 60_000) fun captureActivityLayouts() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val activity = launchActivity()
        val tool = MessagePart("tool", toolName = "read_file", toolCallId = "preview-tool", state = "running")
        val scenarios = listOf("rail", "expanded", "reply", "history", "pending", "tasks")
        try {
            for (scenario in scenarios) {
                val choices = RailChoices()
                if (scenario in listOf("expanded", "tasks")) choices.set("preview:preview-tool", true)
                val parts = when (scenario) {
                    "reply", "history" -> listOf(tool.copy(state = "complete", output = "done"), MessagePart("text", text = "Hello"))
                    "pending" -> listOf(tool.copy(state = "approval-requested"))
                    "tasks" -> listOf(tool.copy(toolName = "create_tasks"))
                    else -> listOf(tool)
                }
                onMain {
                    activity.setContent {
                        SuzentTheme {
                            androidx.compose.runtime.CompositionLocalProvider(LocalRailChoices provides choices, LocalRailScope provides "preview") {
                                androidx.compose.material3.Surface(Modifier.fillMaxSize()) {
                                    androidx.compose.foundation.layout.Column(Modifier.systemBarsPadding().padding(16.dp)) {
                                        ActivityTurn(parts, live = scenario != "history", compact = scenario == "history")
                                    }
                                }
                            }
                        }
                    }
                }
                Thread.sleep(1500)
                val image = instrumentation.uiAutomation.takeScreenshot()
                checkNotNull(image)
                java.io.File(instrumentation.targetContext.cacheDir, "bot-$scenario.png").outputStream().use {
                    image.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
                }
                image.recycle()
            }
        } finally { onMain { activity.finish() } }
    }

    private fun launchActivity(): MainActivity {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(!instrumentation.targetContext.getSystemService(android.app.KeyguardManager::class.java).isKeyguardLocked) {
            "Unlock the device before running animation tests"
        }
        // Shell launch also works on devices that restrict background activity starts.
        ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(
            "am start -n ${instrumentation.targetContext.packageName}/com.suzent.mobile.MainActivity"
        )).use { it.readBytes() }
        val deadline = System.nanoTime() + 10_000_000_000L
        while (!onMain {
            ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
                .any { it is MainActivity && !it.isFinishing && !it.isDestroyed }
        }) {
            check(System.nanoTime() < deadline) { "Activity did not resume" }
            Thread.sleep(50)
        }
        val activity = onMain {
            ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
                .filterIsInstance<MainActivity>().single { !it.isFinishing && !it.isDestroyed }
        }
        onMain { activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
        return activity
    }

    private fun <T> onMain(block: () -> T): T {
        var result: Result<T>? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }
}

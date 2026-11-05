package com.suzent.mobile

import android.content.Intent
import android.widget.FrameLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class VoiceCubeViewTest {
    @Test fun sharedCubeRendersAndChangesWithVoiceState() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val intent = Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val activity = instrumentation.startActivitySync(intent)
        lateinit var view: VoiceCubeWebView
        instrumentation.runOnMainSync {
            view = VoiceCubeWebView(activity)
            activity.setContentView(FrameLayout(activity).apply {
                setBackgroundColor(android.graphics.Color.WHITE)
                val density = resources.displayMetrics.density
                addView(view, FrameLayout.LayoutParams((260 * density).toInt(), (112 * density).toInt()))
            })
        }
        fun evaluate(script: String): String {
            val done = CountDownLatch(1)
            var value = ""
            instrumentation.runOnMainSync { view.evaluateJavascript(script) { value = it; done.countDown() } }
            check(done.await(5, TimeUnit.SECONDS))
            return value
        }
        fun awaitValue(script: String, accept: (String) -> Boolean): String {
            val end = System.nanoTime() + TimeUnit.SECONDS.toNanos(10)
            while (System.nanoTime() < end) {
                val value = evaluate(script)
                if (accept(value)) return value
                Thread.sleep(100)
            }
            error("Voice cube did not render: ${evaluate(script)}")
        }
        fun pixels(state: String, working: Boolean): String {
            evaluate("""window.__voicePixels=null; window.updateVoiceCube({status:'$state',working:$working,level:0,dark:false,reducedMotion:true});
                requestAnimationFrame(()=>requestAnimationFrame(()=>{
                  const c=document.querySelector('canvas'),g=c.getContext('webgl2');
                  if(!g){window.__voicePixels='no-canvas';return;}
                  const p=new Uint8Array(c.width*c.height*4);g.readPixels(0,0,c.width,c.height,g.RGBA,g.UNSIGNED_BYTE,p);
                  let count=0,hash=0;for(let i=0;i<p.length;i+=4){if(p[i+3]>0)count++;hash=(hash+p[i]*(i+1))%2147483647;}
                  window.__voicePixels=count+':'+hash;
                }));""")
            return awaitValue("window.__voicePixels") { it != "null" && it != "" }
        }
        try {
            awaitValue("typeof window.updateVoiceCube") { it == "\"function\"" }
            val listening = pixels("listening", false)
            val speaking = pixels("speaking", false)
            val working = pixels("listening", true)
            assertFalse("Presentation canvas is unavailable", listening.contains("no-canvas"))
            assertTrue("Cube was blank: $listening", listening.trim('"').substringBefore(':').toInt() > 100)
            assertNotEquals("Speech must deform the cube", listening, speaking)
            assertNotEquals("Working must show scan lines", listening, working)
            // Framebuffer pixels alone do not prove Android composited the canvas.
            instrumentation.waitForIdleSync()
            val location = IntArray(2)
            var width = 0
            var height = 0
            instrumentation.runOnMainSync {
                view.getLocationOnScreen(location)
                width = view.width
                height = view.height
            }
            val screenshot = checkNotNull(instrumentation.uiAutomation.takeScreenshot())
            var visiblePixels = 0
            for (y in location[1] until location[1] + height) {
                for (x in location[0] until location[0] + width) {
                    val pixel = screenshot.getPixel(x, y)
                    if (android.graphics.Color.red(pixel) < 200 &&
                        android.graphics.Color.green(pixel) < 200 &&
                        android.graphics.Color.blue(pixel) < 200) visiblePixels++
                }
            }
            screenshot.recycle()
            assertTrue("Cube pixels must reach the screen", visiblePixels > 100)

        } finally {
            instrumentation.runOnMainSync { view.destroy(); activity.finish() }
        }
    }
}

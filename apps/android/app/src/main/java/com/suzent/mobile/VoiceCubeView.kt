package com.suzent.mobile

import android.annotation.SuppressLint
import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Color
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.viewinterop.AndroidView
import org.json.JSONObject

@SuppressLint("SetJavaScriptEnabled")
internal class VoiceCubeWebView(context: Context) : WebView(context) {
    private var ready = false
    private var state = "{}"
    init {
        setBackgroundColor(Color.TRANSPARENT)
        isVerticalScrollBarEnabled = false
        isHorizontalScrollBarEnabled = false
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        settings.javaScriptEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.blockNetworkLoads = true
        setOnTouchListener { _, _ -> true }
        webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String) { ready = true; render() }
        }
        val html = context.assets.open("voice-cube.html").bufferedReader().use { it.readText() }
        loadDataWithBaseURL("https://voice.suzent.invalid/", html, "text/html", "UTF-8", null)
    }
    fun update(status: String, working: Boolean, micLevel: Double, dark: Boolean) {
        state = JSONObject().put("status", status).put("working", working)
            .put("level", micLevel).put("dark", dark)
            .put("reducedMotion", !ValueAnimator.areAnimatorsEnabled()).toString()
        render()
    }
    private fun render() { if (ready) evaluateJavascript("window.updateVoiceCube?.($state)", null) }
}

@Composable
fun VoiceCubeView(status: String, working: Boolean, micLevel: Double, modifier: Modifier = Modifier) {
    val dark = MaterialTheme.colorScheme.background.luminance() < 0.5f
    AndroidView(factory = { VoiceCubeWebView(it) }, modifier = modifier,
        update = { it.update(status, working, micLevel, dark) }, onRelease = { it.stopLoading(); it.destroy() })
}

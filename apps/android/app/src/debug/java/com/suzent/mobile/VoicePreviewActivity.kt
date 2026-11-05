package com.suzent.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

/** Debug-only, microphone-free preview of the real composer's animation host. */
class VoicePreviewActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContent {
            SuzentTheme {
                var tick by remember { mutableIntStateOf(0) }
                LaunchedEffect(Unit) { while (true) { delay(100); tick++ } }
                val states = listOf("connecting", "listening", "user_speaking", "thinking", "speaking")
                val state = states[(tick / 50) % states.size]
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.fillMaxSize().systemBarsPadding().padding(24.dp),
                        verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(stringResource(R.string.voice_preview_title), style = MaterialTheme.typography.titleLarge)
                        Text(stringResource(R.string.voice_preview_notice), modifier = Modifier.padding(vertical = 16.dp))
                        Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
                            .border(2.dp, MaterialTheme.colorScheme.outline).animateContentSize().padding(10.dp)) {
                            VoiceCubeView(state, tick / 250 % 2 == 1,
                                if (state == "user_speaking") 0.5 + 0.4 * kotlin.math.sin(tick.toDouble()) else 0.0,
                                Modifier.fillMaxWidth().height(112.dp))
                            Text(stringResource(when (state) {
                                "connecting" -> R.string.voice_connecting
                                "thinking" -> R.string.voice_thinking
                                "speaking" -> R.string.voice_speaking
                                else -> R.string.voice_listening
                            }), modifier = Modifier.padding(8.dp))
                        }
                        TextButton(onClick = { finish() }, modifier = Modifier.padding(top = 16.dp)) {
                            Text(stringResource(R.string.voice_preview_close))
                        }
                    }
                }
            }
        }
    }
}

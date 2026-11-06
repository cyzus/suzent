package com.suzent.mobile

import android.annotation.SuppressLint
import android.content.Context
import android.media.*
import android.media.audiofx.AcousticEchoCanceler
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject

class VoiceSession(private val context: Context, private val scope: CoroutineScope, private val onError: (Int) -> Unit,
                   private val onRefresh: () -> Unit) {
    var active by mutableStateOf(false)
        private set
    var animationState by mutableStateOf("idle")
        private set
    var working by mutableStateOf(false)
        private set
    var micLevel by mutableStateOf(0.0)
        private set
    var status by mutableStateOf(R.string.voice_connecting)
        private set
    var transcript by mutableStateOf("")
        private set
    private var job: Job? = null
    private var socket: WebSocket? = null

    fun start(prepare: suspend () -> Pair<BackendClient, String>) {
        if (active) return
        active = true
        animationState = "connecting"
        working = false
        micLevel = 0.0
        status = R.string.voice_connecting
        transcript = ""
        job = scope.launch {
            val frames = Channel<Any>(128)
            try {
                val (client, chatId) = prepare()
                ensureActive()
                socket = client.voiceSocket(chatId, object : WebSocketListener() {
                    override fun onMessage(webSocket: WebSocket, text: String) { offer(text) }
                    override fun onMessage(webSocket: WebSocket, bytes: ByteString) { offer(bytes) }
                    private fun offer(value: Any) {
                        if (frames.trySend(value).isFailure) frames.close(IllegalStateException("Voice queue full"))
                    }
                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { frames.close(t) }
                    override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                        frames.close(if (code == 1000) null else IllegalStateException("Voice closed"))
                    }
                })
                val first = withTimeout(20_000) { frames.receive() } as? String ?: error("Missing voice handshake")
                run {
                    val ready = JSONObject(first)
                    check(ready.optString("type") == "ready")
                    val input = ready.getInt("input_sample_rate")
                    val output = ready.getInt("output_sample_rate")
                    check(input in 8000..48000 && output in 8000..48000)
                    working = ready.optBoolean("working")
                    startAudio(input, output, frames)
                }
            } catch (_: TimeoutCancellationException) {
                onError(R.string.voice_failed)
            } catch (_: CancellationException) {
                // A user hang-up or leaving the app ends capture immediately.
            } catch (_: Exception) {
                onError(R.string.voice_failed)
            } finally {
                frames.cancel()
                socket?.cancel(); socket = null
                active = false
                animationState = "idle"
                working = false
                micLevel = 0.0
                onRefresh()
            }
        }
    }

    @SuppressLint("MissingPermission")
    private suspend fun startAudio(inputRate: Int, outputRate: Int, frames: Channel<Any>) = coroutineScope {
        val manager = context.getSystemService(AudioManager::class.java)
        val previousMode = manager.mode
        val previousSpeaker = manager.isSpeakerphoneOn
        val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).build())
            .setOnAudioFocusChangeListener { change -> if (change < 0) scope.launch { stop() } }.build()
        check(manager.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED)
        var recorder: AudioRecord? = null
        var player: AudioTrack? = null
        var echo: AcousticEchoCanceler? = null
        var capture: Job? = null
        var playback: Job? = null
        val audio = Channel<Pair<Int, ByteArray>>(128)
        val playbackEpoch = java.util.concurrent.atomic.AtomicInteger()
        try {
            manager.mode = AudioManager.MODE_IN_COMMUNICATION
            if (!manager.isBluetoothScoOn && !manager.isWiredHeadsetOn) manager.isSpeakerphoneOn = true
            val record = AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, inputRate,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                maxOf(AudioRecord.getMinBufferSize(inputRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT), inputRate / 5))
            recorder = record
            check(record.state == AudioRecord.STATE_INITIALIZED)
            if (AcousticEchoCanceler.isAvailable()) echo = AcousticEchoCanceler.create(record.audioSessionId)?.apply { enabled = true }
            val track = AudioTrack.Builder()
                .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setAudioFormat(AudioFormat.Builder().setSampleRate(outputRate).setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                .setBufferSizeInBytes(maxOf(AudioTrack.getMinBufferSize(outputRate, AudioFormat.CHANNEL_OUT_MONO,
                    AudioFormat.ENCODING_PCM_16BIT), outputRate / 5)).setTransferMode(AudioTrack.MODE_STREAM).build()
            player = track
            check(track.state == AudioTrack.STATE_INITIALIZED)
            track.play()
            record.startRecording()
            status = R.string.voice_listening
            animationState = "listening"
            capture = launch(Dispatchers.IO) {
                val bytes = ByteArray(inputRate / 25 * 2)
                var lastMeter = 0L
                while (isActive) {
                    val count = record.read(bytes, 0, bytes.size)
                    if (count <= 0) error("Microphone unavailable")
                    val now = android.os.SystemClock.elapsedRealtime()
                    if (now - lastMeter >= 80) {
                        var sum = 0.0
                        for (index in 0 until count - 1 step 2) {
                            val sample = ((bytes[index].toInt() and 255) or (bytes[index + 1].toInt() shl 8)).toShort().toDouble() / 32768
                            sum += sample * sample
                        }
                        val rms = kotlin.math.sqrt(sum / maxOf(1, count / 2))
                        val level = ((20 * kotlin.math.log10(maxOf(rms, 0.00001)) + 60) / 50).coerceIn(0.0, 1.0)
                        withContext(Dispatchers.Main) { micLevel = level }
                        lastMeter = now
                    }
                    val connection = socket ?: break
                    check(connection.queueSize() < 256_000 && connection.send(bytes.toByteString(0, count)))
                }
            }
            playback = launch(Dispatchers.IO) {
                for ((epoch, bytes) in audio) {
                    var offset = 0
                    while (offset < bytes.size && isActive && epoch == playbackEpoch.get()) {
                        val written = track.write(bytes, offset, bytes.size - offset, AudioTrack.WRITE_NON_BLOCKING)
                        check(written >= 0)
                        if (written == 0) delay(5) else offset += written
                    }
                }
            }
            for (frame in frames) when (frame) {
                is ByteString -> check(audio.trySend(playbackEpoch.get() to frame.toByteArray()).isSuccess)
                is String -> {
                    val message = JSONObject(frame)
                    when (message.optString("type")) {
                        "state" -> {
                            animationState = message.optString("state").takeIf { it in setOf("listening", "user_speaking", "thinking", "speaking") } ?: "listening"
                            status = when (animationState) {
                                "speaking" -> R.string.voice_speaking
                                "thinking" -> R.string.voice_thinking
                                else -> R.string.voice_listening
                            }
                        }
                        "working" -> { working = message.optBoolean("active"); onRefresh() }
                        "transcript" -> transcript = message.optString("text")
                        "interrupted" -> {
                            playbackEpoch.incrementAndGet()
                            while (audio.tryReceive().isSuccess) { }
                            track.pause(); track.flush(); track.play()
                        }
                        "error" -> error("Voice service unavailable")
                        "closed" -> break
                    }
                }
            }
        } finally {
            capture?.cancel(); playback?.cancel()
            runCatching { recorder?.stop() }
            runCatching { player?.pause(); player?.flush() }
            withContext(NonCancellable) { capture?.join(); playback?.join() }
            echo?.release(); recorder?.release(); player?.release()
            audio.cancel()
            manager.isSpeakerphoneOn = previousSpeaker
            manager.mode = previousMode
            manager.abandonAudioFocusRequest(focus)
        }
    }

    fun stop() {
        job?.cancel()
        socket?.cancel()
    }
}

package com.suzent.mobile

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

class MobileModel(application: Application) : AndroidViewModel(application) {
    var origin by mutableStateOf("")
    var token by mutableStateOf("")
    var chats by mutableStateOf<List<Chat>>(emptyList())
    var selected by mutableStateOf<Chat?>(null)
    var draft by mutableStateOf("")
    var liveText by mutableStateOf("")
    var error by mutableStateOf<String?>(null)
    var busy by mutableStateOf(false)
    var streaming by mutableStateOf(false)
    var connected by mutableStateOf(false)
    var nodeEnabled by mutableStateOf(false)
    var nodeStatus by mutableStateOf(text(R.string.node_off))
    private val store = CredentialStore(application)
    private var connection: Connection? = null
    private var client: BackendClient? = null
    private var streamJob: Job? = null
    private var socket: WebSocket? = null
    private var foreground = false
    private var generation = 0

    private fun text(id: Int, vararg args: Any): String = getApplication<Application>().getString(id, *args)

    init {
        try {
            connection = store.load()
            origin = connection?.origin.orEmpty()
            token = connection?.hostToken.orEmpty()
        } catch (_: Exception) { error = text(R.string.secure_error) }
    }

    fun connect() {
        if (busy) return
        busy = true
        error = null
        viewModelScope.launch {
            var candidate: BackendClient? = null
            try {
                val backend = Backend.parse(origin, BuildConfig.DEBUG)
                val credential = token.trim()
                require(credential.isNotEmpty())
                val api = BackendClient(backend, credential)
                candidate = api
                val listing = api.chats()
                val saved = Connection(backend.origin.toString(), credential,
                    if (connection?.origin == backend.origin.toString()) connection?.nodeToken.orEmpty() else "")
                store.save(saved)
                client?.close()
                client = api
                connection = saved
                chats = listing
                connected = true
                token = ""
            } catch (_: Exception) {
                candidate?.close()
                error = text(R.string.connect_error)
            } finally { busy = false }
        }
    }

    fun refresh() { viewModelScope.launch { refreshNow() } }

    private suspend fun refreshNow() {
        val api = client ?: return
        val current = generation
        try {
            val listing = api.chats()
            if (current != generation) return
            chats = listing
            val id = selected?.id
            if (id != null && !streaming) {
                val chat = api.chat(id)
                if (current == generation && selected?.id == id) selected = chat
            }
            if (current == generation) error = null
        } catch (error: CancellationException) { throw error }
        catch (failure: Exception) {
            if (BuildConfig.DEBUG) {
                val status = failure.message?.takeIf { it.matches(Regex("HTTP [0-9]{3}")) }
                android.util.Log.d("SuzentNetwork", "Refresh failure: ${failure.javaClass.simpleName} / ${status ?: failure.cause?.javaClass?.simpleName ?: "transport"}")
            }
            if (current == generation) error = text(R.string.refresh_error)
        }
    }

    fun open(chat: Chat) {
        if (streaming || busy) return
        selected = chat
        liveText = ""
        viewModelScope.launch {
            refreshNow()
            if (selected?.id == chat.id) observe(chat.id)
        }
    }

    fun create() {
        val api = client ?: return
        if (busy || streaming) return
        busy = true
        viewModelScope.launch {
            try {
                selected = api.create(text(R.string.mobile_conversation))
                refreshNow()
            } catch (_: Exception) { error = text(R.string.request_error) }
            finally { busy = false }
        }
    }

    fun send() {
        val api = client ?: return
        val id = selected?.id ?: return
        val message = draft.trim()
        if (busy || streaming || message.isEmpty()) return
        busy = true
        error = null
        viewModelScope.launch {
            try {
                api.send(id, message)
                draft = ""
                refreshNow()
                if (foreground) observe(id)
            } catch (_: Exception) { error = text(R.string.send_unknown) }
            finally { busy = false }
        }
    }

    private fun observe(id: String) {
        val api = client ?: return
        if (streaming || !foreground) return
        val current = generation
        streaming = true
        liveText = ""
        streamJob = viewModelScope.launch {
            try {
                api.observe(id) { event ->
                    withContext(Dispatchers.Main) {
                        if (current == generation && foreground) {
                            when (event.optString("type")) {
                                "STREAM_RESET" -> liveText = ""
                                "TEXT_MESSAGE_CONTENT" -> liveText += event.optString("delta")
                                "RUN_ERROR" -> error = text(R.string.task_error)
                            }
                        }
                    }
                }
                val saved = api.chat(id)
                if (current == generation && selected?.id == id) {
                    selected = saved
                    liveText = ""
                }
            } catch (error: CancellationException) { throw error }
            catch (_: Exception) { if (current == generation && foreground) error = text(R.string.stream_error) }
            finally { if (current == generation) streaming = false }
        }
    }

    fun stop() {
        val api = client ?: return
        val id = selected?.id ?: return
        viewModelScope.launch {
            try { api.stop(id) } catch (_: Exception) { error = text(R.string.request_error) }
        }
    }

    fun setForeground(active: Boolean) {
        foreground = active
        if (!active) {
            client?.cancelLive()
            streamJob?.cancel()
            streaming = false
            liveText = ""
            disconnectNode()
        } else {
            viewModelScope.launch {
                refreshNow()
                selected?.let { chat -> observe(chat.id) }
                if (nodeEnabled && foreground) startNode()
            }
        }
    }

    fun toggleNode(enabled: Boolean) {
        nodeEnabled = enabled
        if (enabled && foreground) startNode() else disconnectNode()
    }

    private fun disconnectNode() {
        socket?.cancel()
        socket = null
        nodeStatus = text(if (nodeEnabled) R.string.node_offline else R.string.node_off)
    }

    private fun startNode() {
        disconnectNode()
        val api = client ?: return
        val saved = connection ?: return
        nodeStatus = text(R.string.node_connecting)
        socket = api.node(object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                viewModelScope.launch {
                    if (socket !== webSocket || !foreground) { webSocket.cancel(); return@launch }
                    webSocket.send(NodeProtocol.connect("Suzent Android", "android", saved.nodeToken).toString())
                }
            }
            override fun onMessage(webSocket: WebSocket, text: String) {
                viewModelScope.launch {
                    if (socket !== webSocket || !foreground) return@launch
                    try {
                        val message = JSONObject(text)
                        when (message.optString("type")) {
                            "pending" -> nodeStatus = text(R.string.node_pending, message.optString("pairing_code"))
                            "connected" -> {
                                val credential = message.optString("device_token")
                                if (credential.isNotEmpty()) {
                                    val updated = saved.copy(nodeToken = credential)
                                    store.save(updated)
                                    connection = updated
                                }
                                nodeStatus = text(R.string.node_online)
                            }
                            "error" -> { disconnectNode(); nodeStatus = text(R.string.node_error) }
                            else -> NodeProtocol.reply(message, "android")?.let { webSocket.send(it.toString()) }
                        }
                    } catch (_: Exception) { disconnectNode(); nodeStatus = text(R.string.node_error) }
                }
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                viewModelScope.launch {
                    if (socket === webSocket) { disconnectNode(); nodeStatus = text(R.string.node_error) }
                }
            }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, null)
                viewModelScope.launch {
                    if (socket === webSocket) { disconnectNode(); nodeStatus = text(R.string.node_error) }
                }
            }
        })
    }

    fun forget() {
        if (busy) return
        try { store.clear() } catch (_: Exception) { error = text(R.string.secure_error); return }
        generation++
        nodeEnabled = false
        disconnectNode()
        streamJob?.cancel()
        client?.close()
        client = null
        connection = null
        connected = false
        selected = null
        chats = emptyList()
        token = ""
        origin = ""
        draft = ""
        streaming = false
        liveText = ""
    }

    override fun onCleared() { disconnectNode(); client?.close() }
}

package com.suzent.mobile

import java.util.Base64
import java.io.IOException
import java.net.SocketTimeoutException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import okhttp3.Call
import okhttp3.Headers
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.Buffer
import okio.BufferedSource
import okio.ByteString
import okio.ByteString.Companion.toByteString
import okio.Source
import okio.Timeout
import okio.buffer
import org.json.JSONObject

/** How to reach a desktop through its owner's relay; carried by the pairing QR and the session. */
data class RelayRoute(val url: String, val channel: String, val key: String) {
    val staticKey: ByteArray get() = Base64.getUrlDecoder().decode(key)

    /** `wss://<relay>/c/<channel>/__suzent_e2e__`, as OkHttp spells it. */
    val socketUrl: HttpUrl get() = requireNotNull(url.toHttpUrlOrNull()).newBuilder()
        .addPathSegment("c").addPathSegment(channel).addPathSegment("__suzent_e2e__").build()

    fun json(): JSONObject = JSONObject().put("version", 1).put("url", url).put("channel", channel).put("key", key)

    companion object {
        /** The only origin a relay-backed client is given; requests to it never leave the tunnel. */
        val placeholder: HttpUrl = requireNotNull("https://relay.suzent.invalid/".toHttpUrlOrNull())

        fun parse(json: JSONObject?, allowHttp: Boolean = false): RelayRoute? {
            if (json == null || json.optInt("version") != 1) return null
            return runCatching {
                val url = requireNotNull(json.getString("url").toHttpUrlOrNull())
                require(url.isHttps || allowHttp)
                require(url.username.isEmpty() && url.password.isEmpty() && url.query == null && url.fragment == null)
                val channel = json.getString("channel")
                require(channel.matches(Regex("[A-Za-z0-9_-]{16,128}")))
                val route = RelayRoute(url.toString().removeSuffix("/"), channel, json.getString("key"))
                RelayCrypto.decode(route.staticKey)
                route
            }.getOrNull()
        }
    }
}

/**
 * One end-to-end encrypted WebSocket to the desktop through a relay. Inside it the phone plays
 * the relay's part of the relay frame protocol: it sends `hreq`/`wopen` and the desktop answers
 * with `hres`, body chunks and `wopened`, exactly as over the relay's own agent socket.
 */
class RelayTunnel(private val route: RelayRoute, private val transport: OkHttpClient) {
    private val ids = AtomicLong()
    private val lock = Any()
    @Volatile private var link: Link? = null
    @Volatile var closed = false
        private set

    /**
     * Returns an open, handshaken link, dialling a new one if there is none or the last one
     * failed. A failed link never comes back: its counters can't be trusted, so a fresh
     * handshake starts a fresh session.
     */
    private fun connect(timeoutMillis: Long = 15_000): Link {
        val current = synchronized(lock) {
            if (closed) throw IOException("Relay connection closed")
            link?.takeUnless { it.failed } ?: Link().also { link = it; it.dial() }
        }
        current.await(timeoutMillis)
        return current
    }

    fun close() {
        val current = synchronized(lock) { closed = true; link.also { link = null } }
        current?.shutdown(IOException("Relay connection closed"))
    }

    private inner class Link : WebSocketListener() {
        val http = ConcurrentHashMap<String, HttpExchange>()
        val sockets = ConcurrentHashMap<String, RelayWebSocket>()
        private val opened = CountDownLatch(1)
        private val ephemeral = RelayCrypto.newEphemeral()
        private var socket: WebSocket? = null
        @Volatile private var session: RelaySession? = null
        @Volatile private var failure: IOException? = null
        @Volatile var failed = false
            private set

        fun dial() { socket = transport.newWebSocket(Request.Builder().url(route.socketUrl).build(), this) }

        fun await(timeoutMillis: Long) {
            if (!opened.await(timeoutMillis, TimeUnit.MILLISECONDS)) {
                shutdown(IOException("Relay did not answer"))
            }
            failure?.let { throw it }
        }

        override fun onOpen(webSocket: WebSocket, response: Response) {
            webSocket.send(RelayCrypto.encode(ephemeral.public).toByteString())
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            try {
                val current = session
                if (current == null) {
                    session = RelayCrypto.finish(ephemeral, route.staticKey, route.channel, bytes.toByteArray())
                    opened.countDown()
                    return
                }
                val plaintext = current.decrypt(bytes.toByteArray())
                if (plaintext.isEmpty()) throw RelayCryptoFailure("Empty frame")
                when (plaintext[0].toInt()) {
                    0 -> onFrame(JSONObject(String(plaintext, 1, plaintext.size - 1, Charsets.UTF_8)))
                    1 -> onBinary(plaintext.copyOfRange(1, plaintext.size))
                    else -> throw RelayCryptoFailure("Unknown frame type")
                }
            } catch (error: Exception) {
                shutdown(error as? IOException ?: IOException(error))
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) = shutdown(RelayCryptoFailure("Plaintext on an encrypted route"))
        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) = shutdown(IOException("Relay connection closed ($code)"))
        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = shutdown(IOException("Relay connection closed ($code)"))
        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) =
            shutdown(t as? IOException ?: IOException(t))

        fun shutdown(error: IOException) {
            synchronized(this) {
                if (failed) return
                failed = true
                failure = error
            }
            opened.countDown()
            socket?.cancel()
            http.values.forEach { it.fail(error) }
            http.clear()
            sockets.values.forEach { it.peerFailed(error) }
            sockets.clear()
        }

        private fun seal(plaintext: ByteArray) {
            val current = session ?: throw IOException("Relay connection not open")
            // Counters must reach the wire in the order they were used.
            synchronized(this) {
                if (failed) throw failure ?: IOException("Relay connection closed")
                if (socket?.send(current.encrypt(plaintext).toByteString()) != true) throw IOException("Relay connection closed")
            }
        }

        fun send(frame: JSONObject) = seal(byteArrayOf(0) + frame.toString().toByteArray(Charsets.UTF_8))

        fun sendBinary(kind: Int, id: String, payload: ByteArray) {
            val rawId = id.toByteArray(Charsets.UTF_8)
            seal(byteArrayOf(1, kind.toByte(), rawId.size.toByte()) + rawId + payload)
        }

        private fun onFrame(frame: JSONObject) {
            val id = frame.optString("id")
            when (frame.optString("t")) {
                "hres" -> http[id]?.head(frame)
                "hchunk" -> http[id]?.chunk(Base64.getDecoder().decode(frame.getString("b")))
                "hack" -> http[id]?.ack(frame.optLong("n"))
                "hend" -> http.remove(id)?.end()
                "herr" -> http.remove(id)?.fail(IOException(frame.optString("message", "Request failed")))
                "wopened" -> sockets[id]?.peerOpened()
                "werr" -> sockets.remove(id)?.peerFailed(IOException(frame.optString("message", "WebSocket refused")))
                "wmsg" -> sockets[id]?.let { socket ->
                    if (frame.has("s")) socket.peerText(frame.getString("s"))
                    else socket.peerBytes(Base64.getDecoder().decode(frame.getString("b")).toByteString())
                }
                "wclose" -> sockets.remove(id)?.peerClosed(frame.optInt("code", 1000), frame.optString("reason"))
            }
        }

        private fun onBinary(frame: ByteArray) {
            if (frame.size < 2 || frame.size < 2 + (frame[1].toInt() and 0xff)) return
            val end = 2 + (frame[1].toInt() and 0xff)
            val id = String(frame, 2, end - 2, Charsets.UTF_8)
            val payload = frame.copyOfRange(end, frame.size)
            when (frame[0].toInt()) {
                HCHUNK -> http[id]?.chunk(payload)
                WBIN -> sockets[id]?.peerBytes(payload.toByteString())
                WTEXT -> sockets[id]?.peerText(String(payload, Charsets.UTF_8))
            }
        }
    }

    /**
     * Runs [request] through the tunnel. Blocks like a network call and honours [call]'s
     * cancellation and, between messages from the desktop, [readTimeoutMillis] (0 waits forever).
     */
    fun execute(call: Call, request: Request, readTimeoutMillis: Long = 0): Response {
        val link = connect()
        val id = "h${ids.incrementAndGet()}"
        val exchange = HttpExchange(link, id, call, readTimeoutMillis)
        link.http[id] = exchange
        val body = request.body?.let { body -> Buffer().also { body.writeTo(it) }.readByteArray() }
        val headers = JSONObject()
        request.headers.forEach { (name, value) -> headers.put(name.lowercase(), value) }
        request.body?.contentType()?.let { headers.put("content-type", it.toString()) }
        if (body != null) headers.put("content-length", body.size.toString())
        val url = request.url
        val frame = JSONObject().put("t", "hreq").put("id", id).put("method", request.method)
            .put("path", url.encodedPath + (url.encodedQuery?.let { "?$it" } ?: "")).put("headers", headers)
        // A large body inline would be one oversized WebSocket message, so it streams in chunks
        // paced by the desktop's acknowledgements instead.
        val streamed = body != null && body.size > STREAM_THRESHOLD
        if (streamed) frame.put("stream", true)
        else if (body != null && body.isNotEmpty()) frame.put("b", Base64.getEncoder().encodeToString(body))
        try {
            link.send(frame)
            if (streamed) {
                for (start in body!!.indices step BODY_CHUNK) {
                    val chunk = body.copyOfRange(start, minOf(body.size, start + BODY_CHUNK))
                    exchange.reserve(chunk.size)
                    link.sendBinary(HBODY, id, chunk)
                }
                link.send(JSONObject().put("t", "hreqend").put("id", id))
            }
        } catch (error: IOException) {
            if (link.http.remove(id) != null) runCatching { link.send(JSONObject().put("t", "hcancel").put("id", id)) }
            throw error
        }
        val head = exchange.awaitHead()
        val responseHeaders = Headers.Builder().apply {
            val names = head.optJSONObject("headers") ?: JSONObject()
            names.keys().forEach { name ->
                when (val value = names.get(name)) {
                    is org.json.JSONArray -> (0 until value.length()).forEach { addUnsafeNonAscii(name, value.getString(it)) }
                    else -> addUnsafeNonAscii(name, value.toString())
                }
            }
        }.build()
        val contentType = responseHeaders["content-type"]?.toMediaTypeOrNull()
        val source = exchange.source().buffer()
        return Response.Builder().request(request).protocol(Protocol.HTTP_1_1)
            .code(head.getInt("status")).message("").headers(responseHeaders)
            .body(object : ResponseBody() {
                override fun contentType() = contentType
                override fun contentLength() = -1L
                override fun source(): BufferedSource = source
            }).build()
    }

    /** Opens [request]'s path as a WebSocket on the desktop, through the tunnel. */
    fun webSocket(request: Request, listener: WebSocketListener): WebSocket {
        val id = "w${ids.incrementAndGet()}"
        val socket = RelayWebSocket(id, request, listener)
        Thread {
            try {
                val link = connect()
                socket.link = link
                link.sockets[id] = socket
                val headers = JSONObject()
                request.headers.forEach { (name, value) -> headers.put(name.lowercase(), value) }
                val url = request.url
                link.send(JSONObject().put("t", "wopen").put("id", id)
                    .put("path", url.encodedPath + (url.encodedQuery?.let { "?$it" } ?: "")).put("headers", headers))
            } catch (error: IOException) {
                socket.link?.sockets?.remove(id)
                socket.peerFailed(error)
            }
        }.apply { isDaemon = true; name = "relay-wopen" }.start()
        return socket
    }

    private class HttpExchange(private val link: Link, private val id: String, private val call: Call, private val readTimeoutMillis: Long) {
        private val head = LinkedBlockingQueue<Result<JSONObject>>()
        private val chunks = LinkedBlockingQueue<Result<ByteArray>>()
        private val window = java.lang.Object()
        private var inFlight = 0L
        @Volatile private var finished = false

        fun head(frame: JSONObject) { head.offer(Result.success(frame)) }
        fun chunk(bytes: ByteArray) { if (bytes.isNotEmpty()) chunks.offer(Result.success(bytes)) }
        fun ack(count: Long) = synchronized(window) { inFlight = maxOf(0, inFlight - count); window.notifyAll() }
        fun end() { finished = true; head.offer(Result.failure(IOException("Response ended without a head"))); chunks.offer(Result.success(ByteArray(0))); wake() }
        fun fail(error: IOException) { finished = true; head.offer(Result.failure(error)); chunks.offer(Result.failure(error)); wake() }
        private fun wake() = synchronized(window) { window.notifyAll() }

        private fun abandon(error: IOException): Nothing {
            if (link.http.remove(id) != null) runCatching { link.send(JSONObject().put("t", "hcancel").put("id", id)) }
            throw error
        }

        private fun deadline() = if (readTimeoutMillis > 0) System.nanoTime() + readTimeoutMillis * 1_000_000 else Long.MAX_VALUE

        private fun check(deadline: Long) {
            if (call.isCanceled()) abandon(IOException("Canceled"))
            if (System.nanoTime() > deadline) abandon(SocketTimeoutException("The desktop did not answer through the relay"))
        }

        /** Waits until the desktop has read enough of the body for [size] more bytes to fit its window. */
        fun reserve(size: Int) {
            val deadline = deadline()
            synchronized(window) {
                while (inFlight > 0 && inFlight + size > BODY_WINDOW) {
                    if (finished) throw IOException("Request ended")
                    check(deadline)
                    window.wait(250)
                }
                inFlight += size
            }
        }

        private fun <T> await(queue: LinkedBlockingQueue<Result<T>>): T {
            val deadline = deadline()
            while (true) {
                check(deadline)
                val next = queue.poll(250, TimeUnit.MILLISECONDS) ?: continue
                return next.getOrThrow()
            }
        }

        fun awaitHead(): JSONObject = await(head)

        fun source(): Source = object : Source {
            private var done = false

            override fun read(sink: Buffer, byteCount: Long): Long {
                if (done) return -1
                val bytes = await(chunks)
                if (bytes.isEmpty()) { done = true; return -1 }
                sink.write(bytes)
                return bytes.size.toLong()
            }

            override fun timeout(): Timeout = Timeout.NONE

            override fun close() {
                if (!finished && link.http.remove(id) != null) runCatching { link.send(JSONObject().put("t", "hcancel").put("id", id)) }
            }
        }
    }

    private class RelayWebSocket(private val id: String, private val request: Request, private val listener: WebSocketListener) : WebSocket {
        @Volatile var link: Link? = null
        @Volatile private var open = false
        @Volatile private var ended = false

        override fun request(): Request = request
        override fun queueSize(): Long = 0

        override fun send(text: String): Boolean = deliver { it.sendBinary(WTEXT, id, text.toByteArray(Charsets.UTF_8)) }
        override fun send(bytes: ByteString): Boolean = deliver { it.sendBinary(WBIN, id, bytes.toByteArray()) }

        private fun deliver(block: (Link) -> Unit): Boolean {
            val current = link
            if (!open || ended || current == null) return false
            return try { block(current); true } catch (_: IOException) { false }
        }

        private fun goodbye(code: Int, reason: String) {
            val current = link ?: return
            current.sockets.remove(id)
            runCatching { current.send(JSONObject().put("t", "wclose").put("id", id).put("code", code).put("reason", reason)) }
        }

        override fun close(code: Int, reason: String?): Boolean {
            if (ended) return false
            ended = true
            goodbye(code, reason.orEmpty())
            listener.onClosed(this, code, reason.orEmpty())
            return true
        }

        override fun cancel() {
            if (ended) return
            ended = true
            goodbye(1001, "")
            listener.onFailure(this, IOException("Canceled"), null)
        }

        fun peerOpened() {
            open = true
            listener.onOpen(this, Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(101).message("Switching Protocols").build())
        }
        fun peerText(text: String) { if (!ended) listener.onMessage(this, text) }
        fun peerBytes(bytes: ByteString) { if (!ended) listener.onMessage(this, bytes) }
        fun peerClosed(code: Int, reason: String) {
            if (ended) return
            ended = true
            listener.onClosing(this, code, reason)
            listener.onClosed(this, code, reason)
        }
        fun peerFailed(error: IOException) {
            if (ended) return
            ended = true
            listener.onFailure(this, error, null)
        }
    }

    private companion object {
        const val HCHUNK = 1
        const val HBODY = 2
        const val WBIN = 3
        const val WTEXT = 4
        const val STREAM_THRESHOLD = 256 * 1024
        const val BODY_CHUNK = 256 * 1024
        /** The desktop acknowledges body bytes as it reads them; the relay protocol allows 4 MiB in flight. */
        const val BODY_WINDOW = 4L * 1024 * 1024
    }
}

/** Answers every request of a relay-backed client from its tunnel instead of the network. */
class RelayInterceptor(private val tunnel: RelayTunnel) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response =
        tunnel.execute(chain.call(), chain.request(), chain.readTimeoutMillis().toLong())
}

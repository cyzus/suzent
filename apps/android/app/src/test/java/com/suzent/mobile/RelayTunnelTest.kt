package com.suzent.mobile

import java.math.BigInteger
import java.security.AlgorithmParameters
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPrivateKeySpec
import java.util.Base64
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** The phone side of the relay route against a Kotlin stand-in for the desktop's E2E endpoint. */
class RelayTunnelTest {
    private val vectors = JSONObject(requireNotNull(javaClass.classLoader?.getResourceAsStream("relay-e2e-vectors.json"))
        .bufferedReader().use { it.readText() })
    private val channel = vectors.getString("channel_token")
    private fun hex(value: String) = ByteArray(value.length / 2) { value.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
    private val staticPublic = hex(vectors.getString("desktop_static_public"))
    private val staticPrivate = KeyFactory.getInstance("EC").generatePrivate(ECPrivateKeySpec(
        BigInteger(vectors.getString("desktop_static_private"), 16),
        AlgorithmParameters.getInstance("EC").apply { init(ECGenParameterSpec("secp256r1")) }.getParameterSpec(ECParameterSpec::class.java)))

    private fun ecdh(peer: ByteArray, secret: java.security.PrivateKey) =
        KeyAgreement.getInstance("ECDH").apply { init(secret); doPhase(RelayCrypto.decode(peer), true) }.generateSecret()

    /** Answers the handshake, then serves hreq/wopen frames like the desktop's tunnel. */
    private inner class Desktop(private val forge: Boolean = false, private val stall: Boolean = false) : WebSocketListener() {
        private var session: RelaySession? = null
        val requests = mutableListOf<JSONObject>()
        val cancelled = CountDownLatch(1)
        private val bodies = mutableMapOf<String, java.io.ByteArrayOutputStream>()

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            val current = session
            if (current == null) {
                val phone = bytes.toByteArray()
                val ephemeral = RelayCrypto.newEphemeral()
                val mine = RelayCrypto.encode(ephemeral.public)
                val sha = MessageDigest.getInstance("SHA-256")
                val transcript = sha.digest("suzent-e2e/1".toByteArray() + MessageDigest.getInstance("SHA-256").digest(channel.toByteArray()) + staticPublic + phone + mine)
                val keys = RelayCrypto.hkdf(transcript, ecdh(phone, staticPrivate) + ecdh(phone, ephemeral.private), "suzent-e2e/1 keys".toByteArray(), 96)
                val tag = RelayCrypto.aead(Cipher.ENCRYPT_MODE, keys.copyOfRange(0, 32), 0, ByteArray(0), transcript)
                session = RelaySession(keys.copyOfRange(64, 96), keys.copyOfRange(32, 64))
                webSocket.send((mine + tag).toByteString())
                return
            }
            val plaintext = current.decrypt(bytes.toByteArray())
            fun reply(json: JSONObject) = webSocket.send(current.encrypt(byteArrayOf(0) + json.toString().toByteArray()).toByteString())
            if (plaintext[0].toInt() == 1) {
                val length = plaintext[2].toInt() and 0xff
                val bodyId = String(plaintext, 3, length)
                val payload = plaintext.copyOfRange(3 + length, plaintext.size)
                bodies.getOrPut(bodyId) { java.io.ByteArrayOutputStream() }.write(payload)
                reply(JSONObject().put("t", "hack").put("id", bodyId).put("n", payload.size))
                return
            }
            val frame = JSONObject(String(plaintext, 1, plaintext.size - 1))
            requests += frame
            val id = frame.getString("id")
            fun binary(kind: Int, payload: ByteArray) = webSocket.send(current.encrypt(byteArrayOf(1, kind.toByte(), id.length.toByte()) + id.toByteArray() + payload).toByteString())
            when (frame.getString("t")) {
                "hcancel" -> cancelled.countDown()
                "hreqend" -> {
                    reply(JSONObject().put("t", "hres").put("id", id).put("status", 200).put("headers", JSONObject()))
                    binary(1, "received ${bodies[id]?.size() ?: 0}".toByteArray())
                    reply(JSONObject().put("t", "hend").put("id", id))
                }
                "hreq" -> {
                    if (stall || frame.optBoolean("stream")) return
                    if (forge) { webSocket.send(ByteArray(40).toByteString()); return }
                    reply(JSONObject().put("t", "hres").put("id", id).put("status", 200)
                        .put("headers", JSONObject().put("content-type", "application/json").put("set-cookie", org.json.JSONArray(listOf("a=1", "b=2")))))
                    val body = JSONObject().put("path", frame.getString("path")).put("method", frame.getString("method"))
                        .put("auth", frame.getJSONObject("headers").optString("authorization"))
                        .put("body", frame.optString("b").let { if (it.isEmpty()) "" else String(Base64.getDecoder().decode(it)) })
                    val bytes = body.toString().toByteArray()
                    binary(1, bytes.copyOfRange(0, 5))
                    binary(1, bytes.copyOfRange(5, bytes.size))
                    reply(JSONObject().put("t", "hend").put("id", id))
                }
                "wopen" -> {
                    reply(JSONObject().put("t", "wopened").put("id", id))
                    binary(4, "hello ${frame.getString("path")}".toByteArray())
                }
            }
        }
    }

    private fun route(server: MockWebServer) = RelayRoute(server.url("/").toString().removeSuffix("/"), channel,
        Base64.getUrlEncoder().withoutPadding().encodeToString(staticPublic))

    private fun tunnelClient(server: MockWebServer): Pair<RelayTunnel, OkHttpClient> {
        val tunnel = RelayTunnel(route(server), OkHttpClient())
        return tunnel to OkHttpClient.Builder().addInterceptor(RelayInterceptor(tunnel)).build()
    }

    @Test(timeout = 10000) fun requestsAndSocketsTravelEncrypted() {
        val server = MockWebServer()
        val desktop = Desktop()
        server.enqueue(MockResponse().withWebSocketUpgrade(desktop))
        server.start()
        val (tunnel, http) = tunnelClient(server)
        try {
            val request = Request.Builder().url(RelayRoute.placeholder.resolve("mobile/client/send?chat_id=a%20b")!!)
                .header("Authorization", "Bearer paired-token")
                .post("""{"message":"hi"}""".toRequestBody("application/json".toMediaType())).build()
            http.newCall(request).execute().use { response ->
                assertEquals(200, response.code)
                assertEquals(listOf("a=1", "b=2"), response.headers("set-cookie"))
                val body = JSONObject(response.body!!.string())
                assertEquals("/mobile/client/send?chat_id=a%20b", body.getString("path"))
                assertEquals("POST", body.getString("method"))
                assertEquals("Bearer paired-token", body.getString("auth"))
                assertEquals("""{"message":"hi"}""", body.getString("body"))
            }
            assertEquals("/c/$channel/__suzent_e2e__", server.takeRequest(2, TimeUnit.SECONDS)!!.path)

            val received = CountDownLatch(1)
            var greeting = ""
            val socket = tunnel.webSocket(Request.Builder().url(RelayRoute.placeholder.resolve("ws/node")!!).build(), object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) { greeting = text; received.countDown() }
            })
            assertTrue(received.await(3, TimeUnit.SECONDS))
            assertEquals("hello /ws/node", greeting)
            socket.close(1000, null)
        } finally { tunnel.close(); server.shutdown() }
    }

    @Test(timeout = 30000) fun largeBodiesStreamPacedByTheDesktop() {
        val server = MockWebServer()
        val desktop = Desktop()
        server.enqueue(MockResponse().withWebSocketUpgrade(desktop))
        server.start()
        val (tunnel, http) = tunnelClient(server)
        try {
            val body = ByteArray(9 * 1024 * 1024) { it.toByte() }
            val request = Request.Builder().url(RelayRoute.placeholder.resolve("mobile/client/upload")!!)
                .post(body.toRequestBody("application/octet-stream".toMediaType())).build()
            http.newCall(request).execute().use { response ->
                assertEquals(200, response.code)
                assertEquals("received ${body.size}", response.body!!.string())
            }
            val sent = desktop.requests.first()
            assertTrue(sent.getBoolean("stream"))
            assertFalse(sent.has("b"))
        } finally { tunnel.close(); server.shutdown() }
    }

    @Test(timeout = 10000) fun stalledRequestsTimeOutAndCancel() {
        val server = MockWebServer()
        val desktop = Desktop(stall = true)
        server.enqueue(MockResponse().withWebSocketUpgrade(desktop))
        server.start()
        val tunnel = RelayTunnel(route(server), OkHttpClient())
        val http = OkHttpClient.Builder().readTimeout(500, TimeUnit.MILLISECONDS).addInterceptor(RelayInterceptor(tunnel)).build()
        try {
            assertThrows(java.net.SocketTimeoutException::class.java) {
                http.newCall(Request.Builder().url(RelayRoute.placeholder.resolve("mobile/capabilities")!!).build()).execute()
            }
            assertTrue(desktop.cancelled.await(2, TimeUnit.SECONDS))
        } finally { tunnel.close(); server.shutdown() }
    }

    @Test(timeout = 10000) fun relayForgeryFailsTheRequest() {
        val server = MockWebServer()
        server.enqueue(MockResponse().withWebSocketUpgrade(Desktop(forge = true)))
        server.start()
        val (tunnel, http) = tunnelClient(server)
        try {
            assertThrows(java.io.IOException::class.java) {
                http.newCall(Request.Builder().url(RelayRoute.placeholder.resolve("mobile/capabilities")!!).build()).execute()
            }
        } finally { tunnel.close(); server.shutdown() }
    }

    @Test fun relayClientsOnlyUseThePlaceholder() {
        val route = RelayRoute("https://relay.example", "c".repeat(43), Base64.getUrlEncoder().withoutPadding().encodeToString(staticPublic))
        assertThrows(IllegalArgumentException::class.java) {
            BackendClient(Backend.parse("https://desk.example", false), "token", relay = route)
        }
    }

    @Test fun routeParsingIsStrict() {
        val good = JSONObject().put("version", 1).put("url", "https://relay.example").put("channel", "c".repeat(43))
            .put("key", Base64.getUrlEncoder().withoutPadding().encodeToString(staticPublic))
        assertNotNull(RelayRoute.parse(good))
        assertEquals("https://relay.example/c/${"c".repeat(43)}/__suzent_e2e__", RelayRoute.parse(good)!!.socketUrl.toString())
        assertNull(RelayRoute.parse(JSONObject(good.toString()).put("version", 2)))
        assertNull(RelayRoute.parse(JSONObject(good.toString()).put("url", "http://relay.example")))
        assertNotNull(RelayRoute.parse(JSONObject(good.toString()).put("url", "http://relay.example"), allowHttp = true))
        assertNull(RelayRoute.parse(JSONObject(good.toString()).put("channel", "short")))
        assertNull(RelayRoute.parse(JSONObject(good.toString()).put("key", "AAAA")))
        assertNull(RelayRoute.parse(null))
    }

    @Test fun connectionsAndInvitationsKeepTheRoute() {
        val route = RelayRoute("https://relay.example", "c".repeat(43), Base64.getUrlEncoder().withoutPadding().encodeToString(staticPublic))
        val connection = Connection("https://desk.example/", "token", clientProtocol = 1, relay = route)
        assertEquals(connection, parseConnection(JSONObject(connection.json().toString())))
        val qr = JSONObject().put("type", "suzent.mobile").put("pairing_protocol", 1)
            .put("origin", "https://desktop.example").put("pairing_id", "a".repeat(32))
            .put("invitation", "b".repeat(43)).put("expires_at", 2000).put("relay", route.json())
        assertEquals(route, PairingInvitation.parse(qr.toString(), now = 1000.0).relay)
    }
}

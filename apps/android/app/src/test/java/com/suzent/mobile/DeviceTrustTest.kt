package com.suzent.mobile

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.security.cert.CertificateFactory
import java.security.cert.CertPathValidator
import java.security.cert.PKIXParameters
import java.security.cert.TrustAnchor
import java.security.cert.X509Certificate
import java.util.Base64
import java.util.Date

class DeviceTrustTest {
    private fun fixture(): JSONObject = JSONObject(javaClass.classLoader!!.getResource("tls-fixture.json")!!.readText())

    @Test fun onlyThePairedAuthorityValidatesTheServer() {
        val fixture = fixture()
        val device = DeviceTrust.parse(fixture.getJSONObject("trust"))
        val factory = CertificateFactory.getInstance("X.509")
        fun certificate(field: String) = factory.generateCertificate(Base64.getDecoder().decode(fixture.getString(field)).inputStream()) as X509Certificate
        fun validate(field: String, authority: X509Certificate) {
            val parameters = PKIXParameters(setOf(TrustAnchor(authority, null))).apply {
                isRevocationEnabled = false
                date = Date(1893456000000)
            }
            CertPathValidator.getInstance("PKIX").validate(factory.generateCertPath(listOf(certificate(field))), parameters)
        }
        validate("leaf", device.certificate())
        for ((leaf, ca) in listOf("expired" to device.certificate(), "leaf" to certificate("wrong_ca"))) {
            try { validate(leaf, ca); fail("Invalid server identity accepted") }
            catch (_: java.security.cert.CertPathValidatorException) { }
        }
        val tampered = fixture.getJSONObject("trust").put("fingerprint", "0".repeat(64))
        try { DeviceTrust.parse(tampered); fail("Tampered fingerprint accepted") }
        catch (_: IllegalArgumentException) { }
    }

    @Test fun secureInvitationsNeverPermitHttpFallback() {
        val invitation = JSONObject().put("type", "suzent.mobile").put("pairing_protocol", 2)
            .put("origin", "https://127.0.0.1:25443").put("pairing_id", "a".repeat(32))
            .put("invitation", "b".repeat(43)).put("expires_at", 2000)
            .put("tls", fixture().getJSONObject("trust"))
        assertNotNull(PairingInvitation.parse(invitation.toString(), now = 1000.0).tls)
        invitation.put("origins", org.json.JSONArray().put("http://127.0.0.1:25443"))
        try { PairingInvitation.parse(invitation.toString(), allowHttp = true, now = 1000.0); fail("HTTP downgrade accepted") }
        catch (_: PairingFailure) { }
    }
    @Test fun nativeClientConnectsToTheLocalTlsFixture() = kotlinx.coroutines.runBlocking {
        val path = System.getenv("SUZENT_TLS_FIXTURE")
        org.junit.Assume.assumeTrue(path != null)
        val fixture = JSONObject(java.io.File(path!!).readText())
        val backend = Backend.parse(fixture.getString("origin"))
        val client = BackendClient(backend, "", deviceTrust = DeviceTrust.parse(fixture.getJSONObject("tls")))
        try {
            client.capabilities()
            client.observe("fixture") { }
            val message = kotlinx.coroutines.CompletableDeferred<String>()
            val socket = client.node(object : okhttp3.WebSocketListener() {
                override fun onMessage(webSocket: okhttp3.WebSocket, text: String) { message.complete(text) }
                override fun onFailure(webSocket: okhttp3.WebSocket, error: Throwable, response: okhttp3.Response?) { message.completeExceptionally(error) }
            })
            try { assertEquals("tls-ok", kotlinx.coroutines.withTimeout(5000) { message.await() }) }
            finally { socket.cancel() }
        } finally { client.close() }
        val untrusted = BackendClient(backend, "", probeOnly = true)
        try { untrusted.capabilities(); fail("Untrusted local certificate accepted") }
        catch (_: javax.net.ssl.SSLHandshakeException) { }
        finally { untrusted.close() }
    }

}

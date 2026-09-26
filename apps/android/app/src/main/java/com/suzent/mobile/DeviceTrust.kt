package com.suzent.mobile

import java.security.KeyStore
import java.security.MessageDigest
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.Base64
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager
import okhttp3.OkHttpClient
import org.json.JSONObject

/** A QR-provided CA used only by the client for the paired desktop. */
data class DeviceTrust(val version: Int, val caCertificate: String, val fingerprint: String) {
    fun certificate(): X509Certificate {
        require(version == 1)
        val der = Base64.getDecoder().decode(caCertificate)
        require(der.size <= 2048)
        val digest = MessageDigest.getInstance("SHA-256").digest(der)
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
        require(digest == fingerprint)
        val certificate = CertificateFactory.getInstance("X.509")
            .generateCertificate(der.inputStream()) as X509Certificate
        require(certificate.basicConstraints >= 0)
        return certificate
    }

    fun configure(builder: OkHttpClient.Builder): OkHttpClient.Builder {
        val store = KeyStore.getInstance(KeyStore.getDefaultType()).apply {
            load(null)
            setCertificateEntry("paired-desktop", certificate())
        }
        val factory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).apply { init(store) }
        val trustManager = factory.trustManagers.single() as X509TrustManager
        val context = SSLContext.getInstance("TLS").apply { init(null, arrayOf(trustManager), null) }
        // OkHttp keeps its standard hostname verifier; no system roots are added here.
        return builder.sslSocketFactory(context.socketFactory, trustManager)
    }

    fun json(): JSONObject = JSONObject().put("version", version)
        .put("ca_certificate", caCertificate).put("fingerprint", fingerprint)

    companion object {
        fun parse(json: JSONObject): DeviceTrust = DeviceTrust(json.getInt("version"),
            json.getString("ca_certificate"), json.getString("fingerprint")).also { it.certificate() }
    }
}

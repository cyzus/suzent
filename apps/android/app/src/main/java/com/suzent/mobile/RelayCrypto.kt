package com.suzent.mobile

import java.math.BigInteger
import java.nio.ByteBuffer
import java.security.AlgorithmParameters
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.PublicKey
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPublicKeySpec
import javax.crypto.AEADBadTagException
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/** A handshake or message on the relay route that must end the session. */
class RelayCryptoFailure(message: String) : java.io.IOException(message)

/**
 * `suzent-e2e/1`: the phone's half of the Noise-NK-style handshake with the desktop's
 * static relay key, then AES-256-GCM with per-direction counters. Spec and vectors:
 * docs/08-developing/protocols/relay.md and packages/mobile-contract/relay-e2e-vectors.json.
 */
object RelayCrypto {
    private val protocol = "suzent-e2e/1".toByteArray()
    private const val POINT = 65
    private const val TAG = 16

    private val params: ECParameterSpec by lazy {
        AlgorithmParameters.getInstance("EC").apply { init(ECGenParameterSpec("secp256r1")) }
            .getParameterSpec(ECParameterSpec::class.java)
    }

    fun newEphemeral(): KeyPair = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()

    fun encode(key: PublicKey): ByteArray {
        val point = (key as ECPublicKey).w
        return byteArrayOf(4) + unsigned32(point.affineX) + unsigned32(point.affineY)
    }

    fun decode(point: ByteArray): PublicKey {
        if (point.size != POINT || point[0] != 4.toByte()) throw RelayCryptoFailure("Expected an uncompressed P-256 point")
        return try {
            val spec = ECPublicKeySpec(ECPoint(BigInteger(1, point.copyOfRange(1, 33)), BigInteger(1, point.copyOfRange(33, 65))), params)
            KeyFactory.getInstance("EC").generatePublic(spec)
        } catch (_: Exception) { throw RelayCryptoFailure("Not a point on P-256") }
    }

    private fun unsigned32(value: BigInteger): ByteArray {
        val raw = value.toByteArray().dropWhile { it == 0.toByte() }.toByteArray()
        require(raw.size <= 32)
        return ByteArray(32 - raw.size) + raw
    }

    private fun ecdh(secret: PrivateKey, peer: PublicKey): ByteArray =
        KeyAgreement.getInstance("ECDH").apply { init(secret); doPhase(peer, true) }.generateSecret()

    private fun hmac(key: ByteArray, vararg parts: ByteArray): ByteArray =
        Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(key, "HmacSHA256")); parts.forEach { update(it) } }.doFinal()

    internal fun hkdf(salt: ByteArray, ikm: ByteArray, info: ByteArray, length: Int): ByteArray {
        val prk = hmac(salt, ikm)
        val out = ByteArray(length)
        var block = ByteArray(0)
        var offset = 0
        var counter = 1
        while (offset < length) {
            block = hmac(prk, block, info, byteArrayOf(counter.toByte()))
            val take = minOf(block.size, length - offset)
            System.arraycopy(block, 0, out, offset, take)
            offset += take
            counter++
        }
        return out
    }

    internal fun nonce(counter: Long): ByteArray = ByteBuffer.allocate(12).putInt(0).putLong(counter).array()

    internal fun aead(mode: Int, key: ByteArray, counter: Long, data: ByteArray, aad: ByteArray? = null): ByteArray =
        Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(mode, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce(counter)))
            if (aad != null) updateAAD(aad)
        }.doFinal(data)

    /** Checks the desktop's reply to [ephemeral] and opens the session. */
    fun finish(ephemeral: KeyPair, staticKey: ByteArray, channel: String, reply: ByteArray): RelaySession {
        if (reply.size != POINT + TAG) throw RelayCryptoFailure("Malformed handshake reply")
        val desktopEphemeral = reply.copyOfRange(0, POINT)
        val sha = MessageDigest.getInstance("SHA-256")
        val transcript = sha.digest(protocol + MessageDigest.getInstance("SHA-256").digest(channel.toByteArray()) +
            staticKey + encode(ephemeral.public) + desktopEphemeral)
        val ikm = ecdh(ephemeral.private, decode(staticKey)) + ecdh(ephemeral.private, decode(desktopEphemeral))
        val keys = hkdf(transcript, ikm, protocol + " keys".toByteArray(), 96)
        try { aead(Cipher.DECRYPT_MODE, keys.copyOfRange(0, 32), 0, reply.copyOfRange(POINT, reply.size), transcript) }
        catch (_: AEADBadTagException) { throw RelayCryptoFailure("The desktop could not prove its key") }
        return RelaySession(keys.copyOfRange(32, 64), keys.copyOfRange(64, 96))
    }
}

/** One direction pair of AES-256-GCM keys. Each direction's counter must match the desktop's. */
class RelaySession(private val sendKey: ByteArray, private val receiveKey: ByteArray) {
    private var sent = 0L
    private var received = 0L

    @Synchronized fun encrypt(plaintext: ByteArray): ByteArray =
        RelayCrypto.aead(Cipher.ENCRYPT_MODE, sendKey, sent, plaintext).also { sent++ }

    @Synchronized fun decrypt(ciphertext: ByteArray): ByteArray {
        val plaintext = try { RelayCrypto.aead(Cipher.DECRYPT_MODE, receiveKey, received, ciphertext) }
        catch (_: AEADBadTagException) { throw RelayCryptoFailure("Message failed authentication") }
        received++
        return plaintext
    }
}

package com.suzent.mobile

import java.math.BigInteger
import java.security.AlgorithmParameters
import java.security.KeyFactory
import java.security.KeyPair
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPrivateKeySpec
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class RelayCryptoTest {
    private val vectors = JSONObject(requireNotNull(javaClass.classLoader?.getResourceAsStream("relay-e2e-vectors.json"))
        .bufferedReader().use { it.readText() })

    private fun hex(value: String) = ByteArray(value.length / 2) { value.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

    private fun phoneEphemeral(): KeyPair {
        val params = AlgorithmParameters.getInstance("EC").apply { init(ECGenParameterSpec("secp256r1")) }
            .getParameterSpec(ECParameterSpec::class.java)
        val secret = KeyFactory.getInstance("EC").generatePrivate(ECPrivateKeySpec(BigInteger(vectors.getString("phone_ephemeral_private"), 16), params))
        return KeyPair(RelayCrypto.decode(hex(vectors.getString("handshake_message_1"))), secret)
    }

    private fun session(): RelaySession = RelayCrypto.finish(phoneEphemeral(), hex(vectors.getString("desktop_static_public")),
        vectors.getString("channel_token"), hex(vectors.getString("handshake_message_2")))

    @Test fun pointsRoundTrip() {
        val point = hex(vectors.getString("handshake_message_1"))
        assertArrayEquals(point, RelayCrypto.encode(RelayCrypto.decode(point)))
        assertEquals(65, RelayCrypto.encode(RelayCrypto.newEphemeral().public).size)
    }

    @Test fun sharedVectors() {
        val phone = session()
        val desktop = RelaySession(hex(vectors.getString("desktop_to_phone_key")), hex(vectors.getString("phone_to_desktop_key")))
        val messages = vectors.getJSONArray("messages")
        for (index in 0 until messages.length()) {
            val message = messages.getJSONObject(index)
            val plaintext = hex(message.getString("plaintext"))
            val ciphertext = hex(message.getString("ciphertext"))
            if (message.getString("direction") == "phone_to_desktop") {
                assertArrayEquals("message $index", ciphertext, phone.encrypt(plaintext))
                assertArrayEquals(plaintext, desktop.decrypt(ciphertext))
            } else {
                assertArrayEquals("message $index", ciphertext, desktop.encrypt(plaintext))
                assertArrayEquals(plaintext, phone.decrypt(ciphertext))
            }
        }
    }

    @Test fun rejectsWrongKeyChannelAndTampering() {
        val reply = hex(vectors.getString("handshake_message_2"))
        val static = hex(vectors.getString("desktop_static_public"))
        assertThrows(RelayCryptoFailure::class.java) {
            RelayCrypto.finish(phoneEphemeral(), static, "another-channel-bbbbbbbbbbbbbbbb", reply)
        }
        val tampered = reply.copyOf().also { it[it.size - 1] = (it[it.size - 1].toInt() xor 1).toByte() }
        assertThrows(RelayCryptoFailure::class.java) {
            RelayCrypto.finish(phoneEphemeral(), static, vectors.getString("channel_token"), tampered)
        }
        assertThrows(RelayCryptoFailure::class.java) { RelayCrypto.decode(ByteArray(65)) }
    }

    @Test fun replayFails() {
        val phone = session()
        val desktop = RelaySession(hex(vectors.getString("desktop_to_phone_key")), hex(vectors.getString("phone_to_desktop_key")))
        val first = phone.encrypt("one".toByteArray())
        desktop.decrypt(first)
        assertThrows(RelayCryptoFailure::class.java) { desktop.decrypt(first) }
    }
}

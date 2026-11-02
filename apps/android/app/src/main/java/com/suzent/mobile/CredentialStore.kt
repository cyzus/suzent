package com.suzent.mobile

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject

data class Connection(val origin: String, val hostToken: String, val nodeToken: String = "", val clientProtocol: Int = 0, val previousToken: String = "", val previousOrigin: String = "", val origins: List<String> = emptyList(), val tls: DeviceTrust? = null, val previousTLS: DeviceTrust? = null, val previousOrigins: List<String> = emptyList())

class CredentialStore(context: Context) {
    private val preferences = context.getSharedPreferences("secure_connection", Context.MODE_PRIVATE)
    private val alias = "com.suzent.mobile.connection"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build())
        }.generateKey()
    }

    fun save(value: SavedDesktops) {
        if (value.desktops.isEmpty()) { clear(); return }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val encrypted = cipher.doFinal(value.json().toString().toByteArray(Charsets.UTF_8))
        check(preferences.edit().putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString("data", Base64.encodeToString(encrypted, Base64.NO_WRAP)).commit())
    }

    /** A record saved by a single-connection version comes back as one desktop and is rewritten in the new shape. */
    fun load(): SavedDesktops {
        val encoded = preferences.getString("data", null) ?: return SavedDesktops()
        val iv = requireNotNull(preferences.getString("iv", null))
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
        }
        val json = JSONObject(String(cipher.doFinal(Base64.decode(encoded, Base64.NO_WRAP)), Charsets.UTF_8))
        return SavedDesktops.parse(json).also { if (!json.has("desktops")) save(it) }
    }

    fun clear() { check(preferences.edit().clear().commit()) }
}

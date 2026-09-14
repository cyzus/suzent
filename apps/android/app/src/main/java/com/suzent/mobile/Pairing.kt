package com.suzent.mobile

import org.json.JSONObject

class PairingFailure(val reason: Reason) : Exception() {
    enum class Reason { INVALID, INCOMPATIBLE, EXPIRED, DENIED }
}

data class ClientPermissions(val chatIds: List<String>, val allChats: Boolean,
    val createChats: Boolean, val send: Boolean, val stop: Boolean) {
    companion object {
        fun parse(json: JSONObject): ClientPermissions {
            val ids = json.getJSONArray("chat_ids")
            return ClientPermissions((0 until ids.length()).map { ids.getString(it) },
                json.getBoolean("all_chats"), json.getBoolean("create_chats"),
                json.getBoolean("send"), json.getBoolean("stop"))
        }
    }
}

data class ClientDevice(val id: String, val name: String, val permissions: ClientPermissions) {
    companion object {
        fun parse(json: JSONObject) = ClientDevice(json.getString("device_id"),
            json.getString("display_name"), ClientPermissions.parse(json.getJSONObject("permissions")))
    }
}

fun validateMobileCapabilities(json: JSONObject, pairing: Boolean = false) {
    val streams = json.getJSONArray("stream_protocols")
    if (json.opt("client_protocol") != 1 || (pairing && json.opt("pairing_protocol") != 1) ||
        !(0 until streams.length()).any { streams.opt(it) == 1 }) {
        throw PairingFailure(PairingFailure.Reason.INCOMPATIBLE)
    }
}

data class PairingInvitation(val origin: String, val id: String, val secret: String, val expiresAt: Double) {
    companion object {
        fun parse(text: String, allowHttp: Boolean = false, now: Double = System.currentTimeMillis() / 1000.0): PairingInvitation {
            try {
                require(text.toByteArray().size <= 4096)
                val json = JSONObject(text)
                if (json.getString("type") != "suzent.mobile" || json.opt("pairing_protocol") != 1)
                    throw PairingFailure(PairingFailure.Reason.INCOMPATIBLE)
                val expiry = json.getDouble("expires_at")
                require(expiry.isFinite())
                if (expiry <= now) throw PairingFailure(PairingFailure.Reason.EXPIRED)
                val origin = json.getString("origin")
                Backend.parse(origin, allowHttp)
                val id = json.getString("pairing_id")
                val secret = json.getString("invitation")
                require(id.matches(Regex("[a-f0-9]{32}")) && secret.matches(Regex("[A-Za-z0-9_-]{40,64}")))
                return PairingInvitation(origin, id, secret, expiry)
            } catch (failure: PairingFailure) { throw failure }
            catch (_: Exception) { throw PairingFailure(PairingFailure.Reason.INVALID) }
        }
    }
}

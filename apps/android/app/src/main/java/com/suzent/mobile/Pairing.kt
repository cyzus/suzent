package com.suzent.mobile

import org.json.JSONObject
import kotlinx.coroutines.ensureActive

class PairingFailure(val reason: Reason) : Exception() {
    enum class Reason { INVALID, INCOMPATIBLE, EXPIRED, DENIED, UNREACHABLE }
}

data class ClientPermissions(val chatIds: List<String>, val allChats: Boolean,
    val createChats: Boolean, val send: Boolean, val stop: Boolean, val approveTools: Boolean = false) {
    companion object {
        fun parse(json: JSONObject): ClientPermissions {
            val ids = json.getJSONArray("chat_ids")
            return ClientPermissions((0 until ids.length()).map { ids.getString(it) },
                json.getBoolean("all_chats"), json.getBoolean("create_chats"),
                json.getBoolean("send"), json.getBoolean("stop"), json.optBoolean("approve_tools"))
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

data class PairingInvitation(val origin: String, val id: String, val secret: String, val expiresAt: Double, val origins: List<String> = listOf(origin), val phoneConfirmation: Boolean = false) {
    companion object {
        fun parse(text: String, allowHttp: Boolean = false, now: Double = System.currentTimeMillis() / 1000.0): PairingInvitation {
            try {
                require(text.toByteArray().size <= 4096)
                val json = JSONObject(text)
                if (json.getString("type") != "suzent.mobile" || json.opt("pairing_protocol") != 1)
                    throw PairingFailure(PairingFailure.Reason.INCOMPATIBLE)
                if (json.has("approval") && json.getString("approval") != "phone")
                    throw PairingFailure(PairingFailure.Reason.INCOMPATIBLE)
                val expiry = json.getDouble("expires_at")
                require(expiry.isFinite())
                if (expiry <= now) throw PairingFailure(PairingFailure.Reason.EXPIRED)
                val origin = json.getString("origin")
                val additional = if (json.has("origins")) json.getJSONArray("origins") else org.json.JSONArray()
                require(additional.length() <= 6)
                val candidates = (listOf(origin) + (0 until additional.length()).map { additional.getString(it) }).distinct()
                require(candidates.size <= 6)
                candidates.forEach { Backend.parse(it, allowHttp = true) }
                val usable = candidates.filter { allowHttp || Backend.parse(it, allowHttp = true).origin.isHttps }
                require(usable.isNotEmpty())
                val id = json.getString("pairing_id")
                val secret = json.getString("invitation")
                require(id.matches(Regex("[a-f0-9]{32}")) && secret.matches(Regex("[A-Za-z0-9_-]{40,64}")))
                return PairingInvitation(usable.first(), id, secret, expiry, usable, json.optString("approval") == "phone")
            } catch (failure: PairingFailure) { throw failure }
            catch (_: Exception) { throw PairingFailure(PairingFailure.Reason.INVALID) }
        }
    }
}


suspend fun <T> resolvePairingInvitation(invitation: PairingInvitation, probe: suspend (String) -> T): Pair<PairingInvitation, T> {
    for (origin in invitation.origins) {
        kotlinx.coroutines.currentCoroutineContext().ensureActive()
        if (invitation.expiresAt <= System.currentTimeMillis() / 1000.0) throw PairingFailure(PairingFailure.Reason.EXPIRED)
        try {
            val value = probe(origin)
            kotlinx.coroutines.currentCoroutineContext().ensureActive()
            return invitation.copy(origin = origin) to value
        } catch (failure: kotlinx.coroutines.CancellationException) { throw failure }
        catch (_: Exception) { }
    }
    throw PairingFailure(PairingFailure.Reason.UNREACHABLE)
}


data class PairingPreview(val desktopName: String, val permissions: ClientPermissions) {
    companion object {
        fun parse(json: JSONObject, invitation: PairingInvitation): PairingPreview {
            require(json.getString("pairing_id") == invitation.id && json.getString("approval") == "phone")
            require(json.getDouble("expires_at") > System.currentTimeMillis() / 1000.0)
            return PairingPreview(json.getString("desktop_name"), ClientPermissions.parse(json.getJSONObject("permissions")))
        }
    }
}

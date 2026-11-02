package com.suzent.mobile

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class SavedDesktop(val id: String, val name: String, val connection: Connection) {
    /** Same desktop as the invitation: its device CA when both have one, otherwise a shared address. */
    fun matches(invitation: PairingInvitation): Boolean {
        val trust = connection.tls
        if (trust != null && invitation.tls != null) return trust.fingerprint == invitation.tls.fingerprint
        val known = (listOf(connection.origin) + connection.origins).mapNotNull(::normalizedOrigin).toSet()
        return (listOf(invitation.origin) + invitation.origins).mapNotNull(::normalizedOrigin).any { it in known }
    }

    fun json(): JSONObject = JSONObject().put("id", id).put("name", name).put("connection", connection.json())

    companion object {
        fun create(name: String, connection: Connection) = SavedDesktop(UUID.randomUUID().toString(), name, connection)
        fun parse(json: JSONObject) = SavedDesktop(json.getString("id"), json.getString("name"), parseConnection(json.getJSONObject("connection")))
    }
}

data class SavedDesktops(val activeId: String? = null, val desktops: List<SavedDesktop> = emptyList()) {
    val active: SavedDesktop? get() = desktops.firstOrNull { it.id == activeId }

    fun desktop(id: String): SavedDesktop? = desktops.firstOrNull { it.id == id }
    fun matching(invitation: PairingInvitation): SavedDesktop? = desktops.firstOrNull { it.matches(invitation) }

    /** Replaces the desktop with the same id in place, or appends a new one. */
    fun upserting(desktop: SavedDesktop): SavedDesktops =
        if (desktops.any { it.id == desktop.id }) copy(desktops = desktops.map { if (it.id == desktop.id) desktop else it })
        else copy(desktops = desktops + desktop)

    fun updating(id: String, connection: Connection): SavedDesktops =
        copy(desktops = desktops.map { if (it.id == id) it.copy(connection = connection) else it })

    fun renaming(id: String, name: String): SavedDesktops =
        copy(desktops = desktops.map { if (it.id == id) it.copy(name = name) else it })

    /** Removing the active desktop hands activity to the first one left. */
    fun removing(id: String): SavedDesktops {
        val remaining = desktops.filterNot { it.id == id }
        return SavedDesktops(if (activeId == id || activeId == null) remaining.firstOrNull()?.id else activeId, remaining)
    }

    fun json(): JSONObject = JSONObject().put("version", 1).put("activeId", activeId ?: JSONObject.NULL)
        .put("desktops", JSONArray(desktops.map { it.json() }))

    companion object {
        /** Reads the multi-desktop record, or the single connection saved before there could be several. */
        fun parse(json: JSONObject): SavedDesktops {
            if (!json.has("desktops")) {
                val legacy = parseConnection(json)
                val desktop = SavedDesktop.create(defaultDesktopName(legacy.origin), legacy)
                return SavedDesktops(desktop.id, listOf(desktop))
            }
            val array = json.getJSONArray("desktops")
            val desktops = (0 until array.length()).map { SavedDesktop.parse(array.getJSONObject(it)) }
            val active = json.optString("activeId").takeIf { id -> desktops.any { it.id == id } }
            return SavedDesktops(active ?: desktops.firstOrNull()?.id, desktops)
        }
    }
}

fun defaultDesktopName(origin: String): String = runCatching { Backend.parse(origin, allowHttp = true).origin.host }.getOrDefault(origin)

private val desktopColors = listOf(0xFF0066FFL, 0xFF1D9E75L, 0xFFD85A30L, 0xFF7F77DDL, 0xFFD4537EL, 0xFFBA7517L)

/** Stable for a desktop's lifetime on this phone, so the same desktop always reads as the same colour. */
fun desktopColor(id: String): Long = desktopColors[Math.floorMod(id.hashCode(), desktopColors.size)]

private fun normalizedOrigin(raw: String): String? = runCatching { Backend.parse(raw, allowHttp = true).origin.toString() }.getOrNull()

private fun strings(array: JSONArray?): List<String> = array?.let { (0 until it.length()).map(it::getString) }.orEmpty()

fun Connection.json(): JSONObject = JSONObject().put("origin", origin).put("hostToken", hostToken)
    .put("previousOrigins", JSONArray(previousOrigins))
    .put("origins", JSONArray(origins)).put("tls", tls?.json()).put("previousTLS", previousTLS?.json())
    .put("previousOrigin", previousOrigin).put("previousToken", previousToken).put("clientProtocol", clientProtocol).put("nodeToken", nodeToken)

fun parseConnection(json: JSONObject) = Connection(json.getString("origin"), json.getString("hostToken"), json.optString("nodeToken"),
    json.optInt("clientProtocol"), json.optString("previousToken"), json.optString("previousOrigin"), strings(json.optJSONArray("origins")),
    json.optJSONObject("tls")?.let { DeviceTrust.parse(it) }, json.optJSONObject("previousTLS")?.let { DeviceTrust.parse(it) },
    strings(json.optJSONArray("previousOrigins")))

/** The scheme is noise in a narrow row and pushes the host and port out of view. */
fun displayOrigin(origin: String): String = origin.removePrefix("https://").removePrefix("http://").removeSuffix("/")

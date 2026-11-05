import Foundation
import Testing
@testable import SuzentCore

private func trust(_ fingerprint: String) -> DeviceTrust {
    DeviceTrust(version: 1, caCertificate: "", fingerprint: fingerprint)
}

private func connection(_ origin: String, origins: [String]? = nil, tls: DeviceTrust? = nil, token: String = "t") -> Connection {
    Connection(origins: origins, tls: tls, origin: origin, hostToken: token, clientProtocol: 1)
}

@Test func trustedConnectionsMatchOnlyByFingerprint() {
    let saved = connection("https://10.0.0.2:25314", tls: trust("AB"))
    #expect(saved.matches(tls: trust("ab"), origins: ["https://elsewhere.example"]))
    #expect(!saved.matches(tls: trust("cd"), origins: ["https://10.0.0.2:25314"]))
}

@Test func untrustedConnectionsMatchByNormalizedOrigin() {
    let saved = connection("https://Desktop.Example:443/", origins: ["https://100.64.0.1:25314"])
    #expect(saved.matches(tls: nil, origins: ["https://desktop.example"]))
    #expect(saved.matches(tls: trust("ab"), origins: ["https://other.example", "https://100.64.0.1:25314"]))
    #expect(!saved.matches(tls: nil, origins: ["http://desktop.example", "https://100.64.0.1:25315"]))
    #expect(normalizedOrigin("not a url") == nil)
}

@Test func matchingFindsInvitationTarget() throws {
    let text = String(decoding: try JSONSerialization.data(withJSONObject: [
        "type": "suzent.mobile", "pairing_protocol": 1, "origin": "https://b.example",
        "origins": ["https://b.example", "https://lan.example:25314"],
        "pairing_id": String(repeating: "a", count: 32), "invitation": String(repeating: "b", count: 43), "expires_at": 2000]), as: UTF8.self)
    let invitation = try PairingInvitation.parse(text, now: Date(timeIntervalSince1970: 1000))
    let list = SavedDesktops(activeId: "a", desktops: [
        SavedDesktop(id: "a", name: "A", connection: connection("https://a.example")),
        SavedDesktop(id: "b", name: "B", connection: connection("https://lan.example:25314"))])
    #expect(list.matching(invitation)?.id == "b")
}

@Test func upsertReplacesByIdAndRemovePicksNextActive() {
    var list = SavedDesktops()
    list.upsert(SavedDesktop(id: "a", name: "A", connection: connection("https://a.example")))
    list.upsert(SavedDesktop(id: "b", name: "B", connection: connection("https://b.example")))
    list.upsert(SavedDesktop(id: "c", name: "C", connection: connection("https://c.example")))
    list.activeId = "b"
    list.upsert(SavedDesktop(id: "b", name: "B2", connection: connection("https://b.example", token: "new")))
    #expect(list.desktops.map(\.id) == ["a", "b", "c"])
    #expect(list.active?.name == "B2" && list.active?.connection.hostToken == "new")
    list.rename("b", to: "  ")
    #expect(list.active?.name == "B2")
    list.remove("c")
    #expect(list.activeId == "b")
    list.remove("b")
    #expect(list.activeId == "a")
    list.remove("a")
    #expect(list.activeId == nil && list.desktops.isEmpty)
}

@Test func legacyConnectionDecodesIntoOneDesktop() throws {
    let legacy = #"{"origin":"https://desktop.example:25314","hostToken":"secret","nodeToken":"node","clientProtocol":1}"#
    let list = try SavedDesktops.decode(Data(legacy.utf8))
    #expect(list.desktops.count == 1)
    #expect(list.active?.name == "desktop.example")
    #expect(list.active?.connection.hostToken == "secret" && list.active?.connection.nodeToken == "node")
    let roundTrip = try SavedDesktops.decode(JSONEncoder().encode(list))
    #expect(roundTrip == list)
    let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(list.active!.connection)) as! [String: Any]
    #expect(Set(encoded.keys) == ["origin", "hostToken", "nodeToken", "clientProtocol"])
}

@Test func desktopColorIsStableAndInPalette() {
    let desktop = SavedDesktop(id: "7B0D7A0E-1C1B-4E7B-9C55-1B1A3C1E4D2F", name: "A", connection: connection("https://a.example"))
    #expect(desktop.color == SavedDesktop(id: desktop.id, name: "B", connection: connection("https://b.example")).color)
    #expect(SavedDesktop.palette.contains(desktop.color))
}

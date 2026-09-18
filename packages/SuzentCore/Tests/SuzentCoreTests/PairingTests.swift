import Foundation
import Testing
@testable import SuzentCore

private func invitation(_ overrides: [String: Any] = [:]) throws -> String {
    var value: [String: Any] = ["type": "suzent.mobile", "pairing_protocol": 1,
                              "origin": "https://desktop.example", "pairing_id": String(repeating: "a", count: 32),
                              "invitation": String(repeating: "b", count: 43), "expires_at": 2000]
    value.merge(overrides) { _, new in new }
    return String(decoding: try JSONSerialization.data(withJSONObject: value), as: UTF8.self)
}

@Test func pairingInvitationValidatesOriginProtocolAndExpiry() throws {
    let now = Date(timeIntervalSince1970: 1000)
    let result = try PairingInvitation.parse(invitation(), now: now)
    #expect(result.origin == "https://desktop.example")
    for invalid: [String: Any] in [["type": "other"], ["pairing_protocol": 2], ["expires_at": 999],
                                 ["pairing_id": "../admin"], ["origin": "https://user:secret@desktop.example"],
                                 ["origin": "http://desktop.example"]] {
        let text = try invitation(invalid)
        #expect(throws: (any Error).self) { try PairingInvitation.parse(text, now: now) }
    }
    let debug = try invitation(["origin": "http://desktop.example"])
    #expect(try PairingInvitation.parse(debug, allowHTTP: true, now: now).origin == "http://desktop.example")
}

@Test func rejectsUnsupportedBackendCapabilities() throws {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let supported = try decoder.decode(MobileCapabilities.self, from: Data(#"{"client_protocol":1,"pairing_protocol":1,"stream_protocols":[1]}"#.utf8))
    try supported.validate()
    let unsupported = try decoder.decode(MobileCapabilities.self, from: Data(#"{"client_protocol":1,"pairing_protocol":1,"stream_protocols":[2]}"#.utf8))
    #expect(throws: PairingError.self) { try unsupported.validate() }
}

@Test func multipleAddressesValidateAndResolve() async throws {
    let mixed = try invitation(["origin": "http://192.168.1.2", "origins": ["http://192.168.1.2", "https://desktop.example"]])
    let release = try PairingInvitation.parse(mixed, now: Date(timeIntervalSince1970: 1000))
    #expect(release.origins == ["https://desktop.example"])
    let invalid = try invitation(["origins": ["https://user:secret@other.example"]])
    #expect(throws: (any Error).self) { try PairingInvitation.parse(invalid, now: Date(timeIntervalSince1970: 1000)) }
    let text = try invitation(["expires_at": Date().timeIntervalSince1970 + 300,
                               "origins": ["https://desktop.example", "https://tailnet.example"]])
    let value = try PairingInvitation.parse(text)
    let selected = try await value.resolving { origin in
        if origin == "https://desktop.example" { throw URLError(.cannotConnectToHost) }
        return "validated preview"
    }
    #expect(selected.invitation.origin == "https://tailnet.example")
    #expect(selected.value == "validated preview")
    do {
        _ = try await value.resolving { _ -> Void in throw URLError(.cannotConnectToHost) }
        Issue.record("Expected all unreachable candidates to fail")
    } catch PairingError.unreachable { }
}


@Test func phoneConfirmationBindsPreviewToInvitation() throws {
    let expiry = Date().timeIntervalSince1970 + 300
    let value = try PairingInvitation.parse(invitation(["approval": "phone", "expires_at": expiry]))
    #expect(value.phoneConfirmation)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let data: [String: Any] = ["pairing_id": value.pairingId, "approval": "phone", "desktop_name": "Test desktop",
                               "expires_at": expiry, "permissions": ["chat_ids": ["one"], "all_chats": false,
                                 "create_chats": false, "send": true, "stop": false]]
    let preview = try decoder.decode(PairingPreview.self, from: JSONSerialization.data(withJSONObject: data))
    try preview.validate(value)
    #expect(preview.permissions.chatIds == ["one"])
    #expect(preview.permissions.send && !preview.permissions.stop)
    #expect(preview.permissions.approveTools != true)
    var wrong = data
    wrong["pairing_id"] = String(repeating: "c", count: 32)
    let other = try decoder.decode(PairingPreview.self, from: JSONSerialization.data(withJSONObject: wrong))
    #expect(throws: PairingError.self) { try other.validate(value) }
}

@Test func repairProofIsBoundToInvitationAndDirection() throws {
    let value = try PairingInvitation.parse(invitation(), now: Date(timeIntervalSince1970: 1000))
    #expect(pairingRepairProof(token: "old-token", invitation: value, side: "phone") == "9e02aadf5f8ce4580dbaab7080c9630d4b87e87aee6622f061023b59523b01be")
    #expect(pairingRepairProof(token: "old-token", invitation: value, side: "desktop") != "9e02aadf5f8ce4580dbaab7080c9630d4b87e87aee6622f061023b59523b01be")
}

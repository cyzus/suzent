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

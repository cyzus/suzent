import Foundation
import Testing
import Security
@testable import SuzentCore

private func tlsFixture() throws -> [String: Any] {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    return try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("mobile-contract/tls-fixture.json"))) as! [String: Any]
}

@Test func deviceTrustRejectsOtherCertificatesAndHostnames() throws {
    let fixture = try tlsFixture()
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let device = try decoder.decode(DeviceTrust.self, from: JSONSerialization.data(withJSONObject: fixture["trust"]!))
    func evaluate(_ field: String, host: String) -> Bool {
        let certificate = SecCertificateCreateWithData(nil, Data(base64Encoded: fixture[field] as! String)! as CFData)!
        var trust: SecTrust?
        SecTrustCreateWithCertificates(certificate, SecPolicyCreateSSL(true, host as CFString), &trust)
        SecTrustSetVerifyDate(trust!, Date(timeIntervalSince1970: 1893456000) as CFDate)
        return device.evaluate(trust!, host: host)
    }
    #expect(evaluate("leaf", host: "127.0.0.1"))
    #expect(!evaluate("leaf", host: "192.168.1.99"))
    #expect(!evaluate("expired", host: "127.0.0.1"))
    #expect(!evaluate("wrong_ca", host: "127.0.0.1"))
}

@Test func secureInvitationCannotDowngradeOrChangeItsFingerprint() throws {
    let fixture = try tlsFixture()
    var value: [String: Any] = ["type": "suzent.mobile", "pairing_protocol": 2,
        "origin": "https://127.0.0.1:25443", "pairing_id": String(repeating: "a", count: 32),
        "invitation": String(repeating: "b", count: 43), "expires_at": 2000, "tls": fixture["trust"]!]
    func parse() throws -> PairingInvitation {
        try PairingInvitation.parse(String(decoding: JSONSerialization.data(withJSONObject: value), as: UTF8.self),
                                    allowHTTP: true, now: Date(timeIntervalSince1970: 1000))
    }
    #expect(try parse().tls != nil)
    value["origin"] = "http://127.0.0.1:25443"
    #expect(throws: (any Error).self) { try parse() }
    value["origin"] = "https://127.0.0.1:25443"
    var bad = fixture["trust"] as! [String: Any]
    bad["fingerprint"] = String(repeating: "0", count: 64)
    value["tls"] = bad
    #expect(throws: (any Error).self) { try parse() }
}

@Test(.enabled(if: ProcessInfo.processInfo.environment["SUZENT_TLS_FIXTURE"] != nil))
func nativeClientUsesDeviceTrustForHTTPStreamAndWebSocket() async throws {
    let path = ProcessInfo.processInfo.environment["SUZENT_TLS_FIXTURE"]!
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let trust = try decoder.decode(DeviceTrust.self, from: JSONSerialization.data(withJSONObject: json["tls"]!))
    let backend = try Backend(json["origin"] as! String)
    let client = try SuzentClient(backend: backend, token: "", deviceTrust: trust)
    defer { client.close() }
    _ = try await client.capabilities()
    try await client.observe("fixture") { _ in }
    let socket = client.nodeSocket()
    socket.resume()
    let message = try await socket.receive()
    if case .string(let value) = message { #expect(value == "tls-ok") }
    else { Issue.record("Unexpected WebSocket frame") }
    socket.cancel(with: .normalClosure, reason: nil)
    let untrusted = try SuzentClient(backend: backend, token: "", probeOnly: true)
    defer { untrusted.close() }
    do { _ = try await untrusted.capabilities(); Issue.record("Untrusted local certificate accepted") }
    catch { }
}

@Test func deviceTrustCannotBeAttachedToPlaintextClient() throws {
    let json = try tlsFixture()
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let trust = try decoder.decode(DeviceTrust.self, from: JSONSerialization.data(withJSONObject: json["trust"]!))
    #expect(throws: (any Error).self) {
        try SuzentClient(backend: Backend("http://127.0.0.1", allowHTTP: true), token: "secret", deviceTrust: trust)
    }
}

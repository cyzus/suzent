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

@Test func fingerprintInvitationRequiresHTTPSAndDefersTheCertificate() throws {
    let fixture = try tlsFixture()
    let fingerprint = (fixture["trust"] as! [String: Any])["fingerprint"] as! String
    let base: [String: Any] = ["type": "suzent.mobile", "pairing_protocol": 3,
        "origin": "https://127.0.0.1:25443", "pairing_id": String(repeating: "a", count: 32),
        "invitation": String(repeating: "b", count: 43), "expires_at": 2000, "tls_fingerprint": fingerprint]
    func parse(_ value: [String: Any]) throws -> PairingInvitation {
        try PairingInvitation.parse(String(decoding: JSONSerialization.data(withJSONObject: value), as: UTF8.self),
                                    allowHTTP: true, now: Date(timeIntervalSince1970: 1000))
    }
    let parsed = try parse(base)
    #expect(parsed.tls == nil && parsed.tlsFingerprint == fingerprint && parsed.secure)
    var bad = [base, base, base, base]
    bad[0]["origins"] = ["http://127.0.0.1:25443"]
    bad[1]["tls_fingerprint"] = String(repeating: "A", count: 64)
    bad[2].removeValue(forKey: "tls_fingerprint")
    bad[3]["pairing_protocol"] = 2
    for value in bad { #expect(throws: (any Error).self) { try parse(value) } }
}

@Test func onlyThePinnedAuthorityIsTakenFromTheChain() throws {
    let fixture = try tlsFixture()
    let trust = fixture["trust"] as! [String: Any]
    let fingerprint = trust["fingerprint"] as! String
    let chain = [Data(base64Encoded: fixture["leaf"] as! String)!, Data(base64Encoded: trust["ca_certificate"] as! String)!]
    #expect(DeviceTrust.fromChain(chain, fingerprint: fingerprint)?.caCertificate == trust["ca_certificate"] as? String)
    #expect(DeviceTrust.fromChain(chain, fingerprint: String(repeating: "0", count: 64)) == nil)
    #expect(DeviceTrust.fromChain([Data(base64Encoded: fixture["wrong_ca"] as! String)!], fingerprint: fingerprint) == nil)
}

@Test(.enabled(if: ProcessInfo.processInfo.environment["SUZENT_TLS_FIXTURE"] != nil))
func fingerprintFetchReadsTheLocalTlsFixtureAuthority() async throws {
    let path = ProcessInfo.processInfo.environment["SUZENT_TLS_FIXTURE"]!
    let json = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: path))) as! [String: Any]
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let expected = try decoder.decode(DeviceTrust.self, from: JSONSerialization.data(withJSONObject: json["tls"]!))
    let origin = json["origin"] as! String
    #expect(try await DeviceTrust.fetch(origin: origin, fingerprint: expected.fingerprint) == expected)
    await #expect(throws: (any Error).self) { try await DeviceTrust.fetch(origin: origin, fingerprint: String(repeating: "0", count: 64)) }
}

import CryptoKit
import Foundation
import Testing
@testable import SuzentCore

private func hex(_ text: String) -> Data {
    var data = Data()
    var index = text.startIndex
    while index < text.endIndex {
        let next = text.index(index, offsetBy: 2)
        data.append(UInt8(text[index..<next], radix: 16)!)
        index = next
    }
    return data
}

private func hex(_ data: Data) -> String { data.map { String(format: "%02x", $0) }.joined() }

private func base64URL(_ data: Data) -> String {
    data.base64EncodedString().replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
}

private func vectors() throws -> [String: Any] {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/relay-e2e-vectors.json"))
    return try JSONSerialization.jsonObject(with: data) as! [String: Any]
}

private func scalar(_ value: Any?) throws -> P256.KeyAgreement.PrivateKey {
    try P256.KeyAgreement.PrivateKey(rawRepresentation: hex(value as! String))
}

@Test func relayCryptoMatchesTheContractVectors() throws {
    let v = try vectors()
    let channel = v["channel_token"] as! String
    let desktopStatic = try scalar(v["desktop_static_private"])
    #expect(hex(desktopStatic.publicKey.x963Representation) == v["desktop_static_public"] as? String)
    #expect(Data(base64URL: v["desktop_static_public_b64url"] as! String) == desktopStatic.publicKey.x963Representation)
    let phoneKey = try scalar(v["phone_ephemeral_private"])
    #expect(hex(phoneKey.publicKey.x963Representation) == v["handshake_message_1"] as? String)
    let (reply, desktop) = try RelayCrypto.respond(staticKey: desktopStatic, channel: channel,
                                                   first: phoneKey.publicKey.x963Representation,
                                                   ephemeral: try scalar(v["desktop_ephemeral_private"]))
    #expect(hex(reply) == v["handshake_message_2"] as? String)
    let phone = try RelayCrypto.finish(ephemeral: phoneKey, staticKey: desktopStatic.publicKey.x963Representation,
                                       channel: channel, reply: hex(v["handshake_message_2"] as! String))
    for message in v["messages"] as! [[String: String]] {
        let (sender, receiver) = message["direction"] == "phone_to_desktop" ? (phone, desktop) : (desktop, phone)
        let plaintext = hex(message["plaintext"]!)
        #expect(hex(try sender.encrypt(plaintext)) == message["ciphertext"])
        #expect(try receiver.decrypt(hex(message["ciphertext"]!)) == plaintext)
    }
}

@Test func relayHandshakeRejectsImpostorsTamperingAndOtherChannels() throws {
    let desktopStatic = P256.KeyAgreement.PrivateKey()
    let phoneKey = P256.KeyAgreement.PrivateKey()
    let channel = "channel-token-aaaaaaaaaaaaaaaa"
    let (reply, _) = try RelayCrypto.respond(staticKey: desktopStatic, channel: channel, first: phoneKey.publicKey.x963Representation)
    let key = desktopStatic.publicKey.x963Representation
    #expect(throws: RelayCryptoError.self) {
        try RelayCrypto.finish(ephemeral: phoneKey, staticKey: P256.KeyAgreement.PrivateKey().publicKey.x963Representation,
                               channel: channel, reply: reply)
    }
    #expect(throws: RelayCryptoError.self) {
        try RelayCrypto.finish(ephemeral: phoneKey, staticKey: key, channel: "another-channel-bbbbbbbbbbbbbbbb", reply: reply)
    }
    var tampered = reply
    tampered[tampered.count - 1] ^= 1
    #expect(throws: RelayCryptoError.self) {
        try RelayCrypto.finish(ephemeral: phoneKey, staticKey: key, channel: channel, reply: tampered)
    }
    #expect(throws: RelayCryptoError.self) { try RelayCrypto.publicKey(Data([4]) + Data(count: 64)) }
}

@Test func relaySessionsRejectReplayAndReordering() throws {
    let desktopStatic = P256.KeyAgreement.PrivateKey()
    let phoneKey = P256.KeyAgreement.PrivateKey()
    let channel = "channel-token-aaaaaaaaaaaaaaaa"
    let (reply, desktop) = try RelayCrypto.respond(staticKey: desktopStatic, channel: channel, first: phoneKey.publicKey.x963Representation)
    let phone = try RelayCrypto.finish(ephemeral: phoneKey, staticKey: desktopStatic.publicKey.x963Representation, channel: channel, reply: reply)
    let first = try phone.encrypt(Data("one".utf8))
    let second = try phone.encrypt(Data("two".utf8))
    #expect(throws: RelayCryptoError.self) { try desktop.decrypt(second) }
    #expect(try desktop.decrypt(first) == Data("one".utf8))
    #expect(throws: RelayCryptoError.self) { try desktop.decrypt(first) }
    #expect(try desktop.decrypt(second) == Data("two".utf8))
}

private let validKey = base64URL(P256.KeyAgreement.PrivateKey().publicKey.x963Representation)

@Test func relayRoutesAreValidated() {
    let route = RelayRoute(url: "https://relay.example/", channel: String(repeating: "a", count: 43), key: validKey)
    #expect(route.validated()?.url == "https://relay.example")
    #expect(route.validated()?.socketURL?.absoluteString == "wss://relay.example/c/\(route.channel)/__suzent_e2e__")
    #expect(RelayRoute(url: "http://relay.example", channel: route.channel, key: validKey).validated() == nil)
    #expect(RelayRoute(url: "http://relay.example", channel: route.channel, key: validKey).validated(allowHTTP: true) != nil)
    #expect(RelayRoute(url: "https://u:p@relay.example", channel: route.channel, key: validKey).validated() == nil)
    #expect(RelayRoute(url: "https://relay.example", channel: "short", key: validKey).validated() == nil)
    #expect(RelayRoute(url: "https://relay.example", channel: route.channel, key: "AAAA").validated() == nil)
}

@Test func connectionsKeepTheirRelay() throws {
    let route = RelayRoute(url: "https://relay.example", channel: String(repeating: "b", count: 43), key: validKey)
    let saved = Connection(origin: "https://desk.example", hostToken: "t", clientProtocol: 1, relay: route)
    let decoded = try JSONDecoder().decode(Connection.self, from: JSONEncoder().encode(saved))
    #expect(decoded.relay == route)
    let legacy = try JSONDecoder().decode(Connection.self, from: Data(#"{"origin":"https://desk.example","hostToken":"t"}"#.utf8))
    #expect(legacy.relay == nil)
}

@Test func invitationsCarryAValidRelayOnly() throws {
    func invitation(_ relay: [String: Any]) throws -> PairingInvitation {
        let text = String(decoding: try JSONSerialization.data(withJSONObject: [
            "type": "suzent.mobile", "pairing_protocol": 1, "origin": "https://desk.example",
            "pairing_id": String(repeating: "a", count: 32), "invitation": String(repeating: "b", count: 43),
            "expires_at": Date().timeIntervalSince1970 + 300, "relay": relay
        ]), as: UTF8.self)
        return try PairingInvitation.parse(text)
    }
    let channel = String(repeating: "c", count: 43)
    let good = try invitation(["version": 1, "url": "https://relay.example", "channel": channel, "key": validKey])
    #expect(good.relay?.channel == channel)
    let insecure = try invitation(["version": 1, "url": "http://relay.example", "channel": channel, "key": validKey])
    #expect(insecure.relay == nil)
}

@Test func relayBinaryFramesRoundTrip() {
    let frame = RelayFrame.encodeBinary(kind: RelayFrame.wbin, id: "w1", payload: Data([9, 8]))
    #expect(frame == Data([3, 2]) + Data("w1".utf8) + Data([9, 8]))
    let decoded = RelayFrame.decodeBinary(frame)
    #expect(decoded?.kind == RelayFrame.wbin && decoded?.id == "w1" && decoded?.payload == Data([9, 8]))
    #expect(RelayFrame.decodeBinary(Data([3, 5, 1])) == nil)
    #expect(RelayFrame.target(URL(string: "https://h.example/mobile/client/voice?chat_id=a%20b")) == "/mobile/client/voice?chat_id=a%20b")
}

/// A desktop on the far side of the relay: answers the handshake, then `hreq` and `wopen` frames.
private final class FakeDesktop: RelayTransport, @unchecked Sendable {
    let staticKey = P256.KeyAgreement.PrivateKey()
    let channel = String(repeating: "d", count: 43)
    private let lock = NSLock()
    private var session: RelaySession?
    private var inbox: [Data] = []
    private var receiver: CheckedContinuation<Data, Error>?
    private var closed = false
    private var frames: [[String: Any]] = []
    private var bodies: [String: Data] = [:]
    let stall: Bool

    init(stall: Bool = false) { self.stall = stall }

    func route(key: Data? = nil) -> RelayRoute {
        RelayRoute(url: "https://relay.example", channel: channel, key: base64URL(key ?? staticKey.publicKey.x963Representation))
    }

    var requests: [[String: Any]] { lock.withLock { frames } }

    func send(_ data: Data, completion: @escaping @Sendable (Error?) -> Void) {
        completion(nil)
        do {
            guard let session = lock.withLock({ self.session }) else {
                let (reply, opened) = try RelayCrypto.respond(staticKey: staticKey, channel: channel, first: data)
                lock.withLock { self.session = opened }
                deliver(reply)
                return
            }
            let plaintext = try session.decrypt(data)
            let body = Data(plaintext.dropFirst())
            if plaintext.first == 1 {
                guard let frame = RelayFrame.decodeBinary(body) else { return }
                if frame.kind == RelayFrame.hbody {
                    lock.withLock { bodies[frame.id, default: Data()].append(frame.payload) }
                    try reply(session, ["t": "hack", "id": frame.id, "n": frame.payload.count])
                } else {
                    try reply(session, binary: frame.kind, id: frame.id, payload: frame.payload)
                }
                return
            }
            let frame = try JSONSerialization.jsonObject(with: body) as! [String: Any]
            lock.withLock { frames.append(frame) }
            let id = frame["id"] as! String
            switch frame["t"] as? String {
            case "hreq":
                if stall || frame["stream"] as? Bool == true { return }
                try answer(session, id: id, body: (frame["b"] as? String).flatMap { Data(base64Encoded: $0) } ?? Data())
            case "hreqend":
                try answer(session, id: id, body: lock.withLock { bodies[id] } ?? Data())
            case "wopen":
                try reply(session, ["t": "wopened", "id": id])
            default: break
            }
        } catch { close() }
    }

    private func answer(_ session: RelaySession, id: String, body: Data) throws {
        try reply(session, ["t": "hres", "id": id, "status": 201, "headers": ["content-type": "text/plain"]])
        try reply(session, binary: RelayFrame.hchunk, id: id, payload: body)
        try reply(session, ["t": "hend", "id": id])
    }

    private func reply(_ session: RelaySession, _ frame: [String: Any]) throws {
        deliver(try session.encrypt(Data([0]) + JSONSerialization.data(withJSONObject: frame)))
    }

    private func reply(_ session: RelaySession, binary kind: UInt8, id: String, payload: Data) throws {
        deliver(try session.encrypt(Data([1]) + RelayFrame.encodeBinary(kind: kind, id: id, payload: payload)))
    }

    private func deliver(_ data: Data) {
        let waiting: CheckedContinuation<Data, Error>? = lock.withLock {
            guard let receiver else { inbox.append(data); return nil }
            self.receiver = nil
            return receiver
        }
        waiting?.resume(returning: data)
    }

    func receive() async throws -> Data {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Data, Error>) in
            let state: Result<Data, Error>? = lock.withLock {
                if !inbox.isEmpty { return .success(inbox.removeFirst()) }
                if closed { return .failure(URLError(.networkConnectionLost)) }
                receiver = continuation
                return nil
            }
            if let state { continuation.resume(with: state) }
        }
    }

    func close() {
        let waiting: CheckedContinuation<Data, Error>? = lock.withLock {
            closed = true
            defer { receiver = nil }
            return receiver
        }
        waiting?.resume(throwing: URLError(.networkConnectionLost))
    }
}

private func relaySession() -> URLSession {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [RelayURLProtocol.self]
    return URLSession(configuration: config)
}

@Test func requestsTravelThroughTheTunnel() async throws {
    let desktop = FakeDesktop()
    let tunnel = try RelayTunnel(route: desktop.route()) { desktop }
    defer { tunnel.close() }
    var request = URLRequest(url: URL(string: tunnel.backend.endpoint("mobile/echo").absoluteString + "?x=1")!)
    request.httpMethod = "POST"
    request.httpBody = Data("hello".utf8)
    request.setValue("Bearer t", forHTTPHeaderField: "Authorization")
    let (data, response) = try await relaySession().data(for: request)
    #expect((response as? HTTPURLResponse)?.statusCode == 201)
    #expect(String(decoding: data, as: UTF8.self) == "hello")
    let sent = desktop.requests.first
    #expect(sent?["path"] as? String == "/mobile/echo?x=1")
    #expect(sent?["method"] as? String == "POST")
    #expect((sent?["headers"] as? [String: String])?["authorization"] == "Bearer t")
}

@Test func largeBodiesStreamPacedByTheDesktop() async throws {
    let desktop = FakeDesktop()
    let tunnel = try RelayTunnel(route: desktop.route()) { desktop }
    defer { tunnel.close() }
    let body = Data((0..<(9 * 1024 * 1024)).map { UInt8(truncatingIfNeeded: $0) })
    var request = URLRequest(url: tunnel.backend.endpoint("mobile/client/upload"))
    request.httpMethod = "POST"
    request.httpBody = body
    let (data, _) = try await relaySession().data(for: request)
    #expect(data == body)
    #expect(desktop.requests.first?["stream"] as? Bool == true)
    #expect(desktop.requests.first?["b"] == nil)
}

@Test func stalledRequestsTimeOutAndCancel() async throws {
    let desktop = FakeDesktop(stall: true)
    let tunnel = try RelayTunnel(route: desktop.route()) { desktop }
    defer { tunnel.close() }
    var request = URLRequest(url: tunnel.backend.endpoint("mobile/capabilities"))
    request.timeoutInterval = 1.5
    await #expect(throws: URLError.self) { _ = try await relaySession().data(for: request) }
    try await Task.sleep(for: .milliseconds(200))
    #expect(desktop.requests.contains { $0["t"] as? String == "hcancel" })
}

@Test func webSocketsTravelThroughTheTunnel() async throws {
    let desktop = FakeDesktop()
    let tunnel = try RelayTunnel(route: desktop.route()) { desktop }
    defer { tunnel.close() }
    let socket = tunnel.webSocket(for: URLRequest(url: tunnel.backend.webSocketURL))
    socket.resume()
    try await socket.send(.string("ping"))
    guard case .string(let text) = try await socket.receive() else { Issue.record("Expected text"); return }
    #expect(text == "ping")
    #expect(desktop.requests.first?["path"] as? String == "/ws/node")
    socket.cancel(with: .goingAway, reason: nil)
    await #expect(throws: (any Error).self) { _ = try await socket.receive() }
}

@Test func aDesktopWithoutThePairedKeyIsRefused() async throws {
    let desktop = FakeDesktop()
    let tunnel = try RelayTunnel(route: desktop.route(key: P256.KeyAgreement.PrivateKey().publicKey.x963Representation)) { desktop }
    defer { tunnel.close() }
    await #expect(throws: (any Error).self) {
        _ = try await relaySession().data(for: URLRequest(url: tunnel.backend.endpoint("mobile/capabilities")))
    }
    #expect(desktop.requests.isEmpty)
}

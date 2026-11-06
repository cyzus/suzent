import CryptoKit
import Foundation

/// How to reach a desktop through its owner's relay; carried by the pairing QR code and the session.
public struct RelayRoute: Codable, Sendable, Equatable {
    public var version: Int
    public let url: String
    public let channel: String
    public let key: String

    public init(url: String, channel: String, key: String) {
        version = 1
        self.url = url
        self.channel = channel
        self.key = key
    }

    public var staticKey: Data? { Data(base64URL: key) }

    /// `wss://<relay>/c/<channel>/__suzent_e2e__`
    var socketURL: URL? {
        guard var parts = URLComponents(string: url) else { return nil }
        parts.scheme = parts.scheme?.lowercased() == "https" ? "wss" : "ws"
        let base = parts.percentEncodedPath.hasSuffix("/") ? String(parts.percentEncodedPath.dropLast()) : parts.percentEncodedPath
        parts.percentEncodedPath = "\(base)/c/\(channel)/__suzent_e2e__"
        return parts.url
    }

    /// The route if it is one this app can use: HTTPS, no credentials, a plausible channel and a P-256 key.
    public func validated(allowHTTP: Bool = false) -> RelayRoute? {
        guard version == 1, let parts = URLComponents(string: url), let scheme = parts.scheme?.lowercased(),
              scheme == "https" || (allowHTTP && scheme == "http"),
              let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              channel.range(of: "^[A-Za-z0-9_-]{16,128}$", options: .regularExpression) != nil,
              let staticKey, (try? RelayCrypto.publicKey(staticKey)) != nil else { return nil }
        return RelayRoute(url: url.hasSuffix("/") ? String(url.dropLast()) : url, channel: channel, key: key)
    }
}

extension Data {
    init?(base64URL text: String) {
        var value = text.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        while value.count % 4 != 0 { value += "=" }
        self.init(base64Encoded: value)
    }
}

/// The relay frame protocol's binary frames: `[kind][idLen][id][payload]`.
enum RelayFrame {
    static let hchunk: UInt8 = 1
    static let hbody: UInt8 = 2
    static let wbin: UInt8 = 3
    static let wtext: UInt8 = 4
    /// Bigger request bodies stream in chunks instead of one oversized WebSocket message.
    static let streamThreshold = 256 * 1024
    static let bodyChunk = 256 * 1024

    static func encodeBinary(kind: UInt8, id: String, payload: Data) -> Data {
        let rawID = Data(id.utf8)
        return Data([kind, UInt8(rawID.count)]) + rawID + payload
    }

    static func decodeBinary(_ frame: Data) -> (kind: UInt8, id: String, payload: Data)? {
        let bytes = [UInt8](frame)
        guard bytes.count >= 2 else { return nil }
        let end = 2 + Int(bytes[1])
        guard bytes.count >= end else { return nil }
        return (bytes[0], String(decoding: bytes[2..<end], as: UTF8.self), Data(bytes[end...]))
    }

    /// The path and query a request targets on the desktop.
    static func target(_ url: URL?) -> String {
        guard let url, let parts = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return "/" }
        let path = parts.percentEncodedPath.isEmpty ? "/" : parts.percentEncodedPath
        return parts.percentEncodedQuery.map { "\(path)?\($0)" } ?? path
    }

    static func headers(_ request: URLRequest) -> [String: String] {
        var headers: [String: String] = [:]
        for (name, value) in request.allHTTPHeaderFields ?? [:] { headers[name.lowercased()] = value }
        return headers
    }
}

/// The socket a tunnel runs over. A protocol so tests can stand in for the relay.
protocol RelayTransport: Sendable {
    func send(_ data: Data, completion: @escaping @Sendable (Error?) -> Void)
    func receive() async throws -> Data
    func close()
}

private struct WebSocketTransport: RelayTransport {
    let task: URLSessionWebSocketTask

    func send(_ data: Data, completion: @escaping @Sendable (Error?) -> Void) {
        task.send(.data(data), completionHandler: completion)
    }

    func receive() async throws -> Data {
        guard case .data(let data) = try await task.receive() else { throw RelayCryptoError.malformed }
        return data
    }

    func close() { task.cancel(with: .goingAway, reason: nil) }
}

protocol RelayHTTPSink: AnyObject, Sendable {
    func head(status: Int, headers: [String: String])
    func chunk(_ data: Data)
    func end()
    func fail(_ error: Error)
}

/// One end-to-end encrypted WebSocket to the desktop through a relay. Inside it the phone plays the
/// relay's part of the relay frame protocol: it sends `hreq`/`wopen` and the desktop answers with
/// `hres`, body chunks and `wopened`, exactly as over the relay's own agent socket.
///
/// HTTP requests reach it through `RelayURLProtocol`, which claims requests to the tunnel's
/// placeholder host, so a client's URLSession code works unchanged; WebSockets use `webSocket(for:)`.
public final class RelayTunnel: @unchecked Sendable {
    public let route: RelayRoute
    /// The only origin a relay-backed client is given; requests to it never leave the tunnel.
    public let backend: Backend
    private let host: String
    private let dialer: @Sendable () -> RelayTransport
    private let lock = NSLock()
    private var link: RelayLink?
    private var closed = false
    private var counter: UInt64 = 0
    private static let registry = RelayRegistry()

    public convenience init(route: RelayRoute) throws {
        let session = URLSession(configuration: .ephemeral)
        guard let url = route.socketURL else { throw ClientError.invalidAddress }
        try self.init(route: route) { WebSocketTransport(task: session.webSocketTask(with: url)) }
    }

    init(route: RelayRoute, dialer: @escaping @Sendable () -> RelayTransport) throws {
        guard let key = route.staticKey, (try? RelayCrypto.publicKey(key)) != nil else { throw ClientError.invalidAddress }
        self.route = route
        self.dialer = dialer
        host = "\(UUID().uuidString.lowercased()).relay.suzent.invalid"
        backend = try Backend("https://\(host)")
        RelayTunnel.registry.add(self, host: host)
    }

    static func tunnel(for host: String?) -> RelayTunnel? { host.flatMap { registry.tunnel($0) } }

    public func close() {
        let current: RelayLink? = lock.withLock {
            closed = true
            defer { link = nil }
            return link
        }
        RelayTunnel.registry.remove(host)
        current?.shutdown(URLError(.cancelled))
    }

    func nextID(_ prefix: String) -> String {
        lock.withLock {
            counter += 1
            return "\(prefix)\(counter)"
        }
    }

    /// An open, handshaken link, dialling a new one if there is none or the last one failed. A failed
    /// link never comes back: its counters can't be trusted, so a fresh handshake starts a fresh session.
    func connect() async throws -> RelayLink {
        let current: RelayLink = try lock.withLock {
            if closed { throw URLError(.cancelled) }
            if let link, !link.failed { return link }
            let next = RelayLink(route: route, transport: dialer())
            link = next
            return next
        }
        current.start()
        try await current.ready()
        return current
    }

    /// Sends the request; the response arrives through `sink`. `onStart` names the exchange as soon
    /// as it exists so it can be cancelled, and `onProgress` marks each body chunk the desktop let through.
    func send(_ request: URLRequest, body: Data?, sink: RelayHTTPSink,
              onStart: @Sendable (RelayLink, String) -> Void, onProgress: @Sendable () -> Void) async throws {
        let link = try await connect()
        let id = nextID("h")
        let body = body.map { Data($0) }
        var headers = RelayFrame.headers(request)
        if let body { headers["content-length"] = String(body.count) }
        var frame: [String: Any] = ["t": "hreq", "id": id, "method": request.httpMethod ?? "GET",
                                    "path": RelayFrame.target(request.url), "headers": headers]
        let window = (body?.count ?? 0) > RelayFrame.streamThreshold ? RelayBodyWindow() : nil
        if window != nil { frame["stream"] = true }
        else if let body, !body.isEmpty { frame["b"] = body.base64EncodedString() }
        try link.add(exchange: sink, id: id, window: window)
        onStart(link, id)
        do {
            try link.send(frame)
            if let body, let window {
                var start = 0
                while start < body.count {
                    let end = min(body.count, start + RelayFrame.bodyChunk)
                    try await window.reserve(end - start)
                    try link.sendBinary(RelayFrame.hbody, id: id, payload: body.subdata(in: start..<end))
                    onProgress()
                    start = end
                }
                try link.send(["t": "hreqend", "id": id])
            }
        } catch {
            link.cancelExchange(id)
            throw error
        }
    }

    /// Opens the request's path as a WebSocket on the desktop. Like a URLSessionWebSocketTask it
    /// does nothing until `resume()`.
    public func webSocket(for request: URLRequest) -> any MobileSocket {
        RelayWebSocket(tunnel: self, id: nextID("w"), path: RelayFrame.target(request.url), headers: RelayFrame.headers(request))
    }
}

private final class RelayRegistry: @unchecked Sendable {
    private struct Entry { weak var tunnel: RelayTunnel? }
    private let lock = NSLock()
    private var entries: [String: Entry] = [:]

    func add(_ tunnel: RelayTunnel, host: String) { lock.withLock { entries[host] = Entry(tunnel: tunnel) } }
    func remove(_ host: String) { lock.withLock { _ = entries.removeValue(forKey: host) } }
    func tunnel(_ host: String) -> RelayTunnel? { lock.withLock { entries[host.lowercased()]?.tunnel } }
}

final class RelayLink: @unchecked Sendable {
    private let route: RelayRoute
    private let transport: RelayTransport
    private let ephemeral = P256.KeyAgreement.PrivateKey()
    private let lock = NSLock()
    private var started = false
    private var session: RelaySession?
    private var failure: Error?
    private var waiters: [CheckedContinuation<Void, Error>] = []
    private var exchanges: [String: RelayHTTPSink] = [:]
    private var windows: [String: RelayBodyWindow] = [:]
    private var sockets: [String: RelayWebSocket] = [:]

    init(route: RelayRoute, transport: RelayTransport) {
        self.route = route
        self.transport = transport
    }

    var failed: Bool { lock.withLock { failure != nil } }

    func start() {
        guard lock.withLock({ () -> Bool in
            defer { started = true }
            return !started
        }) else { return }
        transport.send(ephemeral.publicKey.x963Representation) { [weak self] error in
            if let error { self?.shutdown(error) }
        }
        Task { await self.receiveLoop() }
        Task { [weak self] in
            try? await Task.sleep(for: .seconds(15))
            guard let self, self.lock.withLock({ self.session == nil }) else { return }
            self.shutdown(URLError(.timedOut))
        }
    }

    func ready() async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let state: Result<Void, Error>? = lock.withLock {
                if let failure { return .failure(failure) }
                if session != nil { return .success(()) }
                waiters.append(continuation)
                return nil
            }
            if let state { continuation.resume(with: state) }
        }
    }

    private func receiveLoop() async {
        do {
            while !failed { try handle(try await transport.receive()) }
        } catch { shutdown(error) }
    }

    private func handle(_ data: Data) throws {
        guard let current = lock.withLock({ session }) else {
            guard let key = route.staticKey else { throw RelayCryptoError.invalidKey }
            let opened = try RelayCrypto.finish(ephemeral: ephemeral, staticKey: key, channel: route.channel, reply: data)
            let waiting: [CheckedContinuation<Void, Error>] = lock.withLock {
                session = opened
                defer { waiters = [] }
                return waiters
            }
            waiting.forEach { $0.resume() }
            return
        }
        let plaintext = try current.decrypt(data)
        guard let kind = plaintext.first else { throw RelayCryptoError.malformed }
        let body = Data(plaintext.dropFirst())
        switch kind {
        case 0: try onFrame(body)
        case 1: onBinary(body)
        default: throw RelayCryptoError.malformed
        }
    }

    func shutdown(_ error: Error) {
        let state: ([CheckedContinuation<Void, Error>], [RelayHTTPSink], [RelayBodyWindow], [RelayWebSocket])? = lock.withLock {
            guard failure == nil else { return nil }
            failure = error
            let state = (waiters, Array(exchanges.values), Array(windows.values), Array(sockets.values))
            waiters = []; exchanges = [:]; windows = [:]; sockets = [:]
            return state
        }
        guard let state else { return }
        let (waiting, pending, uploads, open) = state
        transport.close()
        waiting.forEach { $0.resume(throwing: error) }
        uploads.forEach { $0.fail(error) }
        pending.forEach { $0.fail(error) }
        open.forEach { $0.peerFailed(error) }
    }

    private func seal(_ plaintext: Data) throws {
        // Counters must reach the wire in the order they were used.
        try lock.withLock {
            if let failure { throw failure }
            guard let session else { throw URLError(.notConnectedToInternet) }
            let sealed = try session.encrypt(plaintext)
            transport.send(sealed) { [weak self] error in
                if let error { self?.shutdown(error) }
            }
        }
    }

    func send(_ frame: [String: Any]) throws {
        try seal(Data([0]) + JSONSerialization.data(withJSONObject: frame))
    }

    func sendBinary(_ kind: UInt8, id: String, payload: Data) throws {
        try seal(Data([1]) + RelayFrame.encodeBinary(kind: kind, id: id, payload: payload))
    }

    func add(exchange: RelayHTTPSink, id: String, window: RelayBodyWindow? = nil) throws {
        try lock.withLock {
            if let failure { throw failure }
            exchanges[id] = exchange
            windows[id] = window
        }
    }

    func removeExchange(_ id: String) -> RelayHTTPSink? {
        let (exchange, window) = lock.withLock { (exchanges.removeValue(forKey: id), windows.removeValue(forKey: id)) }
        window?.fail(URLError(.cancelled))
        return exchange
    }

    private func exchange(_ id: String) -> RelayHTTPSink? { lock.withLock { exchanges[id] } }

    func cancelExchange(_ id: String) {
        guard removeExchange(id) != nil else { return }
        try? send(["t": "hcancel", "id": id])
    }

    func add(socket: RelayWebSocket, id: String) throws {
        try lock.withLock {
            if let failure { throw failure }
            sockets[id] = socket
        }
    }
    func removeSocket(_ id: String) -> RelayWebSocket? { lock.withLock { sockets.removeValue(forKey: id) } }
    private func socket(_ id: String) -> RelayWebSocket? { lock.withLock { sockets[id] } }

    private func onFrame(_ data: Data) throws {
        guard let frame = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw RelayCryptoError.malformed }
        let id = frame["id"] as? String ?? ""
        switch frame["t"] as? String {
        case "hres":
            var headers: [String: String] = [:]
            for (name, value) in frame["headers"] as? [String: Any] ?? [:] {
                if let value = value as? String { headers[name] = value }
                else if let values = value as? [String] { headers[name] = values.joined(separator: ", ") }
            }
            exchange(id)?.head(status: frame["status"] as? Int ?? 502, headers: headers)
        case "hchunk":
            if let encoded = frame["b"] as? String, let bytes = Data(base64Encoded: encoded) { exchange(id)?.chunk(bytes) }
        case "hack": lock.withLock { windows[id] }?.ack(frame["n"] as? Int ?? 0)
        case "hend": removeExchange(id)?.end()
        case "herr": removeExchange(id)?.fail(URLError(.badServerResponse))
        case "wopened": socket(id)?.peerOpened(self)
        case "werr": removeSocket(id)?.peerFailed(URLError(.cannotConnectToHost))
        case "wmsg":
            if let text = frame["s"] as? String { socket(id)?.peer(.string(text)) }
            else if let encoded = frame["b"] as? String, let bytes = Data(base64Encoded: encoded) { socket(id)?.peer(.data(bytes)) }
        case "wclose": removeSocket(id)?.peerFailed(URLError(.networkConnectionLost))
        default: break
        }
    }

    private func onBinary(_ data: Data) {
        guard let frame = RelayFrame.decodeBinary(data) else { return }
        let (kind, id, payload) = frame
        switch kind {
        case RelayFrame.hchunk: exchange(id)?.chunk(payload)
        case RelayFrame.wbin: socket(id)?.peer(.data(payload))
        case RelayFrame.wtext: socket(id)?.peer(.string(String(decoding: payload, as: UTF8.self)))
        default: break
        }
    }
}

/// Paces a streamed request body: the desktop acknowledges (`hack`) the bytes its app has read, and
/// at most 4 MiB may be unacknowledged, as the relay protocol allows.
final class RelayBodyWindow: @unchecked Sendable {
    static let limit = 4 * 1024 * 1024
    private let lock = NSLock()
    private var inFlight = 0
    private var failure: Error?
    private var waiter: (size: Int, continuation: CheckedContinuation<Void, Error>)?

    func reserve(_ size: Int) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let state: Result<Void, Error>? = lock.withLock {
                if let failure { return .failure(failure) }
                if inFlight == 0 || inFlight + size <= Self.limit {
                    inFlight += size
                    return .success(())
                }
                waiter = (size, continuation)
                return nil
            }
            if let state { continuation.resume(with: state) }
        }
    }

    func ack(_ count: Int) {
        let ready: CheckedContinuation<Void, Error>? = lock.withLock {
            inFlight = max(0, inFlight - count)
            guard let waiter, inFlight == 0 || inFlight + waiter.size <= Self.limit else { return nil }
            inFlight += waiter.size
            self.waiter = nil
            return waiter.continuation
        }
        ready?.resume()
    }

    func fail(_ error: Error) {
        let waiting: CheckedContinuation<Void, Error>? = lock.withLock {
            guard failure == nil else { return nil }
            failure = error
            defer { waiter = nil }
            return waiter?.continuation
        }
        waiting?.resume(throwing: error)
    }
}

/// Answers requests to a tunnel's placeholder host from the tunnel instead of the network.
final class RelayURLProtocol: URLProtocol, RelayHTTPSink, @unchecked Sendable {
    private let lock = NSLock()
    private var work: Task<Void, Never>?
    private var watchdog: Task<Void, Never>?
    private var lastActivity = ContinuousClock.now
    private var exchange: (RelayLink, String)?
    private var responded = false
    private var finished = false

    override class func canInit(with request: URLRequest) -> Bool {
        RelayTunnel.tunnel(for: request.url?.host) != nil
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let request = self.request
        guard let tunnel = RelayTunnel.tunnel(for: request.url?.host) else { fail(URLError(.cannotFindHost)); return }
        let body = Self.body(of: request)
        let timeout = request.timeoutInterval > 0 ? request.timeoutInterval : 60
        let task = Task {
            do {
                try await tunnel.send(request, body: body, sink: self, onStart: { link, id in
                    let cancelled = self.lock.withLock { () -> Bool in
                        self.exchange = (link, id)
                        return self.finished
                    }
                    if cancelled { link.cancelExchange(id) }
                }, onProgress: { self.touch() })
            } catch { fail(error) }
        }
        // A custom protocol gets no read timeout from URLSession, so an exchange the desktop stops
        // answering ends here, as an idle direct connection would.
        let watchdog = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self else { return }
                let (idle, done, current) = self.lock.withLock { (self.lastActivity.duration(to: .now), self.finished, self.exchange) }
                if done { return }
                if idle > .seconds(timeout) {
                    self.fail(URLError(.timedOut))
                    if let current { current.0.cancelExchange(current.1) }
                    return
                }
            }
        }
        lock.withLock { work = task; self.watchdog = watchdog }
    }

    override func stopLoading() {
        let (task, timer, current, done): (Task<Void, Never>?, Task<Void, Never>?, (RelayLink, String)?, Bool) = lock.withLock {
            defer { finished = true }
            return (work, watchdog, exchange, finished)
        }
        task?.cancel()
        timer?.cancel()
        if !done, let current { current.0.cancelExchange(current.1) }
    }

    private func touch() { lock.withLock { lastActivity = .now } }

    func head(status: Int, headers: [String: String]) {
        touch()
        guard let url = request.url,
              let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: headers),
              lock.withLock({ () -> Bool in
                  defer { responded = true }
                  return !finished && !responded
              }) else { return }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    }

    func chunk(_ data: Data) {
        touch()
        guard lock.withLock({ responded && !finished }) else { return }
        client?.urlProtocol(self, didLoad: data)
    }

    func end() {
        let state: (Bool, Bool) = lock.withLock {
            defer { finished = true }
            return (finished, responded)
        }
        guard !state.0 else { return }
        if state.1 { client?.urlProtocolDidFinishLoading(self) }
        else { client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse)) }
    }

    func fail(_ error: Error) {
        let done: Bool = lock.withLock {
            defer { finished = true }
            return finished
        }
        guard !done else { return }
        client?.urlProtocol(self, didFailWithError: error)
    }

    private static func body(of request: URLRequest) -> Data? {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 64 * 1024)
        while true {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }
            data.append(buffer, count: count)
        }
        return data
    }
}

/// A desktop WebSocket opened through a tunnel.
final class RelayWebSocket: MobileSocket, @unchecked Sendable {
    private let tunnel: RelayTunnel
    private let id: String
    private let path: String
    private let headers: [String: String]
    private let lock = NSLock()
    private var started = false
    private var link: RelayLink?
    private var openedLink: RelayLink?
    private var failure: Error?
    private var inbox: [URLSessionWebSocketTask.Message] = []
    private var receiver: CheckedContinuation<URLSessionWebSocketTask.Message, Error>?
    private var openers: [CheckedContinuation<RelayLink, Error>] = []

    init(tunnel: RelayTunnel, id: String, path: String, headers: [String: String]) {
        self.tunnel = tunnel
        self.id = id
        self.path = path
        self.headers = headers
    }

    func resume() {
        guard lock.withLock({ () -> Bool in
            defer { started = true }
            return !started && failure == nil
        }) else { return }
        Task {
            do {
                let link = try await tunnel.connect()
                try lock.withLock {
                    if let failure { throw failure }
                    self.link = link
                }
                try link.add(socket: self, id: id)
                try link.send(["t": "wopen", "id": id, "path": path, "headers": headers])
            } catch { peerFailed(error) }
        }
    }

    private func opened() async throws -> RelayLink {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<RelayLink, Error>) in
            let state: Result<RelayLink, Error>? = lock.withLock {
                if let failure { return .failure(failure) }
                if let openedLink { return .success(openedLink) }
                openers.append(continuation)
                return nil
            }
            if let state { continuation.resume(with: state) }
        }
    }

    func send(_ message: URLSessionWebSocketTask.Message) async throws {
        let link = try await opened()
        switch message {
        case .string(let text): try link.sendBinary(RelayFrame.wtext, id: id, payload: Data(text.utf8))
        case .data(let data): try link.sendBinary(RelayFrame.wbin, id: id, payload: data)
        @unknown default: throw URLError(.unsupportedURL)
        }
    }

    func receive() async throws -> URLSessionWebSocketTask.Message {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<URLSessionWebSocketTask.Message, Error>) in
            let state: Result<URLSessionWebSocketTask.Message, Error>? = lock.withLock {
                if !inbox.isEmpty { return .success(inbox.removeFirst()) }
                if let failure { return .failure(failure) }
                if receiver != nil { return .failure(URLError(.cannotLoadFromNetwork)) }
                receiver = continuation
                return nil
            }
            if let state { continuation.resume(with: state) }
        }
    }

    func cancel(with closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        let link = lock.withLock { failure == nil ? self.link : nil }
        if let link, link.removeSocket(id) != nil {
            try? link.send(["t": "wclose", "id": id, "code": closeCode.rawValue,
                            "reason": reason.map { String(decoding: $0, as: UTF8.self) } ?? ""])
        }
        peerFailed(URLError(.cancelled))
    }

    func peerOpened(_ link: RelayLink) {
        let waiting: [CheckedContinuation<RelayLink, Error>] = lock.withLock {
            guard failure == nil else { return [] }
            openedLink = link
            defer { openers = [] }
            return openers
        }
        waiting.forEach { $0.resume(returning: link) }
    }

    func peer(_ message: URLSessionWebSocketTask.Message) {
        let waiting: CheckedContinuation<URLSessionWebSocketTask.Message, Error>? = lock.withLock {
            guard failure == nil else { return nil }
            guard let receiver else { inbox.append(message); return nil }
            self.receiver = nil
            return receiver
        }
        waiting?.resume(returning: message)
    }

    func peerFailed(_ error: Error) {
        let state: (CheckedContinuation<URLSessionWebSocketTask.Message, Error>?, [CheckedContinuation<RelayLink, Error>])? = lock.withLock {
            guard failure == nil else { return nil }
            failure = error
            defer { receiver = nil; openers = [] }
            return (receiver, openers)
        }
        guard let state else { return }
        let (receiving, opening) = state
        receiving?.resume(throwing: error)
        opening.forEach { $0.resume(throwing: error) }
    }
}

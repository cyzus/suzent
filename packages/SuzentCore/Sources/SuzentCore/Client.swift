import Foundation

private final class RedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

public final class SuzentClient: Sendable {
    public let backend: Backend
    private let token: String
    private let session: URLSession

    public init(backend: Backend, token: String) {
        self.backend = backend
        self.token = token
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 90
        config.timeoutIntervalForResource = 3600
        config.urlCache = nil
        session = URLSession(configuration: config, delegate: RedirectBlocker(), delegateQueue: nil)
    }

    public func close() { session.invalidateAndCancel() }

    public func nodeSocket() -> URLSessionWebSocketTask {
        session.webSocketTask(with: backend.webSocketURL)
    }

    private func request(_ path: String, body: [String: String]? = nil) throws -> URLRequest {
        var request = URLRequest(url: backend.endpoint(path))
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(body)
        }
        return request
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { throw ClientError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else { throw ClientError.http(http.statusCode) }
    }

    private func data(_ path: String, body: [String: String]? = nil) async throws -> Data {
        let (data, response) = try await session.data(for: request(path, body: body))
        try validate(response)
        return data
    }

    public func chats() async throws -> [Chat] {
        struct Listing: Decodable { let chats: [Chat] }
        return try JSONDecoder().decode(Listing.self, from: await data("chats")).chats
    }

    public func createChat(title: String) async throws -> Chat {
        try JSONDecoder().decode(Chat.self, from: await data("chats", body: ["title": title]))
    }

    public func chat(_ id: String) async throws -> Chat {
        // IDs are backend-issued. Reject path separators instead of treating them as routes.
        guard !id.contains("/"), id != ".", id != ".." else { throw ClientError.invalidResponse }
        return try JSONDecoder().decode(Chat.self, from: await data("chats/\(id)"))
    }

    public func send(_ text: String, chatID: String) async throws {
        _ = try await data("chat/send", body: ["chat_id": chatID, "message": text])
    }

    public func stop(_ chatID: String) async throws {
        _ = try await data("chat/stop", body: ["chat_id": chatID])
    }

    public func observe(_ chatID: String, onEvent: @Sendable (StreamEvent) async -> Void) async throws {
        var recovery = StreamRecovery()
        for attempt in 0..<5 {
            try Task.checkCancellation()
            var request = try request("chat/live", body: ["chat_id": chatID])
            request.httpBody = try recovery.request(chatID: chatID)
            do {
                let (bytes, response) = try await session.bytes(for: request)
                try validate(response)
                if (response as? HTTPURLResponse)?.statusCode == 204 { return }
                guard (response as? HTTPURLResponse)?.mimeType == "text/event-stream" else {
                    throw ClientError.invalidResponse
                }
                var decoder = SSEByteDecoder()
                for try await byte in bytes {
                    try Task.checkCancellation()
                    guard let payload = decoder.consume(byte) else { continue }
                    let frame = try JSONDecoder().decode(StreamFrame.self, from: Data(payload.utf8))
                    for event in try recovery.consume(frame) { await onEvent(event) }
                    if recovery.ended { break }
                }
                if recovery.ended {
                    if recovery.superseded { recovery = StreamRecovery() }
                    else if recovery.persisted { return }
                    else { throw ClientError.saveFailed }
                } else { throw ClientError.interrupted }
            } catch {
                try Task.checkCancellation()
                if case ClientError.saveFailed = error { throw error }
                if case ClientError.http(let code) = error, code < 500 { throw error }
                if attempt == 4 { throw error }
            }
            try await Task.sleep(for: .milliseconds(250 * (1 << attempt)))
        }
        throw ClientError.interrupted
    }
}

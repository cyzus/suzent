import Foundation

public struct Backend: Sendable, Equatable {
    public let url: URL

    public init(_ raw: String, allowHTTP: Bool = false) throws {
        guard let parts = URLComponents(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = parts.scheme?.lowercased(),
              scheme == "https" || (allowHTTP && scheme == "http"),
              let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil,
              parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/",
              parts.port == nil || (1...65535).contains(parts.port!),
              let url = parts.url else { throw ClientError.invalidAddress }
        self.url = url
    }

    public func endpoint(_ path: String) -> URL {
        path.split(separator: "/").reduce(url) { $0.appendingPathComponent(String($1)) }
    }

    public var webSocketURL: URL {
        var parts = URLComponents(url: endpoint("ws/node"), resolvingAgainstBaseURL: false)!
        parts.scheme = url.scheme == "https" ? "wss" : "ws"
        return parts.url!
    }
}

public enum ClientError: Error, LocalizedError, Sendable {
    case invalidAddress, http(Int), invalidResponse, interrupted, saveFailed

    public var errorDescription: String? {
        switch self {
        case .saveFailed: String(localized: "The response could not be saved. Keep this view open and retry refreshing history.")
        case .invalidAddress: String(localized: "Enter an HTTPS origin without a path. HTTP is available in debug builds.")
        case .http(let code): String(localized: "Backend request failed (HTTP \(code)).")
        case .invalidResponse: String(localized: "The backend returned an invalid response.")
        case .interrupted: String(localized: "Live connection ended. Refresh history before sending again.")
        }
    }
}

public struct Chat: Decodable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public var messages: [ChatMessage]?
    public var isRunning: Bool?
}

public struct ChatMessage: Decodable, Sendable {
    public let role: String
    public let content: String

    public let parts: [MessagePart]
    public let name: String?
    public let toolCallId: String?

    public init(role: String, content: String) {
        self.role = role
        self.content = content
        self.parts = []
        self.name = nil
        self.toolCallId = nil
    }

    enum CodingKeys: String, CodingKey { case role, content, parts, name; case toolCallId = "tool_call_id" }
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        role = try values.decodeIfPresent(String.self, forKey: .role) ?? "assistant"
        content = (try? values.decode(String.self, forKey: .content)) ?? ""
        parts = try values.decodeIfPresent([MessagePart].self, forKey: .parts) ?? []
        name = try values.decodeIfPresent(String.self, forKey: .name)
        toolCallId = try values.decodeIfPresent(String.self, forKey: .toolCallId)
    }
}

public struct StreamEvent: Decodable, Sendable {
    public let type: String
    public let delta: String?
    public let message: String?
}

public struct SSEDecoder: Sendable {
    private var lines: [String] = []
    public init() {}

    public mutating func consume(_ line: String) -> String? {
        let line = line.hasSuffix("\r") ? String(line.dropLast()) : line
        if line.isEmpty {
            defer { lines.removeAll(keepingCapacity: true) }
            return lines.isEmpty ? nil : lines.joined(separator: "\n")
        }
        if line.hasPrefix("data:") {
            var value = String(line.dropFirst(5))
            if value.hasPrefix(" ") { value.removeFirst() }
            lines.append(value)
        }
        return nil
    }
}

public struct SSEByteDecoder: Sendable {
    private var line: [UInt8] = []
    private var previousWasCR = false
    private var decoder = SSEDecoder()
    public init() {}

    public mutating func consume(_ byte: UInt8) -> String? {
        if previousWasCR && byte == 10 { previousWasCR = false; return nil }
        previousWasCR = byte == 13
        if byte == 10 || byte == 13 {
            defer { line.removeAll(keepingCapacity: true) }
            return decoder.consume(String(decoding: line, as: UTF8.self))
        }
        line.append(byte)
        return nil
    }
}

public enum NodeProtocol {
    public static func connect(name: String, platform: String, token: String) -> [String: Any] {
        ["type": "connect", "display_name": name, "platform": platform,
         "device_token": token, "capabilities": [["name": "device.status",
         "description": "Foreground device availability", "params_schema": [:]]]]
    }

    public static func reply(to message: [String: Any], platform: String) -> [String: Any]? {
        switch message["type"] as? String {
        case "ping": return ["type": "pong"]
        case "invoke":
            guard let id = message["request_id"] as? String else { return nil }
            if message["command"] as? String == "device.status" {
                return ["type": "result", "request_id": id, "success": true,
                        "result": ["platform": platform, "foreground": true]]
            }
            return ["type": "result", "request_id": id, "success": false,
                    "error": "Unsupported capability"]
        default: return nil
        }
    }
}

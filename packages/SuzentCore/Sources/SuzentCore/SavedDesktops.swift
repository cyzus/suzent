import Foundation

/// A paired desktop credential. The field names are the Keychain JSON shape and must stay stable.
public struct Connection: Codable, Sendable, Equatable {
    public var origins: [String]?
    public var tls: DeviceTrust?
    public var previousOrigins: [String]?
    public var previousTLS: DeviceTrust?
    public var origin: String
    public let hostToken: String
    public var nodeToken: String
    public var clientProtocol: Int?
    public var previousToken: String?
    public var previousOrigin: String?

    public init(origins: [String]? = nil, tls: DeviceTrust? = nil, previousOrigins: [String]? = nil, previousTLS: DeviceTrust? = nil,
                origin: String, hostToken: String, nodeToken: String = "", clientProtocol: Int? = nil,
                previousToken: String? = nil, previousOrigin: String? = nil) {
        self.origins = origins; self.tls = tls; self.previousOrigins = previousOrigins; self.previousTLS = previousTLS
        self.origin = origin; self.hostToken = hostToken; self.nodeToken = nodeToken; self.clientProtocol = clientProtocol
        self.previousToken = previousToken; self.previousOrigin = previousOrigin
    }

    public init(from decoder: any Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        origins = try values.decodeIfPresent([String].self, forKey: .origins)
        tls = try values.decodeIfPresent(DeviceTrust.self, forKey: .tls)
        previousOrigins = try values.decodeIfPresent([String].self, forKey: .previousOrigins)
        previousTLS = try values.decodeIfPresent(DeviceTrust.self, forKey: .previousTLS)
        origin = try values.decode(String.self, forKey: .origin)
        hostToken = try values.decode(String.self, forKey: .hostToken)
        nodeToken = try values.decodeIfPresent(String.self, forKey: .nodeToken) ?? ""
        clientProtocol = try values.decodeIfPresent(Int.self, forKey: .clientProtocol)
        previousToken = try values.decodeIfPresent(String.self, forKey: .previousToken)
        previousOrigin = try values.decodeIfPresent(String.self, forKey: .previousOrigin)
    }

    public var host: String { URLComponents(string: origin)?.host ?? origin }

    /// Pinned trust identifies a desktop across address changes; without it only a shared address can.
    public func matches(tls other: DeviceTrust?, origins candidates: [String]) -> Bool {
        if let tls, let other { return tls.fingerprint.lowercased() == other.fingerprint.lowercased() }
        let mine = Set(([origin] + (origins ?? [])).compactMap(normalizedOrigin))
        return candidates.compactMap(normalizedOrigin).contains { mine.contains($0) }
    }

    public func matches(_ invitation: PairingInvitation) -> Bool {
        matches(tls: invitation.tls, origins: [invitation.origin] + (invitation.origins ?? []))
    }
}

public func normalizedOrigin(_ raw: String) -> String? {
    guard let parts = URLComponents(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
          let scheme = parts.scheme?.lowercased(), let host = parts.host?.lowercased(), !host.isEmpty else { return nil }
    let port = parts.port.flatMap { (scheme == "https" && $0 == 443) || (scheme == "http" && $0 == 80) ? nil : $0 }
    return "\(scheme)://\(host)\(port.map { ":\($0)" } ?? "")"
}

public struct SavedDesktop: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public var name: String
    public var connection: Connection

    public init(id: String = UUID().uuidString, name: String, connection: Connection) {
        self.id = id; self.name = name; self.connection = connection
    }

    /// Index into a fixed palette, stable across launches (unlike `hashValue`).
    public var colorIndex: Int {
        let hash = id.utf8.reduce(UInt32(2166136261)) { ($0 ^ UInt32($1)) &* 16777619 }
        return Int(hash % UInt32(SavedDesktop.palette.count))
    }

    public var color: UInt32 { SavedDesktop.palette[colorIndex] }

    public static let palette: [UInt32] = [0x0066FF, 0x1D9E75, 0xD85A30, 0x7F77DD, 0xD4537E, 0xBA7517]
}

public struct SavedDesktops: Codable, Sendable, Equatable {
    public var activeId: String?
    public var desktops: [SavedDesktop]

    public init(activeId: String? = nil, desktops: [SavedDesktop] = []) {
        self.activeId = activeId; self.desktops = desktops
    }

    public var active: SavedDesktop? { desktops.first { $0.id == activeId } }

    public func desktop(_ id: String) -> SavedDesktop? { desktops.first { $0.id == id } }

    public func matching(_ invitation: PairingInvitation) -> SavedDesktop? {
        desktops.first { $0.connection.matches(invitation) }
    }

    public mutating func upsert(_ desktop: SavedDesktop) {
        if let index = desktops.firstIndex(where: { $0.id == desktop.id }) { desktops[index] = desktop }
        else { desktops.append(desktop) }
    }

    public mutating func update(_ id: String, connection: Connection) {
        guard let index = desktops.firstIndex(where: { $0.id == id }) else { return }
        desktops[index].connection = connection
    }

    public mutating func rename(_ id: String, to name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let index = desktops.firstIndex(where: { $0.id == id }) else { return }
        desktops[index].name = trimmed
    }

    /// Removing the active desktop hands the session to the first remaining one, if any.
    public mutating func remove(_ id: String) {
        desktops.removeAll { $0.id == id }
        if activeId == id || active == nil { activeId = desktops.first?.id }
    }

    public static func legacy(_ connection: Connection, id: String = UUID().uuidString) -> SavedDesktops {
        SavedDesktops(activeId: id, desktops: [SavedDesktop(id: id, name: connection.host, connection: connection)])
    }

    /// Accepts both the list payload and the single-connection payload written by earlier versions.
    public static func decode(_ data: Data) throws -> SavedDesktops {
        let decoder = JSONDecoder()
        if let list = try? decoder.decode(SavedDesktops.self, from: data) { return list }
        return legacy(try decoder.decode(Connection.self, from: data))
    }
}

import Foundation

public struct ClientPermissions: Codable, Sendable {
    public let chatIds: [String]
    public let allChats: Bool
    public let createChats: Bool
    public let send: Bool
    public let stop: Bool
}

public struct ClientDevice: Codable, Sendable {
    public let deviceId: String
    public let displayName: String
    public let platform: String
    public let permissions: ClientPermissions
}

public struct ClientSession: Decodable, Sendable {
    public let device: ClientDevice
    public let clientProtocol: Int
    public let streamProtocols: [Int]

    public func validate() throws {
        guard clientProtocol == 1, streamProtocols.contains(1) else { throw PairingError.incompatible }
    }
}

public struct MobileCapabilities: Decodable, Sendable {
    public let clientProtocol: Int
    public let pairingProtocol: Int
    public let streamProtocols: [Int]

    public func validate() throws {
        guard clientProtocol == 1, pairingProtocol == 1, streamProtocols.contains(1) else {
            throw PairingError.incompatible
        }
    }
}

public struct PairingInvitation: Decodable, Sendable {
    public let type: String
    public let pairingProtocol: Int
    public let origin: String
    public let pairingId: String
    public let invitation: String
    public let expiresAt: Double

    public static func parse(_ text: String, allowHTTP: Bool = false, now: Date = Date()) throws -> Self {
        guard text.utf8.count <= 4096 else { throw PairingError.invalidInvitation }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let value: Self
        do { value = try decoder.decode(Self.self, from: Data(text.utf8)) }
        catch { throw PairingError.invalidInvitation }
        guard value.type == "suzent.mobile", value.pairingProtocol == 1 else { throw PairingError.incompatible }
        guard value.expiresAt > now.timeIntervalSince1970 else { throw PairingError.expired }
        guard value.pairingId.range(of: "^[a-f0-9]{32}$", options: .regularExpression) != nil,
              value.invitation.range(of: "^[A-Za-z0-9_-]{40,64}$", options: .regularExpression) != nil else {
            throw PairingError.invalidInvitation
        }
        _ = try Backend(value.origin, allowHTTP: allowHTTP)
        return value
    }
}

public struct PairingClaim: Decodable, Sendable {
    public let pickupSecret: String
    public let expiresAt: Double
}

public struct PairingResult: Decodable, Sendable {
    public let status: String
    public let token: String?
    public let device: ClientDevice?
}

public enum PairingError: Error, LocalizedError {
    case invalidInvitation, incompatible, expired, denied

    public var errorDescription: String? {
        switch self {
        case .invalidInvitation: return String(localized: "Invalid pairing invitation. Scan a new QR code from your desktop.")
        case .incompatible: return String(localized: "This backend is incompatible. Update Suzent on your desktop and phone.")
        case .expired: return String(localized: "Pairing expired. Generate a new QR code on your desktop.")
        case .denied: return String(localized: "Pairing was declined on the desktop.")
        }
    }
}

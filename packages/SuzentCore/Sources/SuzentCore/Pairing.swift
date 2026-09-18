import Foundation
import CryptoKit

public struct ClientPermissions: Codable, Sendable {
    public let chatIds: [String]
    public let allChats: Bool
    public let createChats: Bool
    public let send: Bool
    public let stop: Bool
    public let approveTools: Bool?
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
    public let pairingRepair: Int?

    public func validate() throws {
        guard clientProtocol == 1, streamProtocols.contains(1) else { throw PairingError.incompatible }
    }
}

public struct MobileCapabilities: Decodable, Sendable {
    public let clientProtocol: Int
    public let pairingProtocol: Int
    public let streamProtocols: [Int]
    public let pairingRepair: Int?

    public func validate() throws {
        guard clientProtocol == 1, pairingProtocol == 1, streamProtocols.contains(1) else {
            throw PairingError.incompatible
        }
    }
}

public struct PairingInvitation: Decodable, Sendable {
    public let type: String
    public let pairingProtocol: Int
    public let approval: String?
    public var phoneConfirmation: Bool { approval == "phone" }
    public var origin: String
    public var origins: [String]?
    public let pairingId: String
    public let invitation: String
    public let expiresAt: Double

    public static func parse(_ text: String, allowHTTP: Bool = false, now: Date = Date()) throws -> Self {
        guard text.utf8.count <= 4096 else { throw PairingError.invalidInvitation }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        var value: Self
        do { value = try decoder.decode(Self.self, from: Data(text.utf8)) }
        catch { throw PairingError.invalidInvitation }
        guard value.type == "suzent.mobile", value.pairingProtocol == 1 else { throw PairingError.incompatible }
        guard value.approval == nil || value.approval == "phone" else { throw PairingError.incompatible }
        guard value.expiresAt > now.timeIntervalSince1970 else { throw PairingError.expired }
        guard value.pairingId.range(of: "^[a-f0-9]{32}$", options: .regularExpression) != nil,
              value.invitation.range(of: "^[A-Za-z0-9_-]{40,64}$", options: .regularExpression) != nil else {
            throw PairingError.invalidInvitation
        }
        guard (value.origins?.count ?? 0) <= 6 else { throw PairingError.invalidInvitation }
        var candidates: [String] = []
        for origin in [value.origin] + (value.origins ?? []) {
            _ = try Backend(origin, allowHTTP: true)
            if !candidates.contains(origin) { candidates.append(origin) }
        }
        guard candidates.count <= 6 else { throw PairingError.invalidInvitation }
        let usable = try candidates.filter { try Backend($0, allowHTTP: true).url.scheme == "https" || allowHTTP }
        guard let first = usable.first else { throw PairingError.invalidInvitation }
        value.origin = first
        value.origins = usable
        return value
    }

    public func resolving<Value: Sendable>(probe: @Sendable (String) async throws -> Value) async throws -> (invitation: Self, value: Value) {
        for candidate in origins ?? [origin] {
            try Task.checkCancellation()
            guard expiresAt > Date().timeIntervalSince1970 else { throw PairingError.expired }
            do {
                let value = try await probe(candidate)
                try Task.checkCancellation()
                var result = self
                result.origin = candidate
                return (result, value)
            } catch {
                try Task.checkCancellation()
            }
        }
        throw PairingError.unreachable
    }

}

public struct PairingPreview: Decodable, Sendable {
    public let pairingId: String
    public let approval: String
    public let desktopName: String
    public let permissions: ClientPermissions
    public let expiresAt: Double

    public func validate(_ invitation: PairingInvitation) throws {
        guard pairingId == invitation.pairingId, approval == "phone" else { throw PairingError.invalidInvitation }
        guard expiresAt > Date().timeIntervalSince1970 else { throw PairingError.expired }
    }
}

public struct PairingClaim: Decodable, Sendable {
    public let serverProof: String?
    public let pickupSecret: String
    public let expiresAt: Double
}

public struct PairingResult: Decodable, Sendable {
    public let status: String
    public let token: String?
    public let reused: Bool?
    public let device: ClientDevice?
}

public enum PairingError: Error, LocalizedError {
    case invalidInvitation, incompatible, expired, denied, unreachable

    public var errorDescription: String? {
        switch self {
        case .invalidInvitation: return String(localized: "Invalid pairing invitation. Scan a new QR code from your desktop.")
        case .incompatible: return String(localized: "This backend is incompatible. Update Suzent on your desktop and phone.")
        case .expired: return String(localized: "Pairing expired. Generate a new QR code on your desktop.")
        case .unreachable: return String(localized: "None of the desktop addresses could be reached with a compatible protocol. Check Wi-Fi or Tailscale and update the desktop app.")
        case .denied: return String(localized: "Pairing was declined on the desktop.")
        }
    }
}


public func pairingRepairProof(token: String, invitation: PairingInvitation, side: String) -> String {
    let key = SymmetricKey(data: SHA256.hash(data: Data(token.utf8)))
    let message = "suzent-mobile-repair-v1:\(side):\(invitation.pairingId):\(invitation.invitation)"
    return HMAC<SHA256>.authenticationCode(for: Data(message.utf8), using: key)
        .map { String(format: "%02x", $0) }.joined()
}

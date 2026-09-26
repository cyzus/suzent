import Foundation
import CryptoKit
import Security

/// Trust received out of band from a desktop QR code, scoped to one connection.
public struct DeviceTrust: Codable, Sendable, Equatable {
    public let version: Int
    public let caCertificate: String
    public let fingerprint: String

    public func evaluate(_ trust: SecTrust, host: String) -> Bool {
        guard let anchor = try? certificate() else { return false }
        guard SecTrustSetPolicies(trust, SecPolicyCreateSSL(true, host as CFString)) == errSecSuccess,
              SecTrustSetAnchorCertificates(trust, [anchor] as CFArray) == errSecSuccess,
              SecTrustSetAnchorCertificatesOnly(trust, true) == errSecSuccess else { return false }
        SecTrustSetNetworkFetchAllowed(trust, false)
        return SecTrustEvaluateWithError(trust, nil)
    }

    public func certificate() throws -> SecCertificate {
        guard version == 1,
              let data = Data(base64Encoded: caCertificate), data.count <= 2048,
              SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == fingerprint,
              let certificate = SecCertificateCreateWithData(nil, data as CFData) else {
            throw PairingError.invalidInvitation
        }
        return certificate
    }
}

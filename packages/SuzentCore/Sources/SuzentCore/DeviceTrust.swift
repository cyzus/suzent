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

    /// Pick the CA whose hash the QR pinned out of the chain a desktop presents.
    public static func fromChain(_ chain: [Data], fingerprint: String) -> DeviceTrust? {
        chain.lazy.map { DeviceTrust(version: 1, caCertificate: $0.base64EncodedString(), fingerprint: fingerprint) }
            .first { (try? $0.certificate()) != nil }
    }

    /// Protocol 3 QR codes carry only the CA fingerprint. The challenge is cancelled once the chain
    /// is read, so no request reaches the desktop before the CA is pinned.
    public static func fetch(origin: String, fingerprint: String) async throws -> DeviceTrust {
        let backend = try Backend(origin)
        let capture = ChainCapture(fingerprint: fingerprint)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 5
        let session = URLSession(configuration: configuration, delegate: capture, delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        _ = try? await session.data(from: backend.url.appendingPathComponent("mobile/capabilities"))
        guard let trust = capture.trust else { throw PairingError.secureConnection }
        return trust
    }
}

private final class ChainCapture: NSObject, URLSessionDelegate, @unchecked Sendable {
    private let fingerprint: String
    private let lock = NSLock()
    private var captured: DeviceTrust?
    var trust: DeviceTrust? { lock.withLock { captured } }

    init(fingerprint: String) { self.fingerprint = fingerprint }

    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        if challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
           let serverTrust = challenge.protectionSpace.serverTrust,
           let chain = SecTrustCopyCertificateChain(serverTrust) as? [SecCertificate] {
            let found = DeviceTrust.fromChain(chain.map { SecCertificateCopyData($0) as Data }, fingerprint: fingerprint)
            lock.withLock { captured = found }
        }
        completionHandler(.cancelAuthenticationChallenge, nil)
    }
}

import CryptoKit
import Foundation

/// The phone's half of `suzent-e2e/1`, the end-to-end encryption between a paired phone and its
/// desktop over a self-hosted relay. docs/08-developing/protocols/relay.md describes the format and
/// packages/mobile-contract/relay-e2e-vectors.json pins it.
public enum RelayCryptoError: Error, Sendable {
    case invalidKey, handshake, authentication, malformed
}

public enum RelayCrypto {
    static let protocolName = Data("suzent-e2e/1".utf8)
    static let pointSize = 65
    static let tagSize = 16

    struct Keys {
        let transcript: Data
        let confirm: SymmetricKey
        let phoneToDesktop: SymmetricKey
        let desktopToPhone: SymmetricKey
    }

    public static func publicKey(_ data: Data) throws -> P256.KeyAgreement.PublicKey {
        guard data.count == pointSize, data.first == 0x04 else { throw RelayCryptoError.invalidKey }
        do { return try P256.KeyAgreement.PublicKey(x963Representation: data) }
        catch { throw RelayCryptoError.invalidKey }
    }

    static func nonce(_ counter: UInt64) throws -> AES.GCM.Nonce {
        var bytes = Data(count: 4)
        withUnsafeBytes(of: counter.bigEndian) { bytes.append(contentsOf: $0) }
        return try AES.GCM.Nonce(data: bytes)
    }

    static func derive(channel: String, staticPublic: Data, phoneEphemeral: Data, desktopEphemeral: Data,
                       es: SharedSecret, ee: SharedSecret) -> Keys {
        var hasher = SHA256()
        hasher.update(data: protocolName)
        hasher.update(data: Data(SHA256.hash(data: Data(channel.utf8))))
        hasher.update(data: staticPublic)
        hasher.update(data: phoneEphemeral)
        hasher.update(data: desktopEphemeral)
        let transcript = Data(hasher.finalize())
        let ikm = es.withUnsafeBytes { Data($0) } + ee.withUnsafeBytes { Data($0) }
        let okm = HKDF<SHA256>.deriveKey(inputKeyMaterial: SymmetricKey(data: ikm), salt: transcript,
                                         info: protocolName + Data(" keys".utf8), outputByteCount: 96)
        let raw = okm.withUnsafeBytes { Data($0) }
        return Keys(transcript: transcript,
                    confirm: SymmetricKey(data: raw.subdata(in: 0..<32)),
                    phoneToDesktop: SymmetricKey(data: raw.subdata(in: 32..<64)),
                    desktopToPhone: SymmetricKey(data: raw.subdata(in: 64..<96)))
    }

    /// Checks the desktop's reply against the static key from the pairing QR code and opens the session.
    public static func finish(ephemeral: P256.KeyAgreement.PrivateKey, staticKey: Data, channel: String,
                              reply: Data) throws -> RelaySession {
        let reply = Data(reply)
        guard reply.count == pointSize + tagSize else { throw RelayCryptoError.handshake }
        let desktopEphemeral = reply.subdata(in: 0..<pointSize)
        let peer = try publicKey(desktopEphemeral)
        let desktopStatic = try publicKey(staticKey)
        let keys = derive(channel: channel, staticPublic: staticKey,
                          phoneEphemeral: ephemeral.publicKey.x963Representation,
                          desktopEphemeral: desktopEphemeral,
                          es: try ephemeral.sharedSecretFromKeyAgreement(with: desktopStatic),
                          ee: try ephemeral.sharedSecretFromKeyAgreement(with: peer))
        do {
            let box = try AES.GCM.SealedBox(nonce: nonce(0), ciphertext: Data(),
                                            tag: reply.subdata(in: pointSize..<reply.count))
            _ = try AES.GCM.open(box, using: keys.confirm, authenticating: keys.transcript)
        } catch { throw RelayCryptoError.handshake }
        return RelaySession(send: keys.phoneToDesktop, receive: keys.desktopToPhone)
    }

    /// The desktop's half. Only tests use it, as a stand-in for the Python implementation.
    static func respond(staticKey: P256.KeyAgreement.PrivateKey, channel: String, first: Data,
                        ephemeral: P256.KeyAgreement.PrivateKey = .init()) throws -> (reply: Data, session: RelaySession) {
        let phone = try publicKey(first)
        let desktopEphemeral = ephemeral.publicKey.x963Representation
        let keys = derive(channel: channel, staticPublic: staticKey.publicKey.x963Representation,
                          phoneEphemeral: first, desktopEphemeral: desktopEphemeral,
                          es: try staticKey.sharedSecretFromKeyAgreement(with: phone),
                          ee: try ephemeral.sharedSecretFromKeyAgreement(with: phone))
        let proof = try AES.GCM.seal(Data(), using: keys.confirm, nonce: nonce(0), authenticating: keys.transcript)
        return (desktopEphemeral + proof.tag, RelaySession(send: keys.desktopToPhone, receive: keys.phoneToDesktop))
    }
}

/// AES-256-GCM in each direction with per-direction message counters as nonces, so a replayed,
/// dropped or reordered message fails to decrypt.
public final class RelaySession: @unchecked Sendable {
    private let sendKey: SymmetricKey
    private let receiveKey: SymmetricKey
    private let lock = NSLock()
    private var sent: UInt64 = 0
    private var received: UInt64 = 0

    init(send: SymmetricKey, receive: SymmetricKey) {
        sendKey = send
        receiveKey = receive
    }

    public func encrypt(_ plaintext: Data) throws -> Data {
        try lock.withLock {
            let box = try AES.GCM.seal(plaintext, using: sendKey, nonce: RelayCrypto.nonce(sent))
            sent += 1
            return box.ciphertext + box.tag
        }
    }

    public func decrypt(_ message: Data) throws -> Data {
        try lock.withLock {
            let message = Data(message)
            guard message.count >= RelayCrypto.tagSize else { throw RelayCryptoError.authentication }
            let split = message.count - RelayCrypto.tagSize
            do {
                let box = try AES.GCM.SealedBox(nonce: RelayCrypto.nonce(received),
                                                ciphertext: message.subdata(in: 0..<split),
                                                tag: message.subdata(in: split..<message.count))
                let plaintext = try AES.GCM.open(box, using: receiveKey)
                received += 1
                return plaintext
            } catch { throw RelayCryptoError.authentication }
        }
    }
}

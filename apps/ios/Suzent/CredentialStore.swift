import Foundation
import Security
import SuzentCore

struct Connection: Codable {
    var origins: [String]? = nil
    var tls: DeviceTrust? = nil
    var previousOrigins: [String]? = nil
    var previousTLS: DeviceTrust? = nil
    var origin: String
    let hostToken: String
    var nodeToken: String = ""
    var clientProtocol: Int? = nil
    var previousToken: String? = nil
    var previousOrigin: String? = nil
}

enum CredentialStore {
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "com.suzent.mobile.connection",
         kSecAttrAccount as String: "primary"]
    }

    static func load() throws -> Connection? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else {
            throw StoreError.failed(status)
        }
        return try JSONDecoder().decode(Connection.self, from: data)
    }

    static func save(_ connection: Connection) throws {
        let data = try JSONEncoder().encode(connection)
        let update = [kSecValueData as String: data]
        let status = SecItemUpdate(query as CFDictionary, update as CFDictionary)
        if status == errSecItemNotFound {
            var item = query
            item[kSecValueData as String] = data
            item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            let added = SecItemAdd(item as CFDictionary, nil)
            guard added == errSecSuccess else { throw StoreError.failed(added) }
        } else if status != errSecSuccess { throw StoreError.failed(status) }
    }

    /// Keychain items outlive app deletion. A reinstall gets a new container, so a credential older
    /// than the container was left by a previous installation; updates keep the container.
    static func clearIfFromPreviousInstall() throws {
        var request = query
        request[kSecReturnAttributes as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return }
        guard status == errSecSuccess, let attributes = result as? [String: Any],
              let saved = attributes[kSecAttrCreationDate as String] as? Date else {
            throw StoreError.failed(status)
        }
        let container = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
        guard let installed = try container.resourceValues(forKeys: [.creationDateKey]).creationDate else { return }
        if saved < installed { try clear() }
    }

    static func clear() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw StoreError.failed(status)
        }
    }

    enum StoreError: Error, LocalizedError {
        case failed(OSStatus)
        var errorDescription: String? { String(localized: "Could not access secure credentials.") }
    }
}

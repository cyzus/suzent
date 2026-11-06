import Foundation
import Security
import SuzentCore

enum CredentialStore {
    private static let desktopsAccount = "desktops"
    /// Written by single-desktop versions; migrated into the list on first load.
    private static let legacyAccount = "primary"

    private static func query(_ account: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "com.suzent.mobile.connection",
         kSecAttrAccount as String: account]
    }

    private static func read(_ account: String) throws -> Data? {
        var request = query(account)
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw StoreError.failed(status) }
        return data
    }

    static func load() throws -> SavedDesktops {
        if let data = try read(desktopsAccount) { return try SavedDesktops.decode(data) }
        guard let legacy = try read(legacyAccount) else { return SavedDesktops() }
        let migrated = try SavedDesktops.decode(legacy)
        try save(migrated)
        try delete(legacyAccount)
        return migrated
    }

    static func save(_ desktops: SavedDesktops) throws {
        guard !desktops.desktops.isEmpty else { try clear(); return }
        let data = try JSONEncoder().encode(desktops)
        let update = [kSecValueData as String: data]
        let status = SecItemUpdate(query(desktopsAccount) as CFDictionary, update as CFDictionary)
        if status == errSecItemNotFound {
            var item = query(desktopsAccount)
            item[kSecValueData as String] = data
            item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            let added = SecItemAdd(item as CFDictionary, nil)
            guard added == errSecSuccess else { throw StoreError.failed(added) }
        } else if status != errSecSuccess { throw StoreError.failed(status) }
    }

    /// Keychain items outlive app deletion. A reinstall gets a new container, so a credential older
    /// than the container was left by a previous installation; updates keep the container.
    static func clearIfFromPreviousInstall() throws {
        let container = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
        guard let installed = try container.resourceValues(forKeys: [.creationDateKey]).creationDate else { return }
        for account in [desktopsAccount, legacyAccount] {
            var request = query(account)
            request[kSecReturnAttributes as String] = true
            request[kSecMatchLimit as String] = kSecMatchLimitOne
            var result: CFTypeRef?
            let status = SecItemCopyMatching(request as CFDictionary, &result)
            if status == errSecItemNotFound { continue }
            guard status == errSecSuccess, let attributes = result as? [String: Any],
                  let saved = attributes[kSecAttrCreationDate as String] as? Date else {
                throw StoreError.failed(status)
            }
            if saved < installed { try delete(account) }
        }
    }

    /// Survives forgetting the connection, and stays on this device, so the desktop can retire
    /// this phone's stale grant when it pairs again.
    static func installationID() throws -> String {
        let installation: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                           kSecAttrService as String: "com.suzent.mobile.connection",
                                           kSecAttrAccount as String: "installation"]
        var request = installation
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data { return String(decoding: data, as: UTF8.self) }
        guard status == errSecItemNotFound else { throw StoreError.failed(status) }
        var bytes = [UInt8](repeating: 0, count: 16)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw StoreError.failed(errSecParam) }
        let id = bytes.map { String(format: "%02x", $0) }.joined()
        var item = installation
        item[kSecValueData as String] = Data(id.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let added = SecItemAdd(item as CFDictionary, nil)
        guard added == errSecSuccess else { throw StoreError.failed(added) }
        return id
    }

    static func clear() throws {
        try delete(desktopsAccount)
        try delete(legacyAccount)
    }

    private static func delete(_ account: String) throws {
        let status = SecItemDelete(query(account) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw StoreError.failed(status) }
    }

    enum StoreError: Error, LocalizedError {
        case failed(OSStatus)
        var errorDescription: String? { String(localized: "Could not access secure credentials.") }
    }
}

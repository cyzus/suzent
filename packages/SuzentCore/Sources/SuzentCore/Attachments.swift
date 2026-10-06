import Foundation

public let maxAttachments = 10

/// A local file staged in the composer, owned by the app until it is sent or removed.
public struct PendingAttachment: Sendable, Identifiable, Equatable {
    public let id: UUID
    public let url: URL
    public let name: String
    public let mimeType: String

    public init(url: URL, name: String, mimeType: String) {
        self.id = UUID()
        self.url = url
        self.name = name
        self.mimeType = mimeType
    }
}

enum MultipartForm {
    /// Streams the form to a temporary file so large videos never sit in memory,
    /// and so the upload carries the Content-Length the backend requires.
    static func write(_ attachments: [PendingAttachment], boundary: String) throws -> URL {
        let target = FileManager.default.temporaryDirectory.appendingPathComponent("upload-\(UUID().uuidString)")
        guard FileManager.default.createFile(atPath: target.path, contents: nil) else { throw ClientError.invalidResponse }
        do {
            let output = try FileHandle(forWritingTo: target)
            defer { try? output.close() }
            for attachment in attachments {
                let name = attachment.name.replacingOccurrences(of: "\"", with: "'")
                    .replacingOccurrences(of: "\r", with: " ").replacingOccurrences(of: "\n", with: " ")
                try output.write(contentsOf: Data((
                    "--\(boundary)\r\n" +
                    "Content-Disposition: form-data; name=\"files\"; filename=\"\(name)\"\r\n" +
                    "Content-Type: \(attachment.mimeType)\r\n\r\n").utf8))
                let input = try FileHandle(forReadingFrom: attachment.url)
                defer { try? input.close() }
                while let chunk = try input.read(upToCount: 1 << 20), !chunk.isEmpty {
                    try output.write(contentsOf: chunk)
                }
                try output.write(contentsOf: Data("\r\n".utf8))
            }
            try output.write(contentsOf: Data("--\(boundary)--\r\n".utf8))
        } catch {
            try? FileManager.default.removeItem(at: target)
            throw error
        }
        return target
    }
}

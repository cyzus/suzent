import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import SuzentCore

/// Copies picked and captured items into a private staging folder: picker grants
/// lapse, and uploads must declare their length and survive a retried send.
enum AttachmentStaging {
    static var directory: URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("attachments", isDirectory: true)
    }

    static func clear() { try? FileManager.default.removeItem(at: directory) }

    static func mimeType(forName name: String) -> String {
        UTType(filenameExtension: (name as NSString).pathExtension)?.preferredMIMEType ?? "application/octet-stream"
    }

    static func copy(_ source: URL, name: String? = nil) throws -> PendingAttachment {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let filename = name ?? source.lastPathComponent
        let target = directory.appendingPathComponent(UUID().uuidString).appendingPathExtension(source.pathExtension)
        try FileManager.default.copyItem(at: source, to: target)
        return PendingAttachment(url: target, name: filename, mimeType: mimeType(forName: filename))
    }

    static func jpeg(_ data: Data, name: String) throws -> PendingAttachment {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let target = directory.appendingPathComponent(UUID().uuidString).appendingPathExtension("jpg")
        try data.write(to: target)
        return PendingAttachment(url: target, name: name, mimeType: "image/jpeg")
    }

    static func timestamp() -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter.string(from: Date())
    }

    static func cameraName(_ fileExtension: String) -> String { "camera-\(timestamp()).\(fileExtension)" }

    /// Photos hands out HEIC; vision models and the desktop expect JPEG.
    static func jpegData(_ data: Data) -> Data? {
        UIImage(data: data)?.jpegData(compressionQuality: 0.85)
    }

    static func load(_ items: [PhotosPickerItem]) async throws -> [PendingAttachment] {
        var staged: [PendingAttachment] = []
        let stamp = "photo-\(timestamp())"
        for (index, item) in items.enumerated() {
            if item.supportedContentTypes.contains(where: { $0.conforms(to: .movie) }),
               let movie = try await item.loadTransferable(type: StagedMovie.self) {
                staged.append(movie.attachment)
            } else if let data = try await item.loadTransferable(type: Data.self), let jpeg = jpegData(data) {
                staged.append(try self.jpeg(jpeg, name: "\(stamp)-\(index + 1).jpg"))
            } else {
                throw CocoaError(.fileReadCorruptFile)
            }
        }
        return staged
    }

    static func load(_ urls: [URL]) throws -> [PendingAttachment] {
        try urls.map { url in
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            return try copy(url)
        }
    }
}

struct StagedMovie: Transferable, Sendable {
    let attachment: PendingAttachment

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .movie) { received in
            StagedMovie(attachment: try AttachmentStaging.copy(received.file))
        }
    }
}

struct CameraPicker: UIViewControllerRepresentable {
    let completion: (PendingAttachment?) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.mediaTypes = [UTType.image.identifier, UTType.movie.identifier]
        picker.videoQuality = .typeHigh
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(completion: completion) }

    @MainActor final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let completion: (PendingAttachment?) -> Void
        init(completion: @escaping (PendingAttachment?) -> Void) { self.completion = completion }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let movie = info[.mediaURL] as? URL {
                completion(try? AttachmentStaging.copy(movie, name: AttachmentStaging.cameraName(movie.pathExtension.isEmpty ? "mov" : movie.pathExtension)))
            } else if let image = info[.originalImage] as? UIImage, let data = image.jpegData(compressionQuality: 0.85) {
                completion(try? AttachmentStaging.jpeg(data, name: AttachmentStaging.cameraName("jpg")))
            } else { completion(nil) }
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { completion(nil) }
    }
}

struct AttachMenu: View {
    var model: MobileModel
    @State private var showCamera = false
    @State private var showPhotos = false
    @State private var showFiles = false
    @State private var photoItems: [PhotosPickerItem] = []

    var body: some View {
        Menu {
            if UIImagePickerController.isSourceTypeAvailable(.camera) {
                Button { showCamera = true } label: { Label("Camera", systemImage: "camera") }
            }
            Button { showPhotos = true } label: { Label("Photos and videos", systemImage: "photo.on.rectangle") }
            Button { showFiles = true } label: { Label("Files", systemImage: "folder") }
        } label: {
            Image(systemName: "plus").font(.system(size: 18, weight: .semibold)).frame(width: 36, height: 44)
        }
        .tint(.primary)
        .accessibilityLabel(String(localized: "Attach"))
        .disabled(model.busy || model.attachments.count >= maxAttachments)
        .photosPicker(isPresented: $showPhotos, selection: $photoItems,
                      maxSelectionCount: max(1, maxAttachments - model.attachments.count),
                      matching: .any(of: [.images, .videos]))
        .onChange(of: photoItems) { _, items in
            guard !items.isEmpty else { return }
            photoItems = []
            Task { await model.stage { try await AttachmentStaging.load(items) } }
        }
        .fileImporter(isPresented: $showFiles, allowedContentTypes: [.item], allowsMultipleSelection: true) { result in
            guard case .success(let urls) = result, !urls.isEmpty else { return }
            Task { await model.stage { try AttachmentStaging.load(urls) } }
        }
        .fullScreenCover(isPresented: $showCamera) {
            CameraPicker { attachment in
                showCamera = false
                if let attachment { Task { await model.stage { [attachment] } } }
            }.ignoresSafeArea()
        }
    }
}

struct AttachmentChip: View {
    let name: String
    let mimeType: String
    var foreground: Color = .primary
    var onRemove: (() -> Void)?

    private var symbol: String {
        if mimeType.hasPrefix("image/") { return "photo" }
        if mimeType.hasPrefix("video/") { return "video" }
        return "doc"
    }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: symbol).font(.system(size: 12))
            Text(name).font(.system(size: 13)).lineLimit(1).truncationMode(.middle).frame(maxWidth: 180, alignment: .leading)
            if let onRemove {
                Button(action: onRemove) { Image(systemName: "xmark").font(.system(size: 11, weight: .bold)) }
                    .buttonStyle(.plain)
                    .accessibilityLabel(String(localized: "Remove \(name)"))
            }
        }
        .foregroundStyle(foreground)
        .padding(.horizontal, 8).padding(.vertical, 4)
        .overlay(Rectangle().strokeBorder(foreground, lineWidth: PresentationTokens.borderWidth))
    }
}

struct PendingAttachmentStrip: View {
    var model: MobileModel

    var body: some View {
        if !model.attachments.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(model.attachments) { attachment in
                        AttachmentChip(name: attachment.name, mimeType: attachment.mimeType) { model.removeAttachment(attachment) }
                            .disabled(model.busy)
                    }
                }
            }
        }
    }
}

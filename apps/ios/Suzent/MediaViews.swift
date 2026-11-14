import AVKit
import ImageIO
import Photos
import SwiftUI
import SuzentCore

/// Fetches a tool's media for the conversation on screen.
struct MediaLoader {
    let load: @MainActor (MediaItem) async -> URL?
}

private struct MediaLoaderKey: EnvironmentKey {
    nonisolated(unsafe) static let defaultValue: MediaLoader? = nil
}

extension EnvironmentValues {
    var mediaLoader: MediaLoader? {
        get { self[MediaLoaderKey.self] }
        set { self[MediaLoaderKey.self] = newValue }
    }
}

/// The images, videos, audio and files a turn's tools made or sent, shown inline like the desktop's result gallery.
struct MediaGallery: View {
    let items: [MediaItem]
    @Environment(\.mediaLoader) private var loader

    var body: some View {
        if let loader, !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(items) { item in
                    if item.kind == "file" { FileRow(item: item, loader: loader) }
                    else { MediaTile(item: item, loader: loader) }
                }
            }
        }
    }
}

/// What the agent handed over with send_file, gathered under the reply as the turn's deliverable.
struct SentFilesSection: View {
    let items: [MediaItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text("Files for you")
                Text(verbatim: "\(items.count)").monospacedDigit()
            }
            .suzentFont(PresentationTokens.typeMeta, weight: .bold, design: .monospaced)
            .textCase(.uppercase).foregroundStyle(Color.suzentMuted)
            .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
            MediaGallery(items: items)
        }
    }
}

/// A sent document or archive: fetched only when the user asks for it, then shared.
private struct FileRow: View {
    let item: MediaItem
    let loader: MediaLoader
    @State private var file: URL?
    @State private var loading = false
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                Text(verbatim: ".\(item.fileExtension)".uppercased())
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(Color.suzentText).lineLimit(1).minimumScaleFactor(0.7)
                    .frame(width: 40, height: 40).background(Color.suzentFileCover(item.fileExtension))
                    .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 1))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.name).suzentFont(PresentationTokens.typeChat, weight: .semibold)
                        .lineLimit(1).truncationMode(.middle)
                    Text(loading ? String(localized: "Loading \(item.name)…") : file == nil ? String(localized: "Tap to download") : String(localized: "Ready to share"))
                        .suzentFont(PresentationTokens.typeMeta).foregroundStyle(Color.suzentMuted).lineLimit(1)
                }
                Spacer(minLength: 0)
                if let file {
                    ShareLink(item: file) { Image(systemName: "square.and.arrow.up").frame(width: 44, height: 44) }
                        .accessibilityLabel(Text("Share \(item.name)"))
                } else if loading {
                    ProgressView().frame(width: 44, height: 44)
                } else {
                    Image(systemName: "arrow.down.circle").frame(width: 44, height: 44).accessibilityHidden(true)
                }
            }
            .padding(.leading, 10).padding(.vertical, 10).padding(.trailing, 4)
            .contentShape(Rectangle())
            .onTapGesture { if file == nil && !loading { download() } }
            .accessibilityElement(children: file == nil ? .ignore : .contain)
            .accessibilityLabel(file == nil ? Text("Download \(item.name)") : Text(item.name))
            .accessibilityAddTraits(file == nil ? .isButton : [])
            .accessibilityAction { if file == nil && !loading { download() } }
            if failed {
                Text(String(localized: "\(item.name) can't be opened. It may have been moved or deleted on your computer."))
                    .suzentFont(PresentationTokens.typeMeta).foregroundStyle(Color.suzentMuted).padding([.horizontal, .bottom], 12)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 1.5))
    }

    private func download() {
        Task {
            loading = true
            failed = false
            file = await loader.load(item)
            failed = file == nil
            loading = false
        }
    }
}

private struct MediaTile: View {
    let item: MediaItem
    let loader: MediaLoader
    @State private var image: UIImage?
    @State private var file: URL?
    @State private var player: AVPlayer?
    @State private var failed = false
    @State private var viewing = false
    @State private var saveNote: String?

    var body: some View {
        content
            .frame(maxWidth: .infinity)
            .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 1))
            .task(id: item.id) { await load() }
            .onDisappear { player?.pause() }
    }

    @ViewBuilder private var content: some View {
        if failed {
            note(String(localized: "\(item.name) can't be opened. It may have been moved or deleted on your computer."))
        } else if let image, let file {
            Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 360)
                .contentShape(Rectangle())
                .onTapGesture { viewing = true }
                .contextMenu {
                    Button { Task { saveNote = await PhotoSaver.saveNote(file) } } label: {
                        Label("Save to Photos", systemImage: "square.and.arrow.down")
                    }
                    ShareLink(item: file) { Label("Share \(item.name)", systemImage: "square.and.arrow.up") }
                }
                .overlay(alignment: .bottom) { SaveNote(text: $saveNote) }
                .accessibilityLabel(Text(item.name))
                .accessibilityHint(Text("Opens full screen. Touch and hold to save or share."))
                .accessibilityAddTraits(.isButton)
                .fullScreenCover(isPresented: $viewing) { ImageViewer(file: file, name: item.name) }
        } else if let player {
            VideoPlayer(player: player).frame(height: item.kind == "audio" ? 80 : 240)
                .accessibilityLabel(Text(item.name))
        } else {
            note(String(localized: "Loading \(item.name)…"))
        }
    }

    private func note(_ text: String) -> some View {
        Text(text).suzentFont(PresentationTokens.typeMeta).foregroundStyle(Color.suzentMuted)
            .lineLimit(2).padding(12).frame(maxWidth: .infinity, alignment: .leading)
    }

    private func load() async {
        guard let file = await loader.load(item) else { failed = true; return }
        if item.kind == "image" {
            self.file = file
            let decoded = await Task.detached(priority: .userInitiated) { downsampledImage(file) }.value
            if let decoded { image = decoded } else { failed = true }
        } else {
            player = AVPlayer(url: file)
        }
    }
}

/// Full screen: pinch or double tap to zoom, drag to pan when zoomed, touch and hold to save or share.
private struct ImageViewer: View {
    let file: URL
    let name: String
    @Environment(\.dismiss) private var dismiss
    @State private var image: UIImage?
    @State private var scale: CGFloat = 1
    @State private var settledScale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var settledOffset: CGSize = .zero
    @State private var saveNote: String?

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let image {
                Image(uiImage: image).resizable().scaledToFit()
                    .scaleEffect(scale).offset(offset)
                    .gesture(zoom.simultaneously(with: pan))
                    .onTapGesture(count: 2) { toggleZoom() }
                    .contextMenu {
                        Button { save() } label: { Label("Save to Photos", systemImage: "square.and.arrow.down") }
                        ShareLink(item: file) { Label("Share \(name)", systemImage: "square.and.arrow.up") }
                    }
                    .accessibilityLabel(Text(name))
                    .accessibilityAction(named: Text("Save to Photos")) { save() }
            } else {
                ProgressView().tint(.white)
            }
        }
        .overlay(alignment: .top) { toolbar }
        .overlay(alignment: .bottom) { SaveNote(text: $saveNote).padding(.bottom, 24) }
        .task { image = await Task.detached(priority: .userInitiated) { downsampledImage(file, maxSide: 2560) }.value }
    }

    private var toolbar: some View {
        HStack(spacing: 4) {
            Button { dismiss() } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }
                .accessibilityLabel(Text("Close"))
            Text(name).suzentFont(PresentationTokens.typeMeta).lineLimit(1).truncationMode(.middle)
            Spacer(minLength: 0)
            Button { save() } label: { Image(systemName: "square.and.arrow.down").frame(width: 44, height: 44) }
                .accessibilityLabel(Text("Save to Photos"))
            ShareLink(item: file) { Image(systemName: "square.and.arrow.up").frame(width: 44, height: 44) }
                .accessibilityLabel(Text("Share \(name)"))
        }
        .foregroundStyle(.white).padding(.horizontal, 8)
    }

    private var zoom: some Gesture {
        MagnifyGesture()
            .onChanged { value in scale = min(max(settledScale * value.magnification, 1), 6) }
            .onEnded { _ in
                settledScale = scale
                if scale == 1 { offset = .zero; settledOffset = .zero }
            }
    }

    private var pan: some Gesture {
        DragGesture()
            .onChanged { value in
                guard scale > 1 else { return }
                offset = CGSize(width: settledOffset.width + value.translation.width,
                                height: settledOffset.height + value.translation.height)
            }
            .onEnded { _ in settledOffset = offset }
    }

    private func toggleZoom() {
        withAnimation(.easeOut(duration: 0.2)) {
            if scale > 1 { scale = 1; offset = .zero } else { scale = 2.5 }
        }
        settledScale = scale
        settledOffset = offset
    }

    private func save() {
        Task { saveNote = await PhotoSaver.saveNote(file) }
    }
}

/// A short confirmation that fades after two seconds.
private struct SaveNote: View {
    @Binding var text: String?

    var body: some View {
        if let text {
            Text(text).suzentFont(PresentationTokens.typeMeta).foregroundStyle(.white)
                .padding(.horizontal, 12).padding(.vertical, 8).background(Color.black.opacity(0.75))
                .padding(8)
                .task(id: text) {
                    try? await Task.sleep(for: .seconds(2))
                    self.text = nil
                }
        }
    }
}

/// Adds an image to the photo library, asking only for add access.
enum PhotoSaver {
    static func save(_ url: URL) async -> Bool {
        let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard status == .authorized || status == .limited else { return false }
        do {
            try await PHPhotoLibrary.shared().performChanges {
                PHAssetCreationRequest.forAsset().addResource(with: .photo, fileURL: url, options: nil)
            }
            return true
        } catch {
            return false
        }
    }

    @MainActor static func saveNote(_ url: URL) async -> String {
        await save(url) ? String(localized: "Saved to Photos") : String(localized: "Couldn't save to Photos")
    }
}

/// Decodes at most about [maxSide] px on the long side, so a large render can't exhaust memory.
private func downsampledImage(_ url: URL, maxSide: Int = 1600) -> UIImage? {
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
    let options: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: maxSide,
    ]
    guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return nil }
    return UIImage(cgImage: image)
}

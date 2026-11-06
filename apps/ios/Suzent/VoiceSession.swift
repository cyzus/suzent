import AVFoundation
import Foundation
import Observation

private final class VoiceCapture: @unchecked Sendable {
    let converter: AVAudioConverter
    let format: AVAudioFormat
    let continuation: AsyncStream<Data>.Continuation
    private var pendingInput: AVAudioPCMBuffer?

    init(input: AVAudioFormat, rate: Double, continuation: AsyncStream<Data>.Continuation) throws {
        guard let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: rate, channels: 1, interleaved: true),
              let converter = AVAudioConverter(from: input, to: format) else { throw VoiceFailure.audio }
        self.format = format
        self.converter = converter
        self.continuation = continuation
    }

    func capture(_ input: AVAudioPCMBuffer) {
        let capacity = AVAudioFrameCount(ceil(Double(input.frameLength) * format.sampleRate / input.format.sampleRate) + 16)
        guard let output = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity) else { return }
        // The tap and converter callback are serial; keep their non-Sendable buffer here.
        pendingInput = input
        var error: NSError?
        converter.convert(to: output, error: &error) { [self] _, status in
            guard let buffer = pendingInput else { status.pointee = .noDataNow; return nil }
            pendingInput = nil
            status.pointee = .haveData
            return buffer
        }
        pendingInput = nil
        guard error == nil, output.frameLength > 0, let samples = output.int16ChannelData?[0] else { return }
        continuation.yield(Data(bytes: samples, count: Int(output.frameLength) * 2))
    }
}

private enum VoiceFailure: Error { case audio, permission, connection }

@MainActor @Observable final class VoiceSession {
    private(set) var active = false
    private(set) var animationState = "idle"
    private(set) var working = false
    private(set) var micLevel = 0.0
    private(set) var status = String(localized: "Connecting voice…")
    private(set) var transcript = ""
    var onError: ((String) -> Void)?
    var onRefresh: (() -> Void)?
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var handshake: Task<Void, Never>?
    @ObservationIgnored private var tapInstalled = false
    @ObservationIgnored private var sender: Task<Void, Never>?
    @ObservationIgnored private var socket: (any MobileSocket)?
    @ObservationIgnored private var engine: AVAudioEngine?
    @ObservationIgnored private var player: AVAudioPlayerNode?
    @ObservationIgnored private var outputFormat: AVAudioFormat?
    @ObservationIgnored private var continuation: AsyncStream<Data>.Continuation?
    @ObservationIgnored private var interruption: NSObjectProtocol?

    func start(prepare: @escaping @MainActor () async throws -> any MobileSocket) {
        guard !active else { return }
        active = true
        animationState = "connecting"
        working = false
        micLevel = 0
        status = String(localized: "Connecting voice…")
        transcript = ""
        task = Task { [weak self] in
            guard let self else { return }
            do {
                guard await AVAudioApplication.requestRecordPermission() else { throw VoiceFailure.permission }
                try Task.checkCancellation()
                let socket = try await prepare()
                try Task.checkCancellation()
                self.socket = socket
                socket.resume()
                handshake = Task { [weak self] in
                    do { try await Task.sleep(for: .seconds(20)) } catch { return }
                    self?.stop()
                    self?.onError?(String(localized: "Voice connection failed. Check voice settings on your desktop and try again."))
                }
                while !Task.isCancelled {
                    switch try await socket.receive() {
                    case .data(let data): play(data)
                    case .string(let text):
                        guard let data = text.data(using: .utf8),
                              let message = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
                        switch message["type"] as? String {
                        case "ready":
                            handshake?.cancel(); handshake = nil
                            guard let input = message["input_sample_rate"] as? Double,
                                  let output = message["output_sample_rate"] as? Double,
                                  (8000...48000).contains(input), (8000...48000).contains(output) else { throw VoiceFailure.audio }
                            try startAudio(inputRate: input, outputRate: output, socket: socket)
                            animationState = "listening"
                            working = message["working"] as? Bool ?? false
                            status = String(localized: "Listening…")
                        case "state":
                            let next = message["state"] as? String ?? "listening"
                            animationState = ["listening", "user_speaking", "thinking", "speaking"].contains(next) ? next : "listening"
                            switch message["state"] as? String {
                            case "speaking": status = String(localized: "Speaking…")
                            case "thinking": status = String(localized: "Thinking…")
                            default: status = String(localized: "Listening…")
                            }
                        case "working":
                            working = message["active"] as? Bool ?? false
                            onRefresh?()
                        case "transcript": transcript = message["text"] as? String ?? ""
                        case "interrupted": player?.stop(); player?.play()
                        case "error": throw VoiceFailure.connection
                        case "closed": stop(); return
                        default: break
                        }
                    @unknown default: break
                    }
                }
            } catch {
                guard !Task.isCancelled else { return }
                let message = (error as? VoiceFailure) == .permission
                    ? String(localized: "Allow microphone access in Settings to use voice.")
                    : String(localized: "Voice connection failed. Check voice settings on your desktop and try again.")
                stop()
                onError?(message)
            }
        }
    }

    private func startAudio(inputRate: Double, outputRate: Double, socket: any MobileSocket) throws {
        guard engine == nil else { return }
        let session = AVAudioSession.sharedInstance()
        var options: AVAudioSession.CategoryOptions = [.defaultToSpeaker]
        #if compiler(>=6.2)
        options.insert(.allowBluetoothHFP)
        #else
        options.insert(.allowBluetooth)
        #endif
        try session.setCategory(.playAndRecord, mode: .voiceChat, options: options)
        try session.setActive(true)
        let engine = AVAudioEngine()
        self.engine = engine
        try engine.inputNode.setVoiceProcessingEnabled(true)
        let stream = AsyncStream<Data>(bufferingPolicy: .bufferingNewest(8)) { continuation = $0 }
        guard let continuation else { throw VoiceFailure.audio }
        let capture = try VoiceCapture(input: engine.inputNode.outputFormat(forBus: 0), rate: inputRate, continuation: continuation)
        engine.inputNode.installTap(onBus: 0, bufferSize: 1024, format: nil) { buffer, _ in capture.capture(buffer) }
        tapInstalled = true
        guard let format = AVAudioFormat(standardFormatWithSampleRate: outputRate, channels: 1) else { throw VoiceFailure.audio }
        outputFormat = format
        let player = AVAudioPlayerNode()
        self.player = player
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: format)
        try engine.start()
        player.play()
        sender = Task { [weak self] in
            do {
                var lastMeter = ContinuousClock.now
                for await chunk in stream {
                    try Task.checkCancellation()
                    if lastMeter.duration(to: .now) >= .milliseconds(80) {
                        var sum = 0.0
                        chunk.withUnsafeBytes { bytes in
                            for offset in stride(from: 0, to: bytes.count - 1, by: 2) {
                                let sample = Double(Int16(littleEndian: bytes.loadUnaligned(fromByteOffset: offset, as: Int16.self))) / 32768
                                sum += sample * sample
                            }
                        }
                        let rms = sqrt(sum / Double(max(1, chunk.count / 2)))
                        self?.micLevel = min(1, max(0, (20 * log10(max(rms, 0.00001)) + 60) / 50))
                        lastMeter = .now
                    }
                    try await socket.send(.data(chunk))
                }
            } catch {
                guard !Task.isCancelled else { return }
                self?.stop()
                self?.onError?(String(localized: "Voice connection failed. Check voice settings on your desktop and try again."))
            }
        }
        interruption = NotificationCenter.default.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.stop() }
        }
    }

    private func play(_ data: Data) {
        guard let format = outputFormat, !data.isEmpty, data.count % 2 == 0,
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(data.count / 2)),
              let samples = buffer.floatChannelData?[0] else { return }
        buffer.frameLength = buffer.frameCapacity
        data.withUnsafeBytes { bytes in
            for index in 0..<Int(buffer.frameLength) {
                let value = bytes.loadUnaligned(fromByteOffset: index * 2, as: Int16.self)
                samples[index] = Float(Int16(littleEndian: value)) / 32768
            }
        }
        player?.scheduleBuffer(buffer)
    }

    func stop() {
        guard active else { return }
        active = false
        animationState = "idle"
        working = false
        micLevel = 0
        task?.cancel(); task = nil
        handshake?.cancel(); handshake = nil
        sender?.cancel(); sender = nil
        continuation?.finish(); continuation = nil
        if tapInstalled { engine?.inputNode.removeTap(onBus: 0); tapInstalled = false }
        engine?.stop(); engine = nil
        player?.stop(); player = nil
        outputFormat = nil
        socket?.cancel(with: .normalClosure, reason: nil); socket = nil
        if let interruption { NotificationCenter.default.removeObserver(interruption) }
        interruption = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        onRefresh?()
    }
}

import Foundation
import Testing
@testable import SuzentCore

@Test func addressesStayBoundToAnOrigin() throws {
    #expect(throws: ClientError.self) { try Backend("http://desktop:25314") }
    for value in ["https://user:secret@desktop", "https://desktop/api", "https://desktop?q=1",
                  "https://desktop#fragment", "file:///etc/passwd", "https://desktop:0"] {
        #expect(throws: (any Error).self) { try Backend(value) }
    }
    let backend = try Backend("http://[::1]:25314/", allowHTTP: true)
    #expect(backend.endpoint("chats").absoluteString == "http://[::1]:25314/chats")
    #expect(backend.webSocketURL.absoluteString == "ws://[::1]:25314/ws/node")
    #expect(try Backend("https://desktop").webSocketURL.absoluteString == "wss://desktop/ws/node")
}

@Test func sharedWireFixtures() throws {
    let fixtureURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("mobile-contract/fixtures.json")
    let fixture = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any])
    var decoder = SSEDecoder()
    let payloads = try #require(fixture["sse"] as? String).components(separatedBy: "\n")
        .compactMap { decoder.consume($0) }
    #expect(payloads.count == 2)
    let event = try JSONDecoder().decode(StreamEvent.self, from: Data(payloads[0].utf8))
    #expect(event.delta == fixture["delta"] as? String)
    var byteDecoder = SSEByteDecoder()
    let bytePayloads = try #require(fixture["sse"] as? String).utf8.compactMap { byteDecoder.consume($0) }
    #expect(bytePayloads == payloads)
    let invoke = try #require(fixture["invoke"] as? [String: Any])
    let result = try #require(NodeProtocol.reply(to: invoke, platform: "ios"))
    #expect(NSDictionary(dictionary: result).isEqual(to: try #require(fixture["result"] as? [String: Any])))
    let connect = NodeProtocol.connect(name: "Suzent Mobile", platform: "ios", token: "")
    #expect(NSDictionary(dictionary: connect).isEqual(to: try #require(fixture["connect"] as? [String: Any])))
}

@Test func rejectUnknownCapabilitiesAndHandleHeartbeat() {
    let result = NodeProtocol.reply(to: ["type": "invoke", "command": "camera.snap", "request_id": "one"], platform: "ios")
    #expect(result?["success"] as? Bool == false)
    #expect(NodeProtocol.reply(to: ["type": "ping"], platform: "ios")?["type"] as? String == "pong")
    #expect(NodeProtocol.reply(to: ["type": "invoke"], platform: "ios") == nil)
}

@Test func partialEventsAreNotDispatched() {
    var decoder = SSEDecoder()
    #expect(decoder.consume(": comment") == nil)
    #expect(decoder.consume("event: update") == nil)
    #expect(decoder.consume("data: incomplete") == nil)
    #expect(decoder.consume("") == "incomplete")
    #expect(decoder.consume("") == nil)
}

@Test func attachmentsDecodeAndStreamAsMultipart() throws {
    let message = try JSONDecoder().decode(ChatMessage.self, from: Data(#"""
        {"role":"user","content":"","files":[{"filename":"photo.jpg","mime_type":"image/jpeg","path":"/workspace/uploads/photo.jpg"}]}
        """#.utf8))
    #expect(message.files == [FileAttachment(filename: "photo.jpg", mimeType: "image/jpeg")])
    #expect(presentMessages([message]).first?.files.count == 1)

    let source = FileManager.default.temporaryDirectory.appendingPathComponent("attachment-\(UUID().uuidString)")
    try Data("abc".utf8).write(to: source)
    defer { try? FileManager.default.removeItem(at: source) }
    let form = try MultipartForm.write([PendingAttachment(url: source, name: "a\"b.txt", mimeType: "text/plain")], boundary: "edge")
    defer { try? FileManager.default.removeItem(at: form) }
    let body = try String(contentsOf: form, encoding: .utf8)
    #expect(body == "--edge\r\nContent-Disposition: form-data; name=\"files\"; filename=\"a'b.txt\"\r\nContent-Type: text/plain\r\n\r\nabc\r\n--edge--\r\n")
}

@Test func sentFilesAreSeparatedFromInlineMedia() throws {
    let a = "0123456789abcdef0123456789abcdef", b = "fedcba9876543210fedcba9876543210"
    let parts = try ["""
    {"type":"tool","toolName":"generate_image","media":[{"id":"\(a)","kind":"image","name":"a.png"}]}
    """, """
    {"type":"tool","toolName":"send_file","media":[{"id":"\(b)","kind":"file","name":"report.pdf"}]}
    """].map { try JSONDecoder().decode(MessagePart.self, from: Data($0.utf8)) }
    #expect(mediaItems(parts).map(\.id) == [a])
    #expect(sentMediaItems(parts).map(\.id) == [b])
}

@Test func toolMediaDecodesLenientlyAndKeepsOnlyValidItems() throws {
    let id = "0123456789abcdef0123456789abcdef"
    let json = """
    {"type":"tool","toolName":"check_video","media":[{"id":"\(id)","kind":"video","name":"clip.MP4"},
     {"id":"../x","kind":"video","name":"bad.mp4"},{"kind":"image"},{"id":"\(id)","kind":"video","name":"clip.MP4"}]}
    """
    let part = try JSONDecoder().decode(MessagePart.self, from: Data(json.utf8))
    #expect(mediaItems([part]) == [MediaItem(id: id, kind: "video", name: "clip.MP4")])
    #expect(mediaItems([part]).first?.fileExtension == "mp4")
    #expect(MediaItem(id: id, kind: "file", name: "a/b.pdf").safeName == "a_b.pdf")
    #expect(MediaItem(id: id, kind: "file", name: "..").safeName == "file.bin")
    #expect(MediaItem(id: id, kind: "file", name: "x").isValid)
}

@Test func attachmentPreviewsSurvivePresentation() throws {
    let message = try JSONDecoder().decode(ChatMessage.self, from: Data(#"""
        {"role":"user","files":[
            {"filename":"photo.png","mime_type":"image/png","media":{"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","kind":"image","name":"photo.png"}},
            {"filename":"bad.png","media":{"id":"../bad","kind":"image","name":"bad.png"}}
        ]}
        """#.utf8))
    #expect(presentMessages([message]).first?.files.first?.media?.kind == "image")
    #expect(message.files[1].media == nil)
}

@Test func regentQueueDistinguishesMissingFromEmptyAndPreservesReasons() throws {
    let decoder = JSONDecoder()
    let old = try decoder.decode(ChatOverview.self, from: Data(#"{"tasks":[],"context":{"categories":[]}}"#.utf8))
    #expect(old.workQueue == nil)
    let empty = try decoder.decode(ChatOverview.self, from: Data(#"{"tasks":[],"context":{"categories":[]},"workQueue":[]}"#.utf8))
    #expect(empty.workQueue == [])
    let active = try decoder.decode(ChatOverview.self, from: Data(#"{"tasks":[],"context":{"categories":[]},"workQueue":[{"chatId":"shared","title":"Ship","state":"waiting","projectName":"Project","waitingKind":"task","waitingReason":"Need access"}]}"#.utf8))
    #expect(active.workQueue?.first?.waitingReason == "Need access")
    #expect(active.workQueue?.first?.id == "shared")
}

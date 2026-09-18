import Foundation
import Testing
@testable import SuzentCore

@Test func sharedRecoveryContract() throws {
    struct Fixture: Decodable {
        let frame: StreamFrame
        let text: String
        let error: Bool
        let ended: Bool
        let persisted: Bool
    }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let fixtures = try JSONDecoder().decode([Fixture].self, from: Data(contentsOf:
        root.appendingPathComponent("mobile-contract/recovery-fixtures.json")))
    var recovery = StreamRecovery()
    var text = ""
    for fixture in fixtures {
        var failed = false
        do {
            for event in try recovery.consume(fixture.frame) {
                if event.type == "STREAM_RESET" { text = "" }
                if event.type == "TEXT_MESSAGE_CONTENT" { text += event.delta ?? "" }
            }
        } catch { failed = true }
        #expect(failed == fixture.error)
        #expect(text == fixture.text)
        #expect(recovery.ended == fixture.ended)
        #expect(recovery.persisted == fixture.persisted)
    }
    let request = try #require(JSONSerialization.jsonObject(with: recovery.request(chatID: "chat")) as? [String: Any])
    #expect(request["protocol"] as? Int == 1)
    #expect(request["run_id"] as? String == "two")
    #expect(request["after_seq"] as? Int == 1)
}

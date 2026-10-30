import Foundation
import Testing
@testable import SuzentCore

@Test func sharedActivityTimingContract() throws {
    struct Fixture: Decodable { let name: String; let messages: [ChatMessage]; let seconds: Int? }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/activity-timing-fixtures.json"))
    for fixture in try JSONDecoder().decode([Fixture].self, from: data) {
        #expect(presentMessages(fixture.messages).last?.workedSeconds == fixture.seconds, "\(fixture.name)")
    }
}

@Test func activityDisclosurePreservesAnswerAndRecognizesFailedEnvelope() {
    let parts = [MessagePart(type: "text", text: "Checking"), MessagePart(type: "tool", toolName: "read_file", output: #"{"success":false,"error":"File missing"}"#, state: "completed"), MessagePart(type: "text", text: "Final answer")]
    #expect(activityFinalStart(parts) == 2)
    #expect(activityFailed(parts[1]))
    #expect(activityDetail(parts[1].output, output: true) == "File missing")
    #expect(activityKind(parts[1]) == "read")
    #expect(activityDuration(65) == "1m 5s")
    #expect(activityDuration(0) == "0s")
    #expect(activityDetail(#"{"message":"Saved","success":true}"#, output: true) == "Saved")
    #expect(activityFinalStart([.init(type: "text", text: "Answer")]) == 0)
}

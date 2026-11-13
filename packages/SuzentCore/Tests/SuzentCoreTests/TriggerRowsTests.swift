import Foundation
import Testing
@testable import SuzentCore

private func rows(_ messages: [String]) throws -> [DisplayMessage] {
    let data = Data("[\(messages.joined(separator: ","))]".utf8)
    return presentMessages(try JSONDecoder().decode([ChatMessage].self, from: data))
}

@Test func readsEachKindOfTrigger() {
    let agent = parseTrigger("[Agent message from Release check 每日 (ea0f)]\n<!-- suzent-agent-inbox:x -->\n## Report\nAll good")
    #expect(agent == ParsedTrigger(kind: .agent, source: "Release check 每日", body: "## Report\nAll good", key: "agent:ea0f", reference: "ea0f"))
    #expect(parseTrigger("**Scheduled Task: Stand-up**\n\nRemind") == ParsedTrigger(kind: .scheduled, source: "Stand-up", body: "Remind", key: "scheduled:Stand-up"))
    #expect(parseTrigger("[Goal mode] Keep going") == ParsedTrigger(kind: .goal, source: "", body: "Keep going", key: "goal"))
    #expect(parseTrigger("**Sub-agent finished**\nResult") == ParsedTrigger(kind: .other, source: "Sub-agent finished", body: "Result", key: "other:Sub-agent finished"))
}

@Test func previewPrefersProseOverHeadings() {
    #expect(triggerPreview("\n---\n- **v0.14.2** shipped [notes](https://x)\nmore") == "v0.14.2 shipped notes")
    #expect(triggerPreview("## Daily report\nAll green") == "All green")
    #expect(triggerPreview("## Daily report") == "Daily report")
}

@Test func repeatsWithNoReplyMergeIntoOneRow() throws {
    let cron = #"{"role":"system_triggered","content":"**Scheduled Task: Check**\n\nDo it"}"#
    let quiet = #"{"role":"assistant","parts":[{"type":"reasoning","text":"thinking"},{"type":"text","text":"HEARTBEAT_OK"}]}"#
    let result = try rows([cron, quiet, cron, quiet, cron, quiet])
    #expect(result.map(\.role) == ["system_triggered"])
    #expect(result.first?.triggers.count == 3)
    #expect(result.first?.messageIndex == 4)
}

@Test func anAnsweredRunMovesOntoItsReply() throws {
    let result = try rows([
        #"{"role":"system_triggered","content":"[Agent message from A (a)]\none"}"#,
        #"{"role":"assistant","content":"HEARTBEAT_OK"}"#,
        #"{"role":"system_triggered","content":"[Agent message from A (a)]\ntwo"}"#,
        #"{"role":"assistant","content":"Done"}"#])
    #expect(result.map(\.role) == ["assistant"])
    #expect(result.first?.triggers.map(\.trigger.body) == ["one", "two"])
    #expect(result.first?.text == "Done")
}

@Test func differentSendersStayApart() throws {
    let result = try rows([
        #"{"role":"system_triggered","content":"[Agent message from A (a)]\none"}"#,
        #"{"role":"assistant","content":"HEARTBEAT_OK"}"#,
        #"{"role":"system_triggered","content":"[Agent message from B (b)]\ntwo"}"#,
        #"{"role":"assistant","content":"HEARTBEAT_OK"}"#])
    #expect(result.map { $0.triggers.map(\.trigger.source) } == [["A"], ["B"]])
}

@Test func aTriggerAnsweredOnlyByAQuietReplyKeepsItsRow() throws {
    let result = try rows([
        #"{"role":"user","content":"hi"}"#,
        #"{"role":"system_triggered","content":"**Scheduled Task: Check**"}"#,
        #"{"role":"assistant","content":"HEARTBEAT_OK"}"#,
        #"{"role":"assistant","content":"Later"}"#])
    #expect(result.map(\.role) == ["user", "system_triggered", "assistant"])
    #expect(result[2].triggers.isEmpty)
}

@Test func aRegentReplyToATriggerNeverReactsToTheUser() {
    let reaction = MessagePart(type: "tool", toolName: "react_to_message", output: #"{"success":true,"metadata":{"regent_reaction":"✅"}}"#, toolCallId: "reaction", state: "completed")
    let user = DisplayMessage(role: "user", parts: [.init(type: "text", text: "hi")], citationSources: [])
    let reply = DisplayMessage(role: "assistant", parts: [reaction, .init(type: "text", text: "Checked")], citationSources: [],
                               triggers: [TriggerEntry(trigger: parseTrigger("**Scheduled Task: Check**"), timestamp: nil)])
    #expect(regentMessages([user, reply]).first?.reaction == nil)
}

import Foundation
import Testing
@testable import SuzentCore

@Test func groupsSurvivePinProjectAndTaskPartitioning() throws {
    struct Fixture: Decodable { let chats: [Chat]; let tasks: [ScheduledTask] }
    let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("mobile-contract/sidebar-group-fixtures.json")
    let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
    let rows = sidebarChats(fixture.chats, search: "", expanded: ["parent", "other"])
    #expect(rows.filter { $0.root.pinned == true }.map(\.id) == ["parent", "child", "grandchild"])
    #expect(rows.filter { $0.root.projectId == "p1" }.map(\.id) == ["parent", "child", "grandchild"])
    #expect(rows.first { $0.id == "other-child" }?.root.pinned == false)
    let groups = scheduledSidebarGroups(fixture.chats, tasks: fixture.tasks, search: "", expanded: ["cron-1", "cron-2"])
    #expect(groups[0].children.map(\.id) == ["cron-child-1"])
    #expect(groups[1].children.map(\.id) == ["cron-child-2"])
    let found = scheduledSidebarGroups(fixture.chats, tasks: fixture.tasks, search: "sources", expanded: [])
    #expect(found.count == 1)
    #expect(found.first?.task?.id == "1")
    #expect(found.first?.root?.id == "cron-1")
    #expect(found.first?.children.map(\.id) == ["cron-child-1"])
    #expect(found.first?.children.first?.depth == 1)
}

@Test func sharedSidebarHierarchyFixtures() throws {
    struct Fixture: Decodable {
        struct Case: Decodable { let search: String; let expanded: [String]; let ids: [String]; let depths: [Int] }
        let chats: [Chat]
        let cases: [Case]
    }
    let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("mobile-contract/sidebar-fixtures.json")
    let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
    for item in fixture.cases {
        let rows = sidebarChats(fixture.chats, search: item.search, expanded: Set(item.expanded))
        #expect(rows.map(\.id) == item.ids)
        #expect(rows.map(\.depth) == item.depths)
    }
    #expect(fixture.chats.first?.isSubagent == true)
    #expect(fixture.chats.last?.isScheduled == true)
    #expect(sidebarChats(fixture.chats, search: "", expanded: []).first?.childCount == 2)
}

@Test func sidebarCyclesRemainVisibleAndFinite() throws {
    let chats = try JSONDecoder().decode([Chat].self, from: Data(#"[{"id":"a","title":"A","platform":"subagent","parentChatId":"b"},{"id":"b","title":"B","platform":"subagent","parentChatId":"a"}]"#.utf8))
    #expect(sidebarChats(chats, search: "", expanded: ["a", "b"]).map(\.id) == ["a", "b"])
}

@Test func taskWithoutConversationIsNotOpenable() throws {
    let task = try JSONDecoder().decode(ScheduledTask.self, from: Data(#"{"id":"7","name":"Report","active":true,"chatId":null,"nextRunAt":null,"lastRunAt":null,"isRunning":false,"hasError":false}"#.utf8))
    #expect(task.chatId == nil)
    #expect(task.nextRunAt == nil)
    #expect(!task.hasError)
}

@Test func scheduledDescendantsStayInTheTaskSection() throws {
    let chats = try JSONDecoder().decode([Chat].self, from: Data(#"[{"id":"cron-1","title":"Report","platform":"cron"},{"id":"child","title":"Check sources","platform":"subagent","parentChatId":"cron-1"},{"id":"regular","title":"Regular"}]"#.utf8))
    #expect(scheduledChatIDs(chats) == ["cron-1", "child"])
}

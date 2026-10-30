import Foundation

/// The conversation surface is shared by network and fully local demonstration clients.
public protocol MobileClient: Sendable {
    func close()
    func clientSession() async throws -> ClientSession
    func chats() async throws -> [Chat]
    func chatPage(_ query: ChatPageQuery, offset: Int, limit: Int) async throws -> ChatPage
    func navigationMetadata() async throws -> NavigationMetadata
    func chatStatuses(_ ids: [String]) async throws -> [Chat]
    func projects() async throws -> [Project]
    func scheduledTasks() async throws -> [ScheduledTask]
    func composer() async throws -> Chat
    func createChat(title: String, projectID: String?) async throws -> Chat
    func chat(_ id: String) async throws -> Chat
    func markRead(_ id: String) async throws
    func manageChat(_ id: String, action: String, value: String?) async throws
    func messageAction(_ id: String, index: Int, action: String, text: String?, model: String?) async throws -> String
    func upload(_ attachments: [PendingAttachment], chatID: String) async throws -> [String]
    func send(_ text: String, chatID: String, model: String?, attachments: [String]) async throws
    func stop(_ chatID: String) async throws
    func approvals(_ id: String) async throws -> ApprovalState
    func decideApprovals(_ id: String, pending: [ApprovalRequest], choices: [String: String]) async throws
    func observe(_ chatID: String, onEvent: @Sendable (StreamEvent) async -> Void) async throws
}

extension SuzentClient: MobileClient {}

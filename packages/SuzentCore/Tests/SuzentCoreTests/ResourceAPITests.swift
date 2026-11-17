import Foundation
import Testing
@testable import SuzentCore

@Test func generatedResourceRequestsKeepWireTypesAndLegacyRoutes() throws {
    let page = try ResourceRequests.chatPage(body: .init(kind: "search", value: "旧会话", offset: 30, limit: 50))
    #expect(page.path(shared: true) == "api/v1/chat-page")
    #expect(page.path(shared: false) == "mobile/client/chat-page")
    let body = try JSONSerialization.jsonObject(with: #require(page.body)) as? [String: Any]
    #expect(body?["offset"] as? Int == 30)
    #expect(body?["limit"] as? Int == 50)
    #expect(body?["value"] as? String == "旧会话")
    let star = try ResourceRequests.starModel(body: .init(model: "openrouter/org/model", starred: false))
    let favorite = try JSONDecoder().decode(WireStarModelRequest.self, from: #require(star.body))
    #expect(favorite.starred == false)
    #expect(favorite.model == "openrouter/org/model")
}

@Test func generatedPathsEncodeOpaqueIdentifiersOnceAtTransportBoundary() throws {
    let backend = try Backend("https://example.com")
    let call = try ResourceRequests.chat(chatId: "chat + 中文%2F")
    #expect(backend.endpoint(call.path).path(percentEncoded: false) == "/api/v1/chats/chat + 中文%2F")
    for value in ["", ".", "..", "one/two"] {
        #expect(throws: ClientError.self) { try ResourceRequests.chat(chatId: value) }
    }
}

@Test func generatedResourceClientDecodesTheCommonResponse() async throws {
    let client = ResourceClient { request in
        #expect(request.path == "api/v1/models")
        #expect(request.method == "GET")
        return Data(#"{"models":["test/model"],"starredModels":[],"canManage":false}"#.utf8)
    }
    let catalog = try await client.models()
    #expect(catalog.models == ["test/model"])
    #expect(catalog.canManage == false)
}

@Test func generatedDTOsPreserveAllowedUnknownFields() throws {
    let source = Data(#"{"id":"chat","title":"Title","futureField":{"enabled":true}}"#.utf8)
    let value = try JSONDecoder().decode(WireApiChat.self, from: source)
    #expect(value.extraFields["futureField"]?["enabled"]?.text == "true")
    let encoded = try JSONEncoder().encode(value)
    let restored = try JSONSerialization.jsonObject(with: encoded) as? [String: Any]
    #expect((restored?["futureField"] as? [String: Bool])?["enabled"] == true)
}

@Test func pollingRequestOmitsModelCatalogWithoutChangingResourcePath() throws {
    let request = try ResourceRequests.chat(chatId: "chat", query: .init(includeModels: false))
    #expect(request.path == "api/v1/chats/chat")
    #expect(request.query == ["include_models": "false"])
    #expect(request.body == nil)
}

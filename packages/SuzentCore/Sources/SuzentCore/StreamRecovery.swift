import Foundation

struct StreamFrame: Decodable {
    let type: String
    let run_id: String
    let seq: Int
    let events: [StreamEvent]?
    let event: StreamEvent?
    let persisted: Bool?
    let superseded: Bool?
}

struct StreamRecovery {
    private(set) var runID: String?
    private(set) var sequence = 0
    private(set) var ended = false
    private(set) var persisted = false
    private(set) var superseded = false

    func request(chatID: String) throws -> Data {
        var body: [String: Any] = ["chat_id": chatID, "wait_ms": 1000, "protocol": 1]
        if let runID { body["run_id"] = runID; body["after_seq"] = sequence }
        return try JSONSerialization.data(withJSONObject: body)
    }

    mutating func consume(_ frame: StreamFrame) throws -> [StreamEvent] {
        guard !frame.run_id.isEmpty, frame.seq >= 0 else { throw ClientError.invalidResponse }
        switch frame.type {
        case "STREAM_SNAPSHOT":
            guard let events = frame.events else { throw ClientError.invalidResponse }
            runID = frame.run_id; sequence = frame.seq
            return [StreamEvent(type: "STREAM_RESET", delta: nil, message: nil)] + events
        case "STREAM_EVENT":
            guard frame.run_id == runID else { throw ClientError.invalidResponse }
            if frame.seq <= sequence { return [] }
            guard frame.seq == sequence + 1, let event = frame.event else { throw ClientError.invalidResponse }
            sequence = frame.seq
            return [event]
        case "STREAM_END":
            guard frame.run_id == runID, frame.seq == sequence else { throw ClientError.invalidResponse }
            ended = true; persisted = frame.persisted == true; superseded = frame.superseded == true
            return []
        default: throw ClientError.invalidResponse
        }
    }
}

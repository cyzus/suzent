package com.suzent.mobile

/**
 * Whether an activity rail is open.
 *
 * A missing choice follows the stream: the rail the agent is in opens, and the
 * others stay shut. Remembering the choice on the conversation, not on the row,
 * keeps a collapse across token updates and across the row leaving the screen.
 * Approval still forces the rail open so the request is not hidden.
 */
fun railExpanded(choice: Boolean?, live: Boolean, current: Boolean, waiting: Boolean): Boolean =
    waiting || (choice ?: (live && current))

/** A new stream gets a new generation so it does not inherit the previous rail's collapse. */
fun nextStreamGeneration(generation: Int, wasStreaming: Boolean, streaming: Boolean): Pair<Int, Boolean> =
    if (streaming && !wasStreaming) (generation + 1) to true else generation to streaming

fun railScope(chatId: String, messageKey: String): String = "$chatId#$messageKey"

fun railChunkKey(chunk: List<MessagePart>, index: Int): String {
    val first = chunk.firstOrNull()
    val stable = first?.toolCallId?.takeIf { it.isNotEmpty() } ?: first?.messageId?.takeIf { it.isNotEmpty() }
    return stable ?: "i$index"
}

/** Choices for one chat. Callers replace the whole object when the chat changes. */
class RailChoices {
    private val values = mutableMapOf<String, Boolean>()

    fun choice(key: String): Boolean? = values[key]

    fun set(key: String, expanded: Boolean) {
        values[key] = expanded
    }
}

enum class ActivityTone { Idle, Streaming, Waiting, Failed }

/**
 * The header speaks for the turn. A failure paints it only when every tool
 * settled in failure. A stream, or a mix of successes and failures, keeps its
 * own color; the failed row carries the error.
 */
fun activityHeaderTone(parts: List<MessagePart>, live: Boolean, current: Boolean): ActivityTone {
    val waiting = parts.any { it.state == "approval-requested" && it.output.isEmpty() }
    val running = live && current && parts.any { it.state == "running" || it.type == "reasoning" }
    if (waiting) return ActivityTone.Waiting
    if (running) return ActivityTone.Streaming
    val tools = parts.filter { it.type == "tool" }
    val failed = tools.count { activityFailed(it) }
    if (tools.isNotEmpty() && failed == tools.size) return ActivityTone.Failed
    return ActivityTone.Idle
}

fun activityItemTone(failed: Boolean, pending: Boolean, active: Boolean): ActivityTone = when {
    failed -> ActivityTone.Failed
    pending -> ActivityTone.Waiting
    active -> ActivityTone.Streaming
    else -> ActivityTone.Idle
}

/** Streaming uses the theme's text color. Link blue is not an activity state. */
fun activityToneToken(tone: ActivityTone): String = when (tone) {
    ActivityTone.Idle -> "muted"
    ActivityTone.Streaming -> "text"
    ActivityTone.Waiting -> "warning"
    ActivityTone.Failed -> "danger"
}

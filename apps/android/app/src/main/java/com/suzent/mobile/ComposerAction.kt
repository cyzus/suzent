package com.suzent.mobile

enum class ComposerAction {
    VOICE, SEND, LOADING, CONNECTING, HANG_UP, STOP;

    companion object {
        fun resolve(hasContent: Boolean, busy: Boolean, running: Boolean, voiceActive: Boolean, voiceConnecting: Boolean): ComposerAction = when {
            voiceActive -> if (voiceConnecting) CONNECTING else HANG_UP
            running -> STOP
            busy -> LOADING
            hasContent -> SEND
            else -> VOICE
        }
    }
}

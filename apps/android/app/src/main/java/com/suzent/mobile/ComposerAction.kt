package com.suzent.mobile

enum class ComposerAction {
    VOICE, SEND, LOADING, CONNECTING, HANG_UP, STOP, QUEUE, REDIRECT;

    companion object {
        /**
         * While a turn runs, typed content is redirected or queued like Enter and Cmd/Ctrl+Enter on desktop;
         * [canRedirect] is false for attachments alone or a desktop without redirects, which leaves queueing.
         */
        fun resolve(hasContent: Boolean, busy: Boolean, running: Boolean, voiceActive: Boolean, voiceConnecting: Boolean,
                    canRedirect: Boolean = false): ComposerAction = when {
            voiceActive -> if (voiceConnecting) CONNECTING else HANG_UP
            running && hasContent && busy -> LOADING
            running && hasContent -> if (canRedirect) REDIRECT else QUEUE
            running -> STOP
            busy -> LOADING
            hasContent -> SEND
            else -> VOICE
        }
    }
}

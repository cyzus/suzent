package com.suzent.mobile

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch

/** Owns a speculative client until the current session can adopt it without interrupting work. */
class ConnectionUpgrade<Candidate>(private val scope: CoroutineScope) {
    private var job: Job? = null

    fun cancel() {
        job?.cancel()
        job = null
    }

    fun start(
        prepare: suspend () -> Candidate,
        isCurrent: () -> Boolean,
        isIdle: () -> Boolean,
        validate: suspend (Candidate) -> Unit,
        install: (Candidate) -> Unit,
        discard: (Candidate) -> Unit,
    ) {
        cancel()
        job = scope.launch {
            try {
                val candidate = prepare()
                var installed = false
                try {
                    ensureActive()
                    while (isCurrent()) {
                        if (isIdle()) {
                            validate(candidate)
                            ensureActive()
                            if (!isCurrent()) return@launch
                            if (isIdle()) {
                                install(candidate)
                                installed = true
                                return@launch
                            }
                        }
                        delay(200)
                        ensureActive()
                    }
                } finally {
                    if (!installed) discard(candidate)
                }
            } catch (failure: CancellationException) { throw failure }
            catch (_: Exception) {
                // An optional route upgrade must never replace a working session's error state.
            }
        }
    }
}

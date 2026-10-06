package com.suzent.mobile

internal fun pairingDeviceName(model: String, readDeviceName: () -> String?): String =
    runCatching { readDeviceName() }.getOrNull()?.trim()?.takeIf { it.isNotEmpty() }
        ?.take(100) ?: model.trim().ifEmpty { "Android" }.take(100)

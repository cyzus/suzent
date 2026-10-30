package com.suzent.mobile

import java.time.OffsetDateTime
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/**
 * Same day → time; same year → abbreviated month, day and time; otherwise a short date.
 * [bestPattern] maps a skeleton such as "MMMdhm" to the locale's pattern
 * (`DateFormat.getBestDateTimePattern` on device).
 */
fun formatTimestamp(raw: String, now: ZonedDateTime, locale: Locale, is24Hour: Boolean,
                    bestPattern: (String) -> String): String = runCatching {
    val time = OffsetDateTime.parse(raw).atZoneSameInstant(now.zone)
    val clock = if (is24Hour) "Hm" else "hm"
    val formatter = when {
        time.toLocalDate() == now.toLocalDate() -> DateTimeFormatter.ofPattern(bestPattern(clock), locale)
        time.year == now.year -> DateTimeFormatter.ofPattern(bestPattern("MMMd$clock"), locale)
        else -> DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT).withLocale(locale)
    }
    time.format(formatter)
}.getOrDefault(raw)

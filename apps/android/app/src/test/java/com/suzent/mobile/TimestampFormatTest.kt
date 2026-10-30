package com.suzent.mobile

import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.Locale

class TimestampFormatTest {
    private val zone = ZoneId.of("Europe/London")
    private val now = ZonedDateTime.of(2026, 10, 30, 18, 0, 0, 0, zone)
    private val patterns = mapOf("Hm" to "HH:mm", "hm" to "h:mm a", "MMMdHm" to "d MMM, HH:mm", "MMMdhm" to "d MMM, h:mm a")

    private fun format(raw: String, is24Hour: Boolean, locale: Locale = Locale.UK) =
        formatTimestamp(raw, now, locale, is24Hour) { patterns.getValue(it) }

    @Test fun sameDayShowsOnlyTheTime() {
        assertEquals("09:05", format("2026-10-30T09:05:00Z", is24Hour = true))
        assertEquals("9:05 am", format("2026-10-30T09:05:00Z", is24Hour = false).lowercase(Locale.ROOT))
    }

    @Test fun sameDayIsJudgedInTheLocalZone() {
        // 23:30 UTC on the 29th is 23:30 London time (GMT after the clocks change), still the previous day.
        assertEquals("29 Oct, 23:30", format("2026-10-29T23:30:00Z", is24Hour = true))
        assertEquals("00:30", format("2026-10-29T23:30:00-01:00", is24Hour = true))
    }

    @Test fun sameYearShowsMonthDayAndTime() {
        assertEquals("3 Feb, 14:07", format("2026-02-03T14:07:00Z", is24Hour = true))
        assertEquals("3 feb, 2:07 pm", format("2026-02-03T14:07:00Z", is24Hour = false).lowercase(Locale.ROOT))
    }

    @Test fun otherYearsShowAShortDate() {
        assertEquals("31/12/2025", format("2025-12-31T10:00:00Z", is24Hour = true))
        assertEquals("12/31/25", format("2025-12-31T10:00:00Z", is24Hour = true, locale = Locale.US))
    }

    @Test fun unparseableInputIsReturnedUnchanged() {
        assertEquals("yesterday", format("yesterday", is24Hour = true))
    }
}

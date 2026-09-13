package com.example.acnotification.notification

import org.junit.Assert.assertEquals
import org.junit.Test

class ReplyCommandTest {

    private fun assertParses(expected: ReplyCommand, vararg replies: String) {
        replies.forEach { assertEquals("\"$it\"", expected, ReplyCommand.parse(it)) }
    }

    @Test
    fun affirmativeRepliesTurnOn() = assertParses(
        ReplyCommand.TURN_ON,
        "Turn on", "yes", "Yes please.", "OK", "turn it on", "Turn on AC", "כן", "תדליק את המזגן"
    )

    @Test
    fun offRepliesTurnOff() = assertParses(ReplyCommand.TURN_OFF, "turn off", "Switch it off.", "תכבה")

    @Test
    fun negativeRepliesDecline() = assertParses(
        ReplyCommand.DECLINE,
        "no", "Not now", "don't turn it on", "No thanks", "לא", "אל תדליק"
    )

    @Test
    fun unclearRepliesAreUnknown() = assertParses(
        ReplyCommand.UNKNOWN,
        "", "   ", "what's the weather", "coffee", "known", "מוכן"
    )
}

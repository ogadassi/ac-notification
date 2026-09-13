package com.example.acnotification.notification

/**
 * Interprets a spoken or typed reply to the AC conversation notification.
 * Android Auto delivers voice replies as transcribed text, so common English and Hebrew phrasings are accepted.
 */
enum class ReplyCommand {
    TURN_ON, TURN_OFF, DECLINE, UNKNOWN;

    companion object {
        // Whole words only: no letter directly before or after (unlike \b, this also works for Hebrew)
        private fun words(vararg phrases: String) = Regex(
            phrases.joinToString("|", prefix = "(?<!\\p{L})(?:", postfix = ")(?!\\p{L})"),
            RegexOption.IGNORE_CASE
        )

        private val OFF_WORDS = words("off", "תכבה", "לכבות", "כבה")
        private val DECLINE_WORDS = words(
            "no", "nope", "nah", "don't", "don’t", "dont", "do not", "not now", "cancel", "later", "stop",
            "לא", "אל תדליק", "עזוב"
        )
        private val ON_WORDS = words(
            "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "please", "on", "do it", "go ahead",
            "כן", "תדליק", "להדליק", "הדלק", "בטח", "יאללה", "סבבה"
        )

        fun parse(reply: CharSequence?): ReplyCommand {
            val text = reply?.trim()?.toString().orEmpty()
            return when {
                text.isEmpty() -> UNKNOWN
                // Checked in this order so "turn it off" and "don't turn it on" never turn the AC on
                OFF_WORDS.containsMatchIn(text) -> TURN_OFF
                DECLINE_WORDS.containsMatchIn(text) -> DECLINE
                ON_WORDS.containsMatchIn(text) -> TURN_ON
                else -> UNKNOWN
            }
        }
    }
}

package com.example.acnotification.util

import android.util.Log
import androidx.compose.runtime.mutableStateListOf
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * In-memory log collector shared across the whole app.
 * Compose observes [entries] directly — no polling needed.
 */
object AppLogger {

    private const val MAX_ENTRIES = 500
    private val fmt = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault())

    /** Compose-observable list — UI recomposes automatically when this changes. */
    val entries = mutableStateListOf<LogEntry>()

    enum class Level { INFO, WARN, ERROR, DEBUG }

    data class LogEntry(
        val time: String,
        val level: Level,
        val tag: String,
        val message: String
    ) {
        val display: String get() = "[$time] ${level.name.padEnd(5)} [$tag] $message"
    }

    fun i(tag: String, msg: String) = add(Level.INFO,  tag, msg).also { Log.i(tag, msg) }
    fun w(tag: String, msg: String) = add(Level.WARN,  tag, msg).also { Log.w(tag, msg) }
    fun e(tag: String, msg: String) = add(Level.ERROR, tag, msg).also { Log.e(tag, msg) }
    fun d(tag: String, msg: String) = add(Level.DEBUG, tag, msg).also { Log.d(tag, msg) }

    var onLogAdded: ((LogEntry) -> Unit)? = null

    fun clear() { entries.clear() }

    private fun add(level: Level, tag: String, msg: String) {
        val entry = LogEntry(fmt.format(Date()), level, tag, msg)
        if (entries.size >= MAX_ENTRIES) entries.removeAt(0)
        entries.add(entry)
        onLogAdded?.invoke(entry)
    }
}

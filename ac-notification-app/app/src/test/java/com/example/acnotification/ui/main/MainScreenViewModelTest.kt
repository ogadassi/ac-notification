package com.example.acnotification.ui.main

import com.example.acnotification.util.AppLogger
import org.junit.Assert.assertEquals
import org.junit.Test

class LogEntryTest {
  @Test
  fun testLogEntryDisplay() {
    val entry = AppLogger.LogEntry(
      time = "10:55:01.123",
      level = AppLogger.Level.INFO,
      tag = "TEST",
      message = "Hello World"
    )
    assertEquals("[10:55:01.123] INFO  [TEST] Hello World", entry.display)
  }
}

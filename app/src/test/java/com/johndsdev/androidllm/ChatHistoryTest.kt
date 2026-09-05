package com.johndsdev.androidllm

import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId

class ChatHistoryTest {
    private val zone = ZoneId.of("America/New_York")
    private val today = LocalDate.of(2026, 9, 5)
    private fun chat(id: String, daysAgo: Long, title: String = id, body: String = "response") =
        ChatSession(id, title, messages = mutableListOf(ChatMessage(
            "assistant", body, today.minusDays(daysAgo).atStartOfDay(zone).toInstant().toEpochMilli(),
        )))

    @Test fun searchesTitlesAndMessagesAndSortsByRecentActivity() {
        val old = chat("old", 8, "Kotlin tips")
        val recent = chat("recent", 0, "Programming", "Use KOTLIN coroutines")
        val unrelated = chat("other", 0)
        assertEquals(listOf(recent, old), ChatHistory.matching(listOf(old, unrelated, recent), " kotlin "))
        assertTrue(ChatHistory.matching(listOf(old), "not found").isEmpty())
    }

    @Test fun groupsByLocalCalendarDaysRatherThanElapsedHours() {
        assertEquals("Today", ChatHistory.group(chat("a", 0), today, zone))
        assertEquals("Yesterday", ChatHistory.group(chat("a", 1), today, zone))
        assertEquals("Previous 7 days", ChatHistory.group(chat("a", 7), today, zone))
        assertEquals("Earlier", ChatHistory.group(chat("a", 8), today, zone))
        assertEquals("New chats", ChatHistory.group(ChatSession("empty", "New chat"), today, zone))
    }

    @Test fun previewIgnoresAnEmptyStreamingPlaceholder() {
        val chat = chat("a", 0, body = "Hello\n  world")
        chat.messages.add(ChatMessage("assistant", ""))
        assertEquals("Hello world", ChatHistory.preview(chat))
    }
}

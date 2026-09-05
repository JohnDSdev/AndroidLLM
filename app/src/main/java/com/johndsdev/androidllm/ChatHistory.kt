package com.johndsdev.androidllm

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

object ChatHistory {
    fun updatedAt(chat: ChatSession): Long = chat.messages.maxOfOrNull { it.timestamp } ?: 0L

    fun matching(chats: List<ChatSession>, query: String): List<ChatSession> {
        val needle = query.trim()
        return chats.filter { chat ->
            needle.isEmpty() || chat.title.contains(needle, ignoreCase = true) ||
                chat.messages.any { it.content.contains(needle, ignoreCase = true) }
        }.sortedByDescending { updatedAt(it) }
    }

    fun group(chat: ChatSession, today: LocalDate, zone: ZoneId): String {
        val timestamp = updatedAt(chat)
        if (timestamp == 0L) return "New chats"
        val date = Instant.ofEpochMilli(timestamp).atZone(zone).toLocalDate()
        return when {
            !date.isBefore(today) -> "Today"
            date == today.minusDays(1) -> "Yesterday"
            !date.isBefore(today.minusDays(7)) -> "Previous 7 days"
            else -> "Earlier"
        }
    }

    fun preview(chat: ChatSession): String = chat.messages.lastOrNull { it.content.isNotBlank() }
        ?.content?.take(180)?.replace(Regex("\\s+"), " ")?.trim() ?: "Start a conversation"
}

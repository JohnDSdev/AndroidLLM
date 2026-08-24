package com.johndsdev.androidllm

data class ChatMessage(
    var role: String,
    var content: String,
    var timestamp: Long = System.currentTimeMillis(),
)

data class ChatSession(
    var id: String,
    var title: String,
    var systemPrompt: String = "You are a helpful assistant.",
    var contextLength: Int = 4096,
    var thinkingEnabled: Boolean = true,
    var modelFile: String? = null,
    val messages: MutableList<ChatMessage> = mutableListOf(),
)

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
    var generationThreads: Int = 4,
    var promptThreads: Int = 6,
    var batchSize: Int = 512,
    var temperature: Float = 0.8f,
    var topK: Int = 40,
    var topP: Float = 0.95f,
    var minP: Float = 0.05f,
    // Kept only for reading old v0.7.x data. GPU PP is disabled in v0.7.2.
    var gpuPromptProcessing: Boolean = false,
    var prettyMode: Boolean = false,
    var modelFile: String? = null,
    val messages: MutableList<ChatMessage> = mutableListOf(),
)

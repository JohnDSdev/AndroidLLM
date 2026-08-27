package com.johndsdev.androidllm

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

class AppStore(private val context: Context) {
    private val dataFile = File(context.filesDir, "data.json")
    val modelsDir: File = File(context.filesDir, "models").apply { mkdirs() }

    val chats: MutableList<ChatSession> = mutableListOf()
    var currentChatId: String? = null
        private set

    init {
        load()
        if (chats.isEmpty()) {
            val chat = makeChat()
            chats += chat
            currentChatId = chat.id
            save()
        } else {
            if (currentChatId == null || chats.none { it.id == currentChatId }) {
                currentChatId = chats.first().id
            }
            // Settings are global. Preserve the settings of the chat the user was
            // actually on, then synchronize them to every other chat.
            synchronizeSettingsFrom(currentChat())
            save()
        }
    }

    fun currentChat(): ChatSession =
        chats.firstOrNull { it.id == currentChatId } ?: chats.first()

    @Synchronized
    fun newChat(): ChatSession {
        val chat = makeChat(currentChat())
        chats.add(0, chat)
        currentChatId = chat.id
        save()
        return chat
    }

    @Synchronized
    fun selectChat(id: String) {
        if (chats.any { it.id == id }) {
            currentChatId = id
            save()
        }
    }

    @Synchronized
    fun deleteChat(id: String) {
        val settings = chats.firstOrNull { it.id == currentChatId } ?: chats.firstOrNull()
        chats.removeAll { it.id == id }
        if (chats.isEmpty()) {
            val replacement = makeChat(settings)
            chats += replacement
            currentChatId = replacement.id
        } else if (currentChatId == id) {
            currentChatId = chats.first().id
        }
        if (settings != null) synchronizeSettingsFrom(settings)
        save()
    }

    /** Commit the settings sheet in one explicit Save action. */
    @Synchronized
    fun applyGlobalSettings(
        systemPrompt: String,
        contextLength: Int,
        thinkingEnabled: Boolean,
        generationThreads: Int,
        promptThreads: Int,
        batchSize: Int,
        temperature: Float,
        topK: Int,
        topP: Float,
        minP: Float,
        prettyMode: Boolean,
    ) {
        val source = currentChat()
        source.systemPrompt = systemPrompt.ifBlank { DEFAULT_SYSTEM_PROMPT }
        source.contextLength = contextLength.coerceIn(512, 131072)
        source.thinkingEnabled = thinkingEnabled
        source.generationThreads = generationThreads.coerceIn(1, 32)
        source.promptThreads = promptThreads.coerceIn(1, 32)
        source.batchSize = batchSize.coerceIn(32, 2048)
        source.temperature = temperature.coerceIn(0f, 2f)
        source.topK = topK.coerceIn(0, 200)
        source.topP = topP.coerceIn(0f, 1f)
        source.minP = minP.coerceIn(0f, 1f)
        source.prettyMode = prettyMode
        source.gpuPromptProcessing = false
        synchronizeSettingsFrom(source)
        save()
    }

    /** Reset is explicit too. Nothing else silently restores defaults. */
    @Synchronized
    fun resetGlobalSettings() {
        applyGlobalSettings(
            systemPrompt = DEFAULT_SYSTEM_PROMPT,
            contextLength = DEFAULT_CONTEXT_LENGTH,
            thinkingEnabled = DEFAULT_THINKING,
            generationThreads = DEFAULT_GENERATION_THREADS,
            promptThreads = DEFAULT_PROMPT_THREADS,
            batchSize = DEFAULT_BATCH_SIZE,
            temperature = DEFAULT_TEMPERATURE,
            topK = DEFAULT_TOP_K,
            topP = DEFAULT_TOP_P,
            minP = DEFAULT_MIN_P,
            prettyMode = DEFAULT_PRETTY_MODE,
        )
    }

    @Synchronized
    fun save() {
        val root = JSONObject()
        root.put("formatVersion", 4)
        root.put("currentChatId", currentChatId)
        val chatArray = JSONArray()
        chats.forEach { chat ->
            val obj = JSONObject()
            obj.put("id", chat.id)
            obj.put("title", chat.title)
            obj.put("systemPrompt", chat.systemPrompt)
            obj.put("contextLength", chat.contextLength)
            obj.put("thinkingEnabled", chat.thinkingEnabled)
            obj.put("generationThreads", chat.generationThreads)
            obj.put("promptThreads", chat.promptThreads)
            obj.put("batchSize", chat.batchSize)
            obj.put("temperature", chat.temperature.toDouble())
            obj.put("topK", chat.topK)
            obj.put("topP", chat.topP.toDouble())
            obj.put("minP", chat.minP.toDouble())
            obj.put("prettyMode", chat.prettyMode)
            obj.put("modelFile", chat.modelFile ?: JSONObject.NULL)
            val messageArray = JSONArray()
            chat.messages.forEach { message ->
                messageArray.put(
                    JSONObject()
                        .put("role", message.role)
                        .put("content", message.content)
                        .put("timestamp", message.timestamp)
                )
            }
            obj.put("messages", messageArray)
            chatArray.put(obj)
        }
        root.put("chats", chatArray)

        val temp = File(dataFile.parentFile, "${dataFile.name}.tmp")
        temp.writeText(root.toString(2))
        if (!temp.renameTo(dataFile)) {
            dataFile.writeText(root.toString(2))
            temp.delete()
        }
    }

    fun dataFile(): File {
        save()
        return dataFile
    }

    private fun load() {
        if (!dataFile.exists()) return
        try {
            val root = JSONObject(dataFile.readText())
            currentChatId = root.optString("currentChatId").takeIf { it.isNotBlank() }
            val chatArray = root.optJSONArray("chats") ?: JSONArray()
            for (i in 0 until chatArray.length()) {
                val obj = chatArray.getJSONObject(i)
                val messages = mutableListOf<ChatMessage>()
                val messageArray = obj.optJSONArray("messages") ?: JSONArray()
                for (j in 0 until messageArray.length()) {
                    val msg = messageArray.getJSONObject(j)
                    messages += ChatMessage(
                        role = msg.optString("role", "user"),
                        content = msg.optString("content", ""),
                        timestamp = msg.optLong("timestamp", 0L),
                    )
                }
                chats += ChatSession(
                    id = obj.optString("id").ifBlank { UUID.randomUUID().toString() },
                    title = obj.optString("title", "New chat"),
                    systemPrompt = obj.optString("systemPrompt", DEFAULT_SYSTEM_PROMPT),
                    contextLength = obj.optInt("contextLength", DEFAULT_CONTEXT_LENGTH).coerceIn(512, 131072),
                    thinkingEnabled = obj.optBoolean("thinkingEnabled", DEFAULT_THINKING),
                    generationThreads = obj.optInt("generationThreads", DEFAULT_GENERATION_THREADS).coerceIn(1, 32),
                    promptThreads = obj.optInt("promptThreads", DEFAULT_PROMPT_THREADS).coerceIn(1, 32),
                    batchSize = obj.optInt("batchSize", DEFAULT_BATCH_SIZE).coerceIn(32, 2048),
                    temperature = obj.optDouble("temperature", DEFAULT_TEMPERATURE.toDouble()).toFloat().coerceIn(0f, 2f),
                    topK = obj.optInt("topK", DEFAULT_TOP_K).coerceIn(0, 200),
                    topP = obj.optDouble("topP", DEFAULT_TOP_P.toDouble()).toFloat().coerceIn(0f, 1f),
                    minP = obj.optDouble("minP", DEFAULT_MIN_P.toDouble()).toFloat().coerceIn(0f, 1f),
                    gpuPromptProcessing = false,
                    prettyMode = obj.optBoolean("prettyMode", DEFAULT_PRETTY_MODE),
                    modelFile = if (obj.isNull("modelFile")) null else obj.optString("modelFile").takeIf { it.isNotBlank() },
                    messages = messages,
                )
            }
        } catch (_: Exception) {
            runCatching {
                dataFile.renameTo(File(context.filesDir, "data-corrupt-${System.currentTimeMillis()}.json"))
            }
            chats.clear()
            currentChatId = null
        }
    }

    private fun synchronizeSettingsFrom(source: ChatSession) {
        chats.forEach { target -> copySettings(source, target) }
    }

    private fun copySettings(source: ChatSession, target: ChatSession) {
        target.systemPrompt = source.systemPrompt
        target.contextLength = source.contextLength
        target.thinkingEnabled = source.thinkingEnabled
        target.generationThreads = source.generationThreads
        target.promptThreads = source.promptThreads
        target.batchSize = source.batchSize
        target.temperature = source.temperature
        target.topK = source.topK
        target.topP = source.topP
        target.minP = source.minP
        target.prettyMode = source.prettyMode
        target.gpuPromptProcessing = false
    }

    private fun makeChat(template: ChatSession? = null) = ChatSession(
        id = UUID.randomUUID().toString(),
        title = "New chat",
    ).also { chat -> if (template != null) copySettings(template, chat) }

    companion object {
        const val DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."
        const val DEFAULT_CONTEXT_LENGTH = 4096
        const val DEFAULT_THINKING = true
        const val DEFAULT_GENERATION_THREADS = 4
        const val DEFAULT_PROMPT_THREADS = 6
        const val DEFAULT_BATCH_SIZE = 512
        const val DEFAULT_TEMPERATURE = 0.8f
        const val DEFAULT_TOP_K = 40
        const val DEFAULT_TOP_P = 0.95f
        const val DEFAULT_MIN_P = 0.05f
        const val DEFAULT_PRETTY_MODE = false
    }
}

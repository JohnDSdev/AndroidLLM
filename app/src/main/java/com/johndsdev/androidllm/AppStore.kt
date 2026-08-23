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
        } else if (currentChatId == null || chats.none { it.id == currentChatId }) {
            currentChatId = chats.first().id
        }
    }

    fun currentChat(): ChatSession =
        chats.firstOrNull { it.id == currentChatId } ?: chats.first()

    @Synchronized
    fun newChat(): ChatSession {
        val chat = makeChat()
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
        chats.removeAll { it.id == id }
        if (chats.isEmpty()) {
            val replacement = makeChat()
            chats += replacement
            currentChatId = replacement.id
        } else if (currentChatId == id) {
            currentChatId = chats.first().id
        }
        save()
    }

    @Synchronized
    fun save() {
        val root = JSONObject()
        root.put("formatVersion", 1)
        root.put("currentChatId", currentChatId)
        val chatArray = JSONArray()
        chats.forEach { chat ->
            val obj = JSONObject()
            obj.put("id", chat.id)
            obj.put("title", chat.title)
            obj.put("systemPrompt", chat.systemPrompt)
            obj.put("contextLength", chat.contextLength)
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
                    systemPrompt = obj.optString("systemPrompt", "You are a helpful assistant."),
                    contextLength = obj.optInt("contextLength", 4096).coerceAtLeast(512),
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

    private fun makeChat() = ChatSession(
        id = UUID.randomUUID().toString(),
        title = "New chat",
    )
}

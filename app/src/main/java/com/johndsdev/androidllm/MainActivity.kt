package com.johndsdev.androidllm

import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.arm.aichat.AiChat
import com.arm.aichat.InferenceEngine
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import java.io.File
import java.util.zip.Deflater
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.math.roundToInt

class MainActivity : AppCompatActivity() {
    private lateinit var store: AppStore
    private lateinit var engine: InferenceEngine

    private lateinit var titleView: TextView
    private lateinit var statusView: TextView
    private lateinit var messageScroll: ScrollView
    private lateinit var messageContainer: LinearLayout
    private lateinit var inputView: EditText
    private lateinit var sendButton: Button
    private lateinit var chatsButton: Button
    private lateinit var newButton: Button
    private lateinit var modelsButton: Button
    private lateinit var menuButton: Button
    private lateinit var exportLauncher: ActivityResultLauncher<String>

    @Volatile private var busy = false
    @Volatile private var loadedModelName: String? = null
    @Volatile private var loadedChatId: String? = null
    @Volatile private var loadedContextLength: Int? = null
    @Volatile private var streamingTextView: TextView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = AppStore(applicationContext)
        engine = AiChat.getInferenceEngine(applicationContext)

        exportLauncher = registerForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
            if (uri != null) exportAllData(uri)
        }

        buildUi()
        renderAll()
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), dp(8), dp(10), dp(8))
        }

        val top = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        chatsButton = compactButton("Chats") { showChatsDialog() }
        newButton = compactButton("New") { createNewChat() }
        modelsButton = compactButton("Model") { showModelsDialog() }
        menuButton = compactButton("Menu") { showMenuDialog() }
        titleView = TextView(this).apply {
            textSize = 18f
            typeface = Typeface.DEFAULT_BOLD
            maxLines = 1
            setPadding(dp(8), 0, dp(8), 0)
        }

        top.addView(chatsButton)
        top.addView(newButton)
        top.addView(titleView, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        top.addView(modelsButton)
        top.addView(menuButton)
        root.addView(top)

        statusView = TextView(this).apply {
            textSize = 12f
            alpha = 0.72f
            setPadding(dp(4), dp(4), dp(4), dp(8))
        }
        root.addView(statusView)

        messageContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(4), dp(4), dp(4), dp(12))
        }
        messageScroll = ScrollView(this).apply {
            isFillViewport = true
            addView(messageContainer)
        }
        root.addView(messageScroll, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            0,
            1f,
        ))

        val composer = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.BOTTOM
        }
        inputView = EditText(this).apply {
            hint = "Message"
            minLines = 1
            maxLines = 6
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            setPadding(dp(12), dp(8), dp(12), dp(8))
        }
        sendButton = Button(this).apply {
            text = "Send"
            setOnClickListener { sendMessage() }
        }
        composer.addView(inputView, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        composer.addView(sendButton)
        root.addView(composer)

        setContentView(root)
    }

    private fun compactButton(label: String, action: () -> Unit) = Button(this).apply {
        text = label
        isAllCaps = false
        minWidth = 0
        minimumWidth = 0
        setPadding(dp(9), 0, dp(9), 0)
        setOnClickListener { action() }
    }

    private fun renderAll() {
        renderHeader()
        renderMessages()
        updateControls()
    }

    private fun renderHeader() {
        val chat = store.currentChat()
        titleView.text = chat.title
        val selected = chat.modelFile ?: "none"
        val loaded = loadedModelName ?: "unloaded"
        statusView.text = "selected: $selected  •  loaded: $loaded  •  context: ${chat.contextLength}"
    }

    private fun renderMessages() {
        streamingTextView = null
        messageContainer.removeAllViews()
        val messages = store.currentChat().messages
        if (messages.isEmpty()) {
            messageContainer.addView(TextView(this).apply {
                text = "No messages yet. Pick a GGUF model, then start typing. Everything stays on-device."
                textSize = 15f
                alpha = 0.65f
                setPadding(dp(8), dp(24), dp(8), dp(8))
            })
        } else {
            messages.forEachIndexed { index, message ->
                val wrapper = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding(dp(8), dp(8), dp(8), dp(10))
                }
                val label = TextView(this).apply {
                    text = if (message.role == "assistant") "assistant" else "you"
                    textSize = 12f
                    typeface = Typeface.DEFAULT_BOLD
                    alpha = 0.62f
                }
                val body = TextView(this).apply {
                    text = message.content
                    textSize = 16f
                    setTextIsSelectable(true)
                }
                wrapper.addView(label)
                wrapper.addView(body)
                messageContainer.addView(wrapper)
                if (busy && index == messages.lastIndex && message.role == "assistant") {
                    streamingTextView = body
                }
            }
        }
        messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
    }

    private fun updateControls() {
        sendButton.isEnabled = !busy
        chatsButton.isEnabled = !busy
        newButton.isEnabled = !busy
        modelsButton.isEnabled = !busy
        menuButton.isEnabled = !busy
        inputView.isEnabled = !busy
    }

    private fun setBusy(value: Boolean, message: String? = null) {
        busy = value
        runOnUiThread {
            updateControls()
            if (message != null) statusView.text = message else renderHeader()
        }
    }

    private fun createNewChat() {
        if (busy) return
        store.newChat()
        loadedChatId = null
        renderAll()
    }

    private fun showChatsDialog() {
        val chats = store.chats.toTypedArray()
        val labels = chats.map { chat ->
            buildString {
                append(chat.title)
                if (chat.id == store.currentChatId) append("  • current")
            }
        }.toTypedArray()

        AlertDialog.Builder(this)
            .setTitle("Chats")
            .setItems(labels) { _, which ->
                store.selectChat(chats[which].id)
                loadedChatId = null
                renderAll()
            }
            .setNeutralButton("Delete current") { _, _ ->
                val current = store.currentChat()
                AlertDialog.Builder(this)
                    .setTitle("Delete chat?")
                    .setMessage(current.title)
                    .setPositiveButton("Delete") { _, _ ->
                        store.deleteChat(current.id)
                        loadedChatId = null
                        renderAll()
                    }
                    .setNegativeButton("Cancel", null)
                    .show()
            }
            .setNegativeButton("Close", null)
            .show()
    }

    private fun showMenuDialog() {
        val items = arrayOf("Chat settings", "Export all data", "Unload model")
        AlertDialog.Builder(this)
            .setTitle("AndroidLLM")
            .setItems(items) { _, which ->
                when (which) {
                    0 -> showSettingsDialog()
                    1 -> exportLauncher.launch("AndroidLLM-export.zip")
                    2 -> unloadModelAsync()
                }
            }
            .show()
    }

    private fun showSettingsDialog() {
        val chat = store.currentChat()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), 0)
        }
        val systemLabel = TextView(this).apply {
            text = "System prompt"
            typeface = Typeface.DEFAULT_BOLD
        }
        val systemInput = EditText(this).apply {
            setText(chat.systemPrompt)
            minLines = 3
            maxLines = 9
            gravity = Gravity.TOP
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        val contextLabel = TextView(this).apply {
            text = "Context length"
            typeface = Typeface.DEFAULT_BOLD
            setPadding(0, dp(12), 0, 0)
        }
        val contextInput = EditText(this).apply {
            setText(chat.contextLength.toString())
            inputType = InputType.TYPE_CLASS_NUMBER
        }
        val hint = TextView(this).apply {
            text = "512–131072 tokens. Higher values use substantially more RAM and may fail if the phone cannot allocate the KV cache."
            textSize = 12f
            alpha = 0.65f
        }
        box.addView(systemLabel)
        box.addView(systemInput)
        box.addView(contextLabel)
        box.addView(contextInput)
        box.addView(hint)

        val dialog = AlertDialog.Builder(this)
            .setTitle("Chat settings")
            .setView(box)
            .setPositiveButton("Save", null)
            .setNegativeButton("Cancel", null)
            .create()

        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val context = contextInput.text.toString().toIntOrNull()
                if (context == null || context !in 512..131072) {
                    contextInput.error = "Enter a value from 512 to 131072"
                    return@setOnClickListener
                }
                chat.systemPrompt = systemInput.text.toString().ifBlank { "You are a helpful assistant." }
                chat.contextLength = context
                store.save()
                loadedChatId = null
                loadedContextLength = null
                dialog.dismiss()
                renderAll()
            }
        }
        dialog.show()
    }

    private fun showModelsDialog() {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(6), dp(14), dp(6))
        }

        val download = Button(this).apply {
            text = "Download GGUF from URL"
            isAllCaps = false
        }
        box.addView(download)

        val unload = Button(this).apply {
            text = "Unload current model"
            isAllCaps = false
            isEnabled = loadedModelName != null || engine.state.value is InferenceEngine.State.ModelReady
        }
        box.addView(unload)

        val files = modelFiles()
        if (files.isEmpty()) {
            box.addView(TextView(this).apply {
                text = "No downloaded models yet."
                alpha = 0.65f
                setPadding(dp(8), dp(14), dp(8), dp(14))
            })
        } else {
            box.addView(TextView(this).apply {
                text = "Downloaded models"
                typeface = Typeface.DEFAULT_BOLD
                setPadding(dp(6), dp(12), dp(6), dp(4))
            })
            files.forEach { file ->
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                }
                val load = Button(this).apply {
                    text = buildString {
                        if (store.currentChat().modelFile == file.name) append("✓ ")
                        append(file.name)
                        append("\n")
                        append(formatBytes(file.length()))
                    }
                    isAllCaps = false
                    gravity = Gravity.START or Gravity.CENTER_VERTICAL
                }
                val delete = Button(this).apply {
                    text = "Delete"
                    isAllCaps = false
                }
                row.addView(load, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                row.addView(delete)
                box.addView(row)

                load.setOnClickListener {
                    currentModelDialog?.dismiss()
                    selectAndLoadModel(file)
                }
                delete.setOnClickListener {
                    confirmDeleteModel(file)
                }
            }
        }

        val scroll = ScrollView(this).apply { addView(box) }
        val dialog = AlertDialog.Builder(this)
            .setTitle("Models")
            .setView(scroll)
            .setNegativeButton("Close", null)
            .create()
        currentModelDialog = dialog
        download.setOnClickListener {
            dialog.dismiss()
            showDownloadDialog()
        }
        unload.setOnClickListener {
            dialog.dismiss()
            unloadModelAsync()
        }
        dialog.setOnDismissListener { if (currentModelDialog === dialog) currentModelDialog = null }
        dialog.show()
    }

    private var currentModelDialog: AlertDialog? = null

    private fun showDownloadDialog() {
        val input = EditText(this).apply {
            hint = "https://…/model.gguf"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine(false)
            minLines = 2
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(4), dp(20), 0)
            addView(TextView(this@MainActivity).apply {
                text = "Paste a direct GGUF download link. Hugging Face resolve/download links work when they point directly to the file."
                textSize = 13f
                alpha = 0.7f
                setPadding(0, 0, 0, dp(8))
            })
            addView(input)
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle("Download model")
            .setView(box)
            .setPositiveButton("Download", null)
            .setNegativeButton("Cancel", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val url = input.text.toString().trim()
                if (!url.startsWith("http://") && !url.startsWith("https://")) {
                    input.error = "Paste a direct http(s) URL"
                    return@setOnClickListener
                }
                dialog.dismiss()
                downloadModel(url)
            }
        }
        dialog.show()
    }

    private fun downloadModel(url: String) {
        if (busy) return
        setBusy(true, "Starting model download…")
        Thread {
            try {
                val file = ModelDownloader.download(url, store.modelsDir) { progress ->
                    val text = if (progress.total > 0) {
                        val percent = (progress.downloaded.toDouble() / progress.total.toDouble() * 100.0).roundToInt()
                        "Downloading model… $percent%  (${formatBytes(progress.downloaded)} / ${formatBytes(progress.total)})"
                    } else {
                        "Downloading model… ${formatBytes(progress.downloaded)}"
                    }
                    runOnUiThread { statusView.text = text }
                }
                runOnUiThread {
                    Toast.makeText(this, "Downloaded ${file.name}", Toast.LENGTH_LONG).show()
                    setBusy(false)
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    setBusy(false)
                    showError("Model download failed", t)
                }
            }
        }.start()
    }

    private fun confirmDeleteModel(file: File) {
        AlertDialog.Builder(this)
            .setTitle("Delete model?")
            .setMessage("${file.name}\n${formatBytes(file.length())}")
            .setPositiveButton("Delete") { _, _ ->
                if (loadedModelName == file.name) {
                    Toast.makeText(this, "Unload this model first.", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                if (file.delete()) {
                    store.chats.filter { it.modelFile == file.name }.forEach { it.modelFile = null }
                    store.save()
                    currentModelDialog?.dismiss()
                    renderAll()
                    showModelsDialog()
                } else {
                    Toast.makeText(this, "Could not delete model.", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun selectAndLoadModel(file: File) {
        val chat = store.currentChat()
        chat.modelFile = file.name
        store.save()
        loadedChatId = null
        renderHeader()
        setBusy(true, "Loading ${file.name}…")
        Thread {
            try {
                ensureModelLoaded(chat)
                runOnUiThread {
                    setBusy(false)
                    Toast.makeText(this, "Model loaded", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    setBusy(false)
                    showError("Could not load model", t)
                }
            }
        }.start()
    }

    private fun unloadModelAsync() {
        if (busy) return
        setBusy(true, "Unloading model…")
        Thread {
            try {
                unloadModelBlocking()
                runOnUiThread {
                    setBusy(false)
                    Toast.makeText(this, "Model unloaded", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    setBusy(false)
                    showError("Could not unload model", t)
                }
            }
        }.start()
    }

    private fun sendMessage() {
        if (busy) return
        val text = inputView.text.toString().trim()
        if (text.isBlank()) return
        val chat = store.currentChat()
        if (chat.modelFile == null) {
            Toast.makeText(this, "Choose or download a model first.", Toast.LENGTH_SHORT).show()
            showModelsDialog()
            return
        }

        inputView.setText("")
        setBusy(true, "Preparing model…")
        Thread {
            var assistant: ChatMessage? = null
            try {
                ensureModelLoaded(chat)

                val userMessage = ChatMessage("user", text)
                assistant = ChatMessage("assistant", "")
                chat.messages += userMessage
                chat.messages += assistant!!
                if (chat.title == "New chat") {
                    chat.title = text.replace("\n", " ").take(42).ifBlank { "New chat" }
                }
                store.save()

                runOnUiThread {
                    renderHeader()
                    renderMessages()
                    statusView.text = "Generating…"
                }

                val buffer = StringBuilder()
                var lastUi = 0L
                runBlocking {
                    engine.sendUserPrompt(text).collect { token ->
                        buffer.append(token)
                        assistant!!.content = buffer.toString()
                        val now = System.currentTimeMillis()
                        if (now - lastUi >= 55) {
                            val snapshot = buffer.toString()
                            runOnUiThread {
                                streamingTextView?.text = snapshot
                                messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
                            }
                            lastUi = now
                        }
                    }
                }
                assistant!!.content = buffer.toString()
                store.save()
                runOnUiThread {
                    setBusy(false)
                    renderAll()
                }
            } catch (t: Throwable) {
                if (assistant != null && assistant!!.content.isBlank()) {
                    assistant!!.content = "[generation failed: ${friendlyMessage(t)}]"
                    store.save()
                }
                runOnUiThread {
                    setBusy(false)
                    renderAll()
                    showError("Generation failed", t)
                }
            }
        }.start()
    }

    private fun ensureModelLoaded(chat: ChatSession) {
        val name = chat.modelFile ?: error("No model selected")
        val file = File(store.modelsDir, name)
        require(file.exists() && file.isFile) { "Model file is missing: $name" }

        if (
            loadedModelName == name &&
            loadedChatId == chat.id &&
            loadedContextLength == chat.contextLength &&
            engine.state.value is InferenceEngine.State.ModelReady
        ) {
            return
        }

        unloadModelBlocking()
        waitForNativeInitialization()

        runOnUiThread { statusView.text = "Loading $name with ${chat.contextLength} context…" }
        runBlocking {
            engine.loadModel(file.absolutePath, chat.contextLength)
            engine.setSystemPrompt(effectiveSystemPrompt(chat))
        }

        loadedModelName = name
        loadedChatId = chat.id
        loadedContextLength = chat.contextLength
        runOnUiThread { renderHeader() }
    }

    private fun waitForNativeInitialization() {
        val state = engine.state.value
        if (state is InferenceEngine.State.Initialized) return
        if (state is InferenceEngine.State.Error) {
            engine.cleanUp()
            return
        }
        if (state is InferenceEngine.State.ModelReady) return

        val resolved = runBlocking {
            withTimeout(60_000L) {
                engine.state.first {
                    it is InferenceEngine.State.Initialized ||
                        it is InferenceEngine.State.ModelReady ||
                        it is InferenceEngine.State.Error
                }
            }
        }
        if (resolved is InferenceEngine.State.Error) throw resolved.exception
    }

    private fun unloadModelBlocking() {
        when (val state = engine.state.value) {
            is InferenceEngine.State.ModelReady,
            is InferenceEngine.State.Error -> engine.cleanUp()
            is InferenceEngine.State.Initialized,
            is InferenceEngine.State.Uninitialized,
            is InferenceEngine.State.Initializing -> Unit
            else -> error("Model is busy: ${state.javaClass.simpleName}")
        }
        loadedModelName = null
        loadedChatId = null
        loadedContextLength = null
    }

    private fun effectiveSystemPrompt(chat: ChatSession): String {
        val base = chat.systemPrompt.ifBlank { "You are a helpful assistant." }
        if (chat.messages.isEmpty()) return base

        val transcript = buildString {
            chat.messages.forEach { message ->
                append(if (message.role == "assistant") "Assistant: " else "User: ")
                append(message.content)
                append("\n\n")
            }
        }

        val historyBudgetChars = (chat.contextLength * 3)
            .coerceAtLeast(2_000)
            .coerceAtMost(180_000)
        val clipped = transcript.takeLast(historyBudgetChars)
        return buildString {
            append(base)
            append("\n\nThe model context was reloaded. Below is the recent conversation history. Continue the conversation naturally and do not mention this restoration note unless asked.\n\n")
            append(clipped)
        }
    }

    private fun exportAllData(uri: Uri) {
        if (busy) return
        setBusy(true, "Exporting app data…")
        Thread {
            try {
                val data = store.dataFile()
                val output = contentResolver.openOutputStream(uri, "w") ?: error("Could not open export destination")
                ZipOutputStream(output.buffered(1024 * 1024)).use { zip ->
                    zip.setLevel(Deflater.NO_COMPRESSION)
                    zip.putNextEntry(ZipEntry("data.json"))
                    data.inputStream().use { it.copyTo(zip, 1024 * 1024) }
                    zip.closeEntry()

                    modelFiles().forEachIndexed { index, model ->
                        runOnUiThread {
                            statusView.text = "Exporting model ${index + 1}/${modelFiles().size}: ${model.name}"
                        }
                        zip.putNextEntry(ZipEntry("models/${model.name}"))
                        model.inputStream().buffered(1024 * 1024).use { it.copyTo(zip, 1024 * 1024) }
                        zip.closeEntry()
                    }
                }
                runOnUiThread {
                    setBusy(false)
                    Toast.makeText(this, "Export complete", Toast.LENGTH_LONG).show()
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    setBusy(false)
                    showError("Export failed", t)
                }
            }
        }.start()
    }

    private fun modelFiles(): List<File> =
        store.modelsDir.listFiles()
            ?.filter { it.isFile && it.extension.equals("gguf", ignoreCase = true) }
            ?.sortedBy { it.name.lowercase() }
            ?: emptyList()

    private fun formatBytes(bytes: Long): String {
        if (bytes < 1024) return "$bytes B"
        val units = arrayOf("KB", "MB", "GB", "TB")
        var value = bytes.toDouble()
        var index = -1
        do {
            value /= 1024.0
            index++
        } while (value >= 1024.0 && index < units.lastIndex)
        return if (value >= 100) "%.0f %s".format(value, units[index]) else "%.1f %s".format(value, units[index])
    }

    private fun showError(title: String, throwable: Throwable) {
        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(friendlyMessage(throwable))
            .setPositiveButton("OK", null)
            .show()
    }

    private fun friendlyMessage(throwable: Throwable): String {
        var current: Throwable? = throwable
        var last = throwable
        while (current != null) {
            last = current
            current = current.cause
        }
        return last.message?.takeIf { it.isNotBlank() } ?: last.javaClass.simpleName
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()
}

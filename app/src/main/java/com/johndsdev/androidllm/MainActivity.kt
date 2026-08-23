package com.johndsdev.androidllm

import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.arm.aichat.AiChat
import com.arm.aichat.InferenceEngine
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
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
    private lateinit var headerSubtitle: TextView
    private lateinit var modelNameView: TextView
    private lateinit var contextView: TextView
    private lateinit var statusContainer: LinearLayout
    private lateinit var statusView: TextView
    private lateinit var downloadProgress: ProgressBar
    private lateinit var modelCard: MaterialCardView
    private lateinit var messageScroll: ScrollView
    private lateinit var messageContainer: LinearLayout
    private lateinit var inputView: EditText
    private lateinit var sendButton: ImageButton
    private lateinit var chatsButton: ImageButton
    private lateinit var newButton: ImageButton
    private lateinit var menuButton: ImageButton
    private lateinit var exportLauncher: ActivityResultLauncher<String>

    @Volatile private var busy = false
    @Volatile private var loadedModelName: String? = null
    @Volatile private var loadedChatId: String? = null
    @Volatile private var loadedContextLength: Int? = null
    @Volatile private var streamingTextView: TextView? = null
    private var currentModelDialog: androidx.appcompat.app.AlertDialog? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = AppStore(applicationContext)
        engine = AiChat.getInferenceEngine(applicationContext)

        exportLauncher = registerForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
            if (uri != null) exportAllData(uri)
        }

        bindUi()
        renderAll()
    }

    private fun bindUi() {
        setContentView(R.layout.activity_main)
        titleView = findViewById(R.id.titleView)
        headerSubtitle = findViewById(R.id.headerSubtitle)
        modelNameView = findViewById(R.id.modelNameView)
        contextView = findViewById(R.id.contextView)
        statusContainer = findViewById(R.id.statusContainer)
        statusView = findViewById(R.id.statusView)
        downloadProgress = findViewById(R.id.downloadProgress)
        modelCard = findViewById(R.id.modelCard)
        messageScroll = findViewById(R.id.messageScroll)
        messageContainer = findViewById(R.id.messageContainer)
        inputView = findViewById(R.id.inputView)
        sendButton = findViewById(R.id.sendButton)
        chatsButton = findViewById(R.id.chatsButton)
        newButton = findViewById(R.id.newButton)
        menuButton = findViewById(R.id.menuButton)

        chatsButton.setOnClickListener { showChatsDialog() }
        newButton.setOnClickListener { createNewChat() }
        menuButton.setOnClickListener { showMenuDialog() }
        modelCard.setOnClickListener { showModelsDialog() }
        sendButton.setOnClickListener { sendMessage() }
        inputView.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                sendMessage()
                true
            } else {
                false
            }
        }
    }

    private fun renderAll() {
        renderHeader()
        renderMessages()
        updateControls()
    }

    private fun renderHeader() {
        val chat = store.currentChat()
        titleView.text = chat.title
        modelNameView.text = chat.modelFile ?: "Choose a GGUF model"
        contextView.text = "${formatContext(chat.contextLength)} ctx"

        headerSubtitle.text = when {
            loadedModelName == chat.modelFile && loadedChatId == chat.id && loadedModelName != null ->
                "On-device • model loaded"
            chat.modelFile != null -> "On-device • model selected"
            else -> "On-device • CPU only"
        }
    }

    private fun renderMessages() {
        streamingTextView = null
        messageContainer.removeAllViews()
        val messages = store.currentChat().messages

        if (messages.isEmpty()) {
            messageContainer.gravity = Gravity.CENTER
            val empty = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setPadding(dp(24), dp(48), dp(24), dp(48))
            }
            empty.addView(TextView(this).apply {
                text = "No messages yet"
                textSize = 22f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                setTextColor(color(R.color.text_primary))
            })
            empty.addView(TextView(this).apply {
                text = "Choose a GGUF model above, then start a local chat.\nEverything stays on this device."
                textSize = 14f
                gravity = Gravity.CENTER
                setTextColor(color(R.color.text_secondary))
                setPadding(0, dp(8), 0, 0)
            })
            messageContainer.addView(
                empty,
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.MATCH_PARENT,
                ),
            )
        } else {
            messageContainer.gravity = Gravity.TOP
            val maxBubbleWidth = (resources.displayMetrics.widthPixels * 0.84f).roundToInt()
            messages.forEachIndexed { index, message ->
                val fromUser = message.role != "assistant"
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = if (fromUser) Gravity.END else Gravity.START
                    setPadding(0, dp(5), 0, dp(5))
                }

                val card = MaterialCardView(this).apply {
                    radius = dp(20).toFloat()
                    cardElevation = 0f
                    strokeWidth = if (fromUser) 0 else dp(1)
                    strokeColor = color(R.color.divider)
                    setCardBackgroundColor(color(if (fromUser) R.color.user_bubble else R.color.assistant_bubble))
                }
                val body = TextView(this).apply {
                    text = message.content
                    textSize = 16f
                    maxWidth = maxBubbleWidth
                    setTextColor(color(if (fromUser) R.color.user_text else R.color.assistant_text))
                    setTextIsSelectable(true)
                    setPadding(dp(15), dp(11), dp(15), dp(11))
                }
                card.addView(body)
                row.addView(card, LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                ))
                messageContainer.addView(row, LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                ))

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
        menuButton.isEnabled = !busy
        modelCard.isEnabled = !busy
        inputView.isEnabled = !busy
        sendButton.alpha = if (busy) 0.45f else 1f
    }

    private fun setBusy(value: Boolean, message: String? = null) {
        busy = value
        runOnUiThread {
            updateControls()
            showStatus(message)
            renderHeader()
        }
    }

    private fun showStatus(message: String?, progress: Int? = null, indeterminate: Boolean = false) {
        if (message.isNullOrBlank()) {
            statusContainer.visibility = View.GONE
            downloadProgress.visibility = View.GONE
            return
        }

        statusContainer.visibility = View.VISIBLE
        statusView.text = message
        if (progress != null || indeterminate) {
            downloadProgress.visibility = View.VISIBLE
            downloadProgress.isIndeterminate = indeterminate || progress == null
            if (progress != null) downloadProgress.progress = progress.coerceIn(0, 100)
        } else {
            downloadProgress.visibility = View.GONE
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
            if (chat.id == store.currentChatId) "${chat.title}  • current" else chat.title
        }.toTypedArray()

        MaterialAlertDialogBuilder(this)
            .setTitle("Chats")
            .setItems(labels) { _, which ->
                store.selectChat(chats[which].id)
                loadedChatId = null
                renderAll()
            }
            .setNeutralButton("Delete current") { _, _ -> confirmDeleteCurrentChat() }
            .setNegativeButton("Close", null)
            .show()
    }

    private fun confirmDeleteCurrentChat() {
        val current = store.currentChat()
        MaterialAlertDialogBuilder(this)
            .setTitle("Delete this chat?")
            .setMessage(current.title)
            .setPositiveButton("Delete") { _, _ ->
                store.deleteChat(current.id)
                loadedChatId = null
                renderAll()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showMenuDialog() {
        val items = arrayOf("Chat settings", "Export all data", "Unload model")
        MaterialAlertDialogBuilder(this)
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
            setPadding(dp(20), dp(6), dp(20), 0)
        }

        val systemInput = TextInputEditText(this).apply {
            setText(chat.systemPrompt)
            minLines = 4
            maxLines = 9
            gravity = Gravity.TOP
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        val systemLayout = TextInputLayout(this).apply {
            hint = "System prompt"
            boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            boxStrokeColor = color(R.color.accent)
            addView(systemInput)
        }

        val contextInput = TextInputEditText(this).apply {
            setText(chat.contextLength.toString())
            inputType = InputType.TYPE_CLASS_NUMBER
        }
        val contextLayout = TextInputLayout(this).apply {
            hint = "Context length"
            boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            boxStrokeColor = color(R.color.accent)
            addView(contextInput)
        }
        val contextParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = dp(14) }

        box.addView(systemLayout, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ))
        box.addView(contextLayout, contextParams)
        box.addView(TextView(this).apply {
            text = "512–131072 tokens. Larger contexts use more RAM and can fail if the device cannot allocate the KV cache."
            textSize = 12f
            setTextColor(color(R.color.text_secondary))
            setPadding(dp(2), dp(8), dp(2), 0)
        })

        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle("Chat settings")
            .setView(box)
            .setPositiveButton("Save", null)
            .setNegativeButton("Cancel", null)
            .create()

        dialog.setOnShowListener {
            dialog.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val context = contextInput.text?.toString()?.toIntOrNull()
                if (context == null || context !in 512..131072) {
                    contextLayout.error = "Enter a value from 512 to 131072"
                    return@setOnClickListener
                }
                contextLayout.error = null
                chat.systemPrompt = systemInput.text?.toString().orEmpty().ifBlank { "You are a helpful assistant." }
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
            setPadding(dp(14), dp(4), dp(14), dp(8))
        }

        val downloadButton = MaterialButton(this).apply {
            text = "Download GGUF from URL"
            isAllCaps = false
            cornerRadius = dp(16)
            setOnClickListener {
                currentModelDialog?.dismiss()
                showDownloadDialog()
            }
        }
        box.addView(downloadButton, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ))

        if (loadedModelName != null || engine.state.value is InferenceEngine.State.ModelReady) {
            val unloadButton = MaterialButton(
                this,
                null,
                com.google.android.material.R.attr.materialButtonOutlinedStyle,
            ).apply {
                text = "Unload current model"
                isAllCaps = false
                cornerRadius = dp(16)
                setOnClickListener {
                    currentModelDialog?.dismiss()
                    unloadModelAsync()
                }
            }
            val p = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(8) }
            box.addView(unloadButton, p)
        }

        val files = modelFiles()
        box.addView(TextView(this).apply {
            text = if (files.isEmpty()) "No downloaded models" else "Downloaded models"
            textSize = 13f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(color(R.color.text_secondary))
            setPadding(dp(2), dp(18), dp(2), dp(8))
        })

        files.forEach { file -> box.addView(modelRow(file)) }

        if (files.isEmpty()) {
            box.addView(TextView(this).apply {
                text = "Paste a direct .gguf link above. The file will be stored privately inside the app."
                textSize = 14f
                setTextColor(color(R.color.text_secondary))
                setPadding(dp(2), dp(2), dp(2), dp(14))
            })
        }

        val scroll = ScrollView(this).apply {
            addView(box)
            isFillViewport = true
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle("Models")
            .setView(scroll)
            .setNegativeButton("Close", null)
            .create()
        currentModelDialog = dialog
        dialog.setOnDismissListener { if (currentModelDialog === dialog) currentModelDialog = null }
        dialog.show()
    }

    private fun modelRow(file: File): View {
        val selected = store.currentChat().modelFile == file.name
        val loaded = loadedModelName == file.name
        val card = MaterialCardView(this).apply {
            radius = dp(16).toFloat()
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = color(if (selected) R.color.accent else R.color.divider)
            setCardBackgroundColor(color(R.color.surface_alt))
            isClickable = true
            isFocusable = true
            setOnClickListener {
                currentModelDialog?.dismiss()
                selectAndLoadModel(file)
            }
        }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(10), dp(8), dp(10))
        }
        val info = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        info.addView(TextView(this).apply {
            text = file.name
            textSize = 14f
            typeface = Typeface.DEFAULT_BOLD
            maxLines = 2
            setTextColor(color(R.color.text_primary))
        })
        info.addView(TextView(this).apply {
            text = buildString {
                if (loaded) append("Loaded • ") else if (selected) append("Selected • ")
                append(formatBytes(file.length()))
            }
            textSize = 12f
            setTextColor(color(R.color.text_secondary))
            setPadding(0, dp(3), 0, 0)
        })
        val delete = TextView(this).apply {
            text = "Delete"
            textSize = 13f
            gravity = Gravity.CENTER
            setTextColor(color(R.color.danger))
            setPadding(dp(12), dp(12), dp(8), dp(12))
            isClickable = true
            setOnClickListener { confirmDeleteModel(file) }
        }
        row.addView(info, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(delete)
        card.addView(row)

        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(card, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(8) })
        }
    }

    private fun showDownloadDialog() {
        val input = TextInputEditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine(false)
            minLines = 2
            maxLines = 4
        }
        val inputLayout = TextInputLayout(this).apply {
            hint = "Direct GGUF URL"
            boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            boxStrokeColor = color(R.color.accent)
            addView(input)
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(4), dp(20), 0)
            addView(TextView(this@MainActivity).apply {
                text = "Paste the direct model-file link. Hugging Face /resolve/ links are supported."
                textSize = 13f
                setTextColor(color(R.color.text_secondary))
                setPadding(dp(2), 0, dp(2), dp(10))
            })
            addView(inputLayout)
        }

        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle("Download model")
            .setView(box)
            .setPositiveButton("Download", null)
            .setNegativeButton("Cancel", null)
            .create()

        dialog.setOnShowListener {
            dialog.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val url = input.text?.toString()?.trim().orEmpty()
                if (!url.startsWith("http://") && !url.startsWith("https://")) {
                    inputLayout.error = "Paste an http(s) URL"
                    return@setOnClickListener
                }
                inputLayout.error = null
                dialog.dismiss()
                downloadModel(url)
            }
        }
        dialog.show()
    }

    private fun downloadModel(url: String) {
        if (busy) return
        setBusy(true, "Starting model download…")
        runOnUiThread { showStatus("Starting model download…", indeterminate = true) }

        Thread {
            var downloadedFile: File? = null
            try {
                downloadedFile = ModelDownloader.download(url, store.modelsDir) { progress ->
                    val percent = if (progress.total > 0) {
                        (progress.downloaded.toDouble() / progress.total.toDouble() * 100.0).roundToInt().coerceIn(0, 100)
                    } else null
                    val text = if (progress.total > 0) {
                        "Downloading ${formatBytes(progress.downloaded)} of ${formatBytes(progress.total)}"
                    } else {
                        "Downloading ${formatBytes(progress.downloaded)}"
                    }
                    runOnUiThread {
                        showStatus(text, progress = percent, indeterminate = percent == null)
                    }
                }

                val chat = store.currentChat()
                chat.modelFile = downloadedFile.name
                store.save()
                runOnUiThread {
                    renderHeader()
                    showStatus("Download complete. Loading ${downloadedFile.name}…", indeterminate = true)
                }

                ensureModelLoaded(chat)
                runOnUiThread {
                    setBusy(false)
                    Toast.makeText(this, "${downloadedFile.name} downloaded and loaded", Toast.LENGTH_LONG).show()
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    setBusy(false)
                    val title = if (downloadedFile == null) "Model download failed" else "Model downloaded, but could not load"
                    showError(title, t)
                }
            }
        }.start()
    }

    private fun confirmDeleteModel(file: File) {
        MaterialAlertDialogBuilder(this)
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
                    showError("Could not delete model", IllegalStateException("Android could not delete ${file.absolutePath}"))
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun selectAndLoadModel(file: File) {
        if (busy) return
        val chat = store.currentChat()
        chat.modelFile = file.name
        store.save()
        loadedChatId = null
        renderHeader()
        setBusy(true, "Loading ${file.name}…")
        runOnUiThread { showStatus("Loading ${file.name}…", indeterminate = true) }

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
        if (loadedModelName == null && engine.state.value !is InferenceEngine.State.ModelReady) {
            Toast.makeText(this, "No model is loaded", Toast.LENGTH_SHORT).show()
            return
        }
        setBusy(true, "Unloading model…")
        runOnUiThread { showStatus("Unloading model…", indeterminate = true) }
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
        runOnUiThread { showStatus("Preparing model…", indeterminate = true) }

        Thread {
            var assistant: ChatMessage? = null
            try {
                ensureModelLoaded(chat)

                val userMessage = ChatMessage("user", text)
                assistant = ChatMessage("assistant", "")
                chat.messages += userMessage
                chat.messages += assistant
                if (chat.title == "New chat") {
                    chat.title = text.replace("\n", " ").take(42).ifBlank { "New chat" }
                }
                store.save()

                runOnUiThread {
                    renderHeader()
                    renderMessages()
                    showStatus("Generating…", indeterminate = true)
                }

                val buffer = StringBuilder()
                var lastUi = 0L
                runBlocking {
                    engine.sendUserPrompt(text).collect { token ->
                        buffer.append(token)
                        assistant.content = buffer.toString()
                        val now = System.currentTimeMillis()
                        if (now - lastUi >= 55L) {
                            val snapshot = buffer.toString()
                            runOnUiThread {
                                streamingTextView?.text = snapshot
                                messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
                            }
                            lastUi = now
                        }
                    }
                }
                assistant.content = buffer.toString()
                store.save()
                runOnUiThread {
                    setBusy(false)
                    renderAll()
                }
            } catch (t: Throwable) {
                if (assistant != null && assistant.content.isBlank()) {
                    assistant.content = "[generation failed: ${friendlyMessage(t)}]"
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

        runOnUiThread {
            showStatus("Loading $name with ${formatContext(chat.contextLength)} context…", indeterminate = true)
        }
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
        if (state is InferenceEngine.State.Initialized || state is InferenceEngine.State.ModelReady) return
        if (state is InferenceEngine.State.Error) {
            engine.cleanUp()
            return
        }

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
        val historyBudgetChars = (chat.contextLength * 3).coerceAtLeast(2_000).coerceAtMost(180_000)
        return buildString {
            append(base)
            append("\n\nThe model context was reloaded. Below is the recent conversation history. Continue naturally and do not mention this restoration note unless asked.\n\n")
            append(transcript.takeLast(historyBudgetChars))
        }
    }

    private fun exportAllData(uri: Uri) {
        if (busy) return
        setBusy(true, "Exporting app data…")
        Thread {
            try {
                val data = store.dataFile()
                val models = modelFiles()
                val output = contentResolver.openOutputStream(uri, "w")
                    ?: error("Could not open the export destination")
                ZipOutputStream(output.buffered(1024 * 1024)).use { zip ->
                    zip.setLevel(Deflater.NO_COMPRESSION)
                    zip.putNextEntry(ZipEntry("data.json"))
                    data.inputStream().use { it.copyTo(zip, 1024 * 1024) }
                    zip.closeEntry()

                    models.forEachIndexed { index, model ->
                        runOnUiThread {
                            showStatus("Exporting model ${index + 1}/${models.size}: ${model.name}")
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

    private fun formatContext(tokens: Int): String = when {
        tokens >= 1024 && tokens % 1024 == 0 -> "${tokens / 1024}k"
        tokens >= 1000 -> "%.1fk".format(tokens / 1000.0)
        else -> tokens.toString()
    }

    private fun showError(title: String, throwable: Throwable) {
        MaterialAlertDialogBuilder(this)
            .setTitle(title)
            .setMessage(friendlyMessage(throwable))
            .setPositiveButton("OK", null)
            .show()
    }

    private fun friendlyMessage(throwable: Throwable): String {
        var current: Throwable? = throwable
        while (current != null) {
            val message = current.message?.trim()
            if (!message.isNullOrBlank()) return message
            current = current.cause
        }
        return throwable.javaClass.simpleName
    }

    private fun color(id: Int): Int = ContextCompat.getColor(this, id)
    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()
}

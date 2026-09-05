package com.johndsdev.androidllm

import android.app.Dialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.Window
import android.view.WindowManager
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.HorizontalScrollView
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
import androidx.core.view.GravityCompat
import androidx.drawerlayout.widget.DrawerLayout
import com.arm.aichat.AiChat
import com.arm.aichat.InferenceEngine
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.slider.Slider
import androidx.appcompat.widget.SwitchCompat
import io.noties.markwon.Markwon
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import java.io.File
import android.text.Editable
import android.text.TextWatcher
import android.os.SystemClock
import androidx.recyclerview.widget.RecyclerView
import androidx.recyclerview.widget.LinearLayoutManager
import java.util.zip.Deflater
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.math.roundToInt

class MainActivity : AppCompatActivity() {
    private lateinit var store: AppStore
    private lateinit var engine: InferenceEngine
    private lateinit var markwon: Markwon

    private lateinit var titleView: TextView
    private lateinit var headerSubtitle: TextView
    private lateinit var modelNameView: TextView
    private lateinit var contextView: TextView
    private lateinit var statusContainer: LinearLayout
    private lateinit var statusView: TextView
    private lateinit var downloadProgress: ProgressBar
    private lateinit var modelCard: MaterialCardView
    private lateinit var messageScroll: TranscriptScrollView
    private lateinit var messageContainer: LinearLayout
    private lateinit var inputView: EditText
    private lateinit var sendButton: ImageButton
    private lateinit var chatsButton: ImageButton
    private lateinit var newButton: ImageButton
    private lateinit var menuButton: ImageButton
    private lateinit var drawerLayout: DrawerLayout
    private lateinit var drawerChatList: RecyclerView
    private lateinit var historyAdapter: ChatHistoryAdapter
    private lateinit var drawerNewChatButton: MaterialButton
    private lateinit var exportLauncher: ActivityResultLauncher<String>

    @Volatile private var busy = false
    @Volatile private var generating = false
    @Volatile private var stopRequested = false
    @Volatile private var lastTps: Double? = null
    @Volatile private var loadedModelName: String? = null
    @Volatile private var loadedChatId: String? = null
    @Volatile private var loadedContextLength: Int? = null
    @Volatile private var loadedRuntimeKey: String? = null
    @Volatile private var gpuPpActive = false
    @Volatile private var streamingTextView: TextView? = null
    private var currentModelDialog: Dialog? = null
    private lateinit var latestButton: TextView
    private lateinit var historySearch: EditText
    private val uiHandler = Handler(Looper.getMainLooper())
    private var activeStream: Runnable? = null
    private var renderedChatId: String? = null


    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = AppStore(applicationContext)
        engine = AiChat.getInferenceEngine(applicationContext)
        markwon = Markwon.create(this)

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
        drawerLayout = findViewById(R.id.drawerLayout)
        drawerChatList = findViewById(R.id.drawerChatList)
        historyAdapter = ChatHistoryAdapter(::selectHistoryChat, ::showChatOptions)
        drawerChatList.layoutManager = LinearLayoutManager(this)
        drawerChatList.adapter = historyAdapter
        drawerChatList.itemAnimator = null
        drawerNewChatButton = findViewById(R.id.drawerNewChatButton)
        latestButton = findViewById(R.id.latestButton)
        historySearch = findViewById(R.id.historySearch)
        latestButton.setOnClickListener { messageScroll.jumpToLatest() }
        messageScroll.onFollowChanged = { following ->
            latestButton.visibility = if (following) View.GONE else View.VISIBLE
        }
        historySearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) { renderChatDrawer() }
            override fun afterTextChanged(s: Editable?) = Unit
        })

        chatsButton.setOnClickListener { drawerLayout.openDrawer(GravityCompat.START) }
        drawerNewChatButton.setOnClickListener {
            if (!busy) {
                createNewChat()
                drawerLayout.closeDrawer(GravityCompat.START)
            }
        }
        newButton.setOnClickListener { createNewChat() }
        menuButton.setOnClickListener { showMenuDialog() }
        modelCard.setOnClickListener { showModelsDialog() }
        sendButton.setOnClickListener { if (generating) stopGeneration() else sendMessage() }
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
        renderChatDrawer()
        updateControls()
    }

    private fun renderHeader() {
        val chat = store.currentChat()
        titleView.text = chat.title
        modelNameView.text = chat.modelFile?.removeSuffix(".gguf") ?: "Choose model"
        contextView.text = formatContext(chat.contextLength)

        val loadedHere = loadedModelName == chat.modelFile && loadedModelName != null
        val computeLabel = when {
            loadedHere && gpuPpActive -> "Vulkan PP • CPU TG"
            loadedHere && chat.gpuPromptProcessing -> "GPU PP unavailable • CPU"
            loadedHere -> "CPU"
            chat.modelFile != null -> "model selected"
            else -> "CPU"
        }
        val baseSubtitle = "On-device • $computeLabel"
        val speed = lastTps?.takeIf { it.isFinite() && it > 0.0 }
        headerSubtitle.text = if (speed != null) {
            "$baseSubtitle • ${formatTps(speed)} tok/s"
        } else {
            baseSubtitle
        }
    }

    private fun renderMessages() {
        val chatId = store.currentChatId
        if (renderedChatId != chatId) {
            messageScroll.jumpToLatest()
            renderedChatId = chatId
        }
        streamingTextView = null
        messageContainer.removeAllViews()
        val messages = store.currentChat().messages

        if (messages.isEmpty()) {
            messageContainer.gravity = Gravity.CENTER
            val empty = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setPadding(dp(18), dp(56), dp(18), dp(56))
            }
            empty.addView(TextView(this).apply {
                text = "What can I help with?"
                textSize = 26f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                setTextColor(color(R.color.text_primary))
            })
            empty.addView(TextView(this).apply {
                text = "Choose a local model above and start chatting."
                textSize = 14f
                gravity = Gravity.CENTER
                setTextColor(color(R.color.text_secondary))
                setPadding(0, dp(10), 0, 0)
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
            val maxUserWidth = (resources.displayMetrics.widthPixels * 0.82f).roundToInt()

            messages.forEachIndexed { index, message ->
                val fromUser = message.role != "assistant"
                val isStreamingAssistant = busy && index == messages.lastIndex && !fromUser

                if (fromUser) {
                    val wrapper = LinearLayout(this).apply {
                        orientation = LinearLayout.VERTICAL
                        gravity = Gravity.END
                        setPadding(dp(34), dp(5), 0, dp(7))
                    }
                    val card = MaterialCardView(this).apply {
                        radius = dp(18).toFloat()
                        cardElevation = 0f
                        strokeWidth = 0
                        setCardBackgroundColor(color(R.color.user_bubble))
                    }
                    val body = TextView(this).apply {
                        text = message.content
                        textSize = 16f
                        maxWidth = maxUserWidth
                        setTextColor(color(R.color.user_text))
                        setTextIsSelectable(true)
                        setLineSpacing(0f, 1.08f)
                        setPadding(dp(14), dp(10), dp(14), dp(10))
                    }
                    card.addView(body)
                    wrapper.addView(card, LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                    ))
                    wrapper.addView(messageActionsRow(
                        Gravity.END,
                        listOf(
                            "Copy" to { copyText(message.content, "Message copied") },
                            "Edit" to { editUserMessage(index) },
                        ),
                    ))
                    messageContainer.addView(wrapper, LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                    ))
                } else {
                    val row = LinearLayout(this).apply {
                        orientation = LinearLayout.VERTICAL
                        gravity = Gravity.START
                        setPadding(0, dp(10), 0, dp(13))
                    }

                    if (isStreamingAssistant) {
                        val body = markdownTextView().apply {
                            // Selection can ask ScrollView to reveal the beginning of
                            // a growing TextView. Enable it only after streaming ends.
                            setTextIsSelectable(false)
                            isFocusable = false
                            text = message.content
                        }
                        row.addView(body, LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            LinearLayout.LayoutParams.WRAP_CONTENT,
                        ))
                        streamingTextView = body
                    } else {
                        renderAssistantMarkdown(row, message.content)
                        row.addView(messageActionsRow(
                            Gravity.START,
                            listOf(
                                "Copy" to { copyText(message.content, "Response copied") },
                                "Regenerate" to { regenerateAssistantMessage(index) },
                            ),
                        ))
                    }

                    messageContainer.addView(row, LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                    ))
                }
            }
        }
    }

    private fun markdownTextView() = TextView(this).apply {
        textSize = 16f
        setTextColor(color(R.color.assistant_text))
        setTextIsSelectable(true)
        setLineSpacing(0f, 1.12f)
        setPadding(0, dp(2), 0, dp(2))
    }

    private fun renderAssistantMarkdown(parent: LinearLayout, content: String) {
        // Completed fenced blocks get native code cards with their own Copy action.
        // Everything between them is still rendered by Markwon.
        val fence = Regex("```([^\\n`]*)\\n([\\s\\S]*?)```")
        var cursor = 0
        var foundFence = false
        fence.findAll(content).forEach { match ->
            foundFence = true
            if (match.range.first > cursor) {
                val markdown = content.substring(cursor, match.range.first)
                if (markdown.isNotEmpty()) {
                    parent.addView(markdownTextView().apply { markwon.setMarkdown(this, markdown) })
                }
            }
            parent.addView(codeBlockView(match.groupValues[1].trim(), match.groupValues[2]))
            cursor = match.range.last + 1
        }
        if (!foundFence) {
            parent.addView(markdownTextView().apply { markwon.setMarkdown(this, content) })
        } else if (cursor < content.length) {
            val markdown = content.substring(cursor)
            if (markdown.isNotEmpty()) {
                parent.addView(markdownTextView().apply { markwon.setMarkdown(this, markdown) })
            }
        }
    }

    private fun codeBlockView(language: String, code: String): View {
        val card = MaterialCardView(this).apply {
            radius = dp(14).toFloat()
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = color(R.color.divider)
            setCardBackgroundColor(color(R.color.surface_alt))
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(6), dp(7), dp(5))
        }
        header.addView(TextView(this).apply {
            text = language.ifBlank { "Code" }
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(color(R.color.text_secondary))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        header.addView(messageAction("Copy") { copyText(code, "Code copied") })
        box.addView(header)
        box.addView(View(this).apply { setBackgroundColor(color(R.color.divider)) }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            dp(1),
        ))
        val horizontal = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = true
            addView(TextView(this@MainActivity).apply {
                text = code.trimEnd('\n')
                textSize = 13.5f
                typeface = Typeface.MONOSPACE
                setTextIsSelectable(true)
                setTextColor(color(R.color.text_primary))
                setPadding(dp(12), dp(10), dp(12), dp(12))
            })
        }
        box.addView(horizontal)
        card.addView(box)
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(card, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply {
                topMargin = dp(7)
                bottomMargin = dp(7)
            })
        }
    }

    private fun messageActionsRow(
        gravity: Int,
        actions: List<Pair<String, () -> Unit>>,
    ) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        this.gravity = gravity
        setPadding(0, dp(3), 0, 0)
        actions.forEach { (label, action) -> addView(messageAction(label, action)) }
    }

    private fun messageAction(label: String, onClick: () -> Unit) = TextView(this).apply {
        text = label
        textSize = 12.5f
        setTextColor(color(R.color.text_secondary))
        setPadding(dp(9), dp(7), dp(9), dp(7))
        isClickable = true
        isFocusable = true
        setOnClickListener { if (!busy) onClick() }
    }

    private fun copyText(value: String, toast: String) {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("AndroidLLM", value))
        Toast.makeText(this, toast, Toast.LENGTH_SHORT).show()
    }

    private fun editUserMessage(index: Int) {
        if (busy) return
        val chat = store.currentChat()
        val message = chat.messages.getOrNull(index) ?: return
        if (message.role == "assistant") return

        val input = TextInputEditText(this).apply {
            setText(message.content)
            minLines = 3
            maxLines = 8
            gravity = Gravity.TOP
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            setSelection(text?.length ?: 0)
        }
        val layout = TextInputLayout(this).apply {
            hint = "Edit message"
            boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            boxStrokeColor = color(R.color.accent)
            addView(input)
        }
        showAppSheet(
            title = "Edit message",
            content = layout,
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Save & send") { dialog ->
                    val revised = input.text?.toString()?.trim().orEmpty()
                    if (revised.isBlank()) return@SheetAction
                    while (chat.messages.size > index) chat.messages.removeAt(chat.messages.lastIndex)
                    store.save()
                    invalidateLoadedConversation()
                    dialog.dismiss()
                    inputView.setText(revised)
                    renderAll()
                    sendMessage()
                },
            ),
        )
    }

    private fun regenerateAssistantMessage(index: Int) {
        if (busy) return
        val chat = store.currentChat()
        val assistant = chat.messages.getOrNull(index) ?: return
        if (assistant.role != "assistant") return
        val userIndex = (index - 1 downTo 0).firstOrNull { chat.messages[it].role != "assistant" } ?: return
        val prompt = chat.messages[userIndex].content

        // Regeneration branches from the user turn that produced this answer.
        // Later messages depended on the old answer, so truncate them too.
        while (chat.messages.size > userIndex) chat.messages.removeAt(chat.messages.lastIndex)
        store.save()
        invalidateLoadedConversation()
        inputView.setText(prompt)
        renderAll()
        sendMessage()
    }

    private fun invalidateLoadedConversation() {
        // Keep model weights + context allocation resident. ensureModelLoaded()
        // will reset only the native conversation/KV state for the next chat.
        loadedChatId = null
        lastTps = null
    }

    private fun invalidateLoadedRuntime() {
        loadedChatId = null
        loadedContextLength = null
        loadedRuntimeKey = null
        gpuPpActive = false
        lastTps = null
    }

    private fun renderChatDrawer() {
        historyAdapter.submit(store.chats, store.currentChatId, historySearch.text.toString())
    }

    private fun selectHistoryChat(chat: ChatSession) {
        if (busy) return
        if (store.currentChatId != chat.id) {
            store.selectChat(chat.id)
            loadedModelName?.let { loaded ->
                store.currentChat().modelFile = loaded
                store.save()
            }
            invalidateLoadedConversation()
            renderAll()
        }
        drawerLayout.closeDrawer(GravityCompat.START)
    }

    private fun showChatOptions(chat: ChatSession) {
        if (busy) return
        val input = TextInputEditText(this).apply {
            setText(chat.title)
            maxLines = 2
            setSelectAllOnFocus(true)
        }
        val layout = TextInputLayout(this).apply {
            hint = "Chat name"
            boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            addView(input)
        }
        showAppSheet(
            title = "Chat options",
            content = layout,
            actions = listOf(
                SheetAction("Delete", destructive = true) {
                    it.dismiss()
                    confirmDeleteChat(chat.id, chat.title)
                },
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Save") {
                    chat.title = input.text.toString().trim().take(100).ifBlank { "New chat" }
                    store.save()
                    renderHeader()
                    renderChatDrawer()
                    it.dismiss()
                },
            ),
        )
    }

    private fun confirmDeleteChat(chatId: String, title: String) {
        showAppSheet(
            title = "Delete this chat?",
            message = title,
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Delete", destructive = true) { dialog ->
                    store.deleteChat(chatId)
                    loadedModelName?.let { loaded ->
                        val selectedChat = store.currentChat()
                        if (selectedChat.modelFile != loaded) {
                            selectedChat.modelFile = loaded
                            store.save()
                        }
                    }
                    invalidateLoadedConversation()
                    dialog.dismiss()
                    renderAll()
                },
            ),
        )
    }

    private fun updateControls() {
        messageScroll.streaming = busy
        sendButton.isEnabled = !busy || (generating && !stopRequested)
        chatsButton.isEnabled = !busy
        newButton.isEnabled = !busy
        menuButton.isEnabled = !busy
        modelCard.isEnabled = !busy
        // Keep the draft editable and focused; toggling enabled would move focus
        // into selectable transcript text and dismiss/reopen the keyboard.
        inputView.isEnabled = true
        sendButton.alpha = if (busy && !generating) 0.45f else if (stopRequested) 0.55f else 1f
        sendButton.setImageResource(if (generating) R.drawable.ic_stop else R.drawable.ic_send)
        sendButton.contentDescription = if (generating) "Stop generation" else "Send message"
    }

    private fun setBusy(value: Boolean, message: String? = null) {
        busy = value
        onUi {
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

    private data class SheetAction(
        val label: String,
        val destructive: Boolean = false,
        val onClick: (Dialog) -> Unit,
    )

    private fun showAppSheet(
        title: String,
        content: View? = null,
        message: String? = null,
        actions: List<SheetAction> = listOf(SheetAction("Close") { it.dismiss() }),
    ): Dialog {
        val dialog = Dialog(this)
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)

        val card = MaterialCardView(this).apply {
            radius = dp(26).toFloat()
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = color(R.color.divider)
            setCardBackgroundColor(color(R.color.surface))
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(10), dp(18), dp(14))
        }
        root.addView(View(this).apply {
            setBackgroundColor(color(R.color.divider))
        }, LinearLayout.LayoutParams(dp(42), dp(4)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            bottomMargin = dp(13)
        })
        root.addView(TextView(this).apply {
            text = title
            textSize = 20f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(color(R.color.text_primary))
            setPadding(dp(2), 0, dp(2), dp(12))
        })
        if (!message.isNullOrBlank()) {
            root.addView(TextView(this).apply {
                text = message
                textSize = 14f
                setTextColor(color(R.color.text_secondary))
                setPadding(dp(2), 0, dp(2), dp(14))
            })
        }
        if (content != null) {
            val requestedContentHeight = content.layoutParams?.height
                ?.takeIf { it > 0 }
                ?: LinearLayout.LayoutParams.WRAP_CONTENT
            root.addView(content, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                requestedContentHeight,
            ))
        }

        if (actions.isNotEmpty()) {
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.END
                setPadding(0, dp(14), 0, 0)
            }
            actions.forEach { action ->
                row.addView(MaterialButton(
                    this,
                    null,
                    com.google.android.material.R.attr.materialButtonOutlinedStyle,
                ).apply {
                    text = action.label
                    isAllCaps = false
                    cornerRadius = dp(15)
                    if (action.destructive) setTextColor(color(R.color.danger))
                    setOnClickListener { action.onClick(dialog) }
                }, LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                ).apply { marginStart = dp(8) })
            }
            root.addView(row)
        }

        card.addView(root)
        dialog.setContentView(card)
        dialog.setCanceledOnTouchOutside(true)
        dialog.show()
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.WRAP_CONTENT)
            setGravity(Gravity.BOTTOM)
            addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            setDimAmount(0.58f)
        }
        return dialog
    }

    private fun sheetRow(
        title: String,
        subtitle: String? = null,
        destructive: Boolean = false,
        onClick: () -> Unit,
    ): View {
        val card = MaterialCardView(this).apply {
            radius = dp(16).toFloat()
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = color(R.color.divider)
            setCardBackgroundColor(color(R.color.surface_alt))
            isClickable = true
            isFocusable = true
            setOnClickListener { onClick() }
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
        }
        box.addView(TextView(this).apply {
            text = title
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(color(if (destructive) R.color.danger else R.color.text_primary))
        })
        if (!subtitle.isNullOrBlank()) {
            box.addView(TextView(this).apply {
                text = subtitle
                textSize = 12f
                setTextColor(color(R.color.text_secondary))
                setPadding(0, dp(3), 0, 0)
            })
        }
        card.addView(box)
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(card, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(8) })
        }
    }

    private fun makeSlider(
        label: String,
        valueFrom: Float,
        valueTo: Float,
        step: Float,
        initial: Float,
        format: (Float) -> String,
    ): Pair<LinearLayout, Slider> {
        val valueView = TextView(this).apply {
            text = format(initial)
            textSize = 13f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(color(R.color.text_secondary))
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(TextView(this@MainActivity).apply {
                text = label
                textSize = 14f
                setTextColor(color(R.color.text_primary))
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(valueView)
        }
        val slider = Slider(this).apply {
            this.valueFrom = valueFrom
            this.valueTo = valueTo
            stepSize = step
            value = initial.coerceIn(valueFrom, valueTo)
            addOnChangeListener { _, newValue, _ -> valueView.text = format(newValue) }
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(7), 0, dp(5))
            addView(header)
            addView(slider)
        } to slider
    }

    private fun sectionLabel(label: String) = TextView(this).apply {
        text = label.uppercase()
        textSize = 11f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(color(R.color.text_secondary))
        setPadding(dp(2), dp(18), dp(2), dp(6))
    }

    private fun createNewChat() {
        if (busy) return
        val chat = store.newChat()
        historySearch.setText("")
        loadedModelName?.let { loaded ->
            if (chat.modelFile != loaded) {
                chat.modelFile = loaded
                store.save()
            }
        }
        invalidateLoadedConversation()
        renderAll()
    }

    private fun showChatsDialog() {
        drawerLayout.openDrawer(GravityCompat.START)
    }

    private fun confirmDeleteCurrentChat() {
        val current = store.currentChat()
        showAppSheet(
            title = "Delete this chat?",
            message = current.title,
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Delete", destructive = true) { dialog ->
                    store.deleteChat(current.id)
                    loadedChatId = null
                    loadedRuntimeKey = null
                    lastTps = null
                    dialog.dismiss()
                    renderAll()
                },
            ),
        )
    }

    private fun showMenuDialog() {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        var dialog: Dialog? = null
        box.addView(sheetRow("Chat settings", "Runtime, sampling, context, thinking, GPU PP") {
            dialog?.dismiss()
            showSettingsDialog()
        })
        box.addView(sheetRow("Export all data", "Chats and downloaded GGUF models") {
            dialog?.dismiss()
            exportLauncher.launch("AndroidLLM-export.zip")
        })
        box.addView(sheetRow("Unload model", "Free model RAM and GPU resources") {
            dialog?.dismiss()
            unloadModelAsync()
        })
        dialog = showAppSheet("AndroidLLM", content = box)
    }

    private fun showSettingsDialog() {
        val chat = store.currentChat()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(2), 0, dp(2), dp(4))
        }

        val systemInput = TextInputEditText(this).apply {
            setText(chat.systemPrompt)
            minLines = 3
            maxLines = 7
            gravity = Gravity.TOP
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        val systemLayout = TextInputLayout(this).apply {
            hint = "System prompt"
            boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            boxStrokeColor = color(R.color.accent)
            addView(systemInput)
        }
        box.addView(systemLayout)

        val contextOptions = intArrayOf(512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072)
        val contextIndex = contextOptions.indexOf(chat.contextLength).takeIf { it >= 0 } ?: 3
        val (contextBlock, contextSlider) = makeSlider(
            "Context length", 0f, (contextOptions.size - 1).toFloat(), 1f, contextIndex.toFloat(),
        ) { contextOptions[it.roundToInt()].let(::formatContext) }

        val maxThreads = Runtime.getRuntime().availableProcessors().coerceIn(2, 16)
        val (genThreadsBlock, genThreadsSlider) = makeSlider(
            "Generation threads", 1f, maxThreads.toFloat(), 1f,
            chat.generationThreads.coerceIn(1, maxThreads).toFloat(),
        ) { it.roundToInt().toString() }
        val (ppThreadsBlock, ppThreadsSlider) = makeSlider(
            "Prompt threads", 1f, maxThreads.toFloat(), 1f,
            chat.promptThreads.coerceIn(1, maxThreads).toFloat(),
        ) { it.roundToInt().toString() }

        val batchOptions = intArrayOf(64, 128, 256, 512, 1024, 2048)
        val batchIndex = batchOptions.indexOf(chat.batchSize).takeIf { it >= 0 } ?: 3
        val (batchBlock, batchSlider) = makeSlider(
            "Prompt batch size", 0f, (batchOptions.size - 1).toFloat(), 1f, batchIndex.toFloat(),
        ) { batchOptions[it.roundToInt()].toString() }

        val (tempBlock, tempSlider) = makeSlider(
            "Temperature", 0f, 2f, 0.05f, chat.temperature,
        ) { java.lang.String.format(java.util.Locale.US, "%.2f", it) }
        val (topKBlock, topKSlider) = makeSlider(
            "Top-k", 0f, 100f, 1f, chat.topK.coerceIn(0, 100).toFloat(),
        ) { it.roundToInt().toString() }
        val (topPBlock, topPSlider) = makeSlider(
            "Top-p", 0.1f, 1f, 0.01f, chat.topP.coerceIn(0.1f, 1f),
        ) { java.lang.String.format(java.util.Locale.US, "%.2f", it) }
        val (minPBlock, minPSlider) = makeSlider(
            "Min-p", 0f, 0.5f, 0.01f, chat.minP.coerceIn(0f, 0.5f),
        ) { java.lang.String.format(java.util.Locale.US, "%.2f", it) }

        val thinkingSwitch = SwitchCompat(this).apply {
            text = "Thinking mode"
            isChecked = chat.thinkingEnabled
            setTextColor(color(R.color.text_primary))
            setPadding(dp(12), dp(9), dp(12), dp(4))
        }
        val thinkingCard = MaterialCardView(this).apply {
            radius = dp(16).toFloat()
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = color(R.color.divider)
            setCardBackgroundColor(color(R.color.surface_alt))
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                addView(thinkingSwitch)
                addView(TextView(this@MainActivity).apply {
                    text = "Use the model's native thinking/reasoning mode when its chat template supports it."
                    textSize = 12f
                    setTextColor(color(R.color.text_secondary))
                    setPadding(dp(12), 0, dp(12), dp(11))
                })
            })
        }

        val prettySwitch = SwitchCompat(this).apply {
            text = "Pretty mode"
            isChecked = chat.prettyMode
            setTextColor(color(R.color.text_primary))
            setPadding(dp(12), dp(9), dp(12), dp(4))
        }
        val prettyCard = MaterialCardView(this).apply {
            radius = dp(16).toFloat()
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = color(R.color.divider)
            setCardBackgroundColor(color(R.color.surface_alt))
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                addView(prettySwitch)
                addView(TextView(this@MainActivity).apply {
                    text = "Reveal text in small, smooth steps. Markdown and code cards appear when the response finishes."
                    textSize = 12f
                    setTextColor(color(R.color.text_secondary))
                    setPadding(dp(12), 0, dp(12), dp(11))
                })
            })
        }

        box.addView(sectionLabel("Runtime"))
        box.addView(contextBlock)
        box.addView(genThreadsBlock)
        box.addView(ppThreadsBlock)
        box.addView(batchBlock)

        box.addView(sectionLabel("Thinking"))
        box.addView(thinkingCard)

        box.addView(sectionLabel("Display"))
        box.addView(prettyCard)

        box.addView(sectionLabel("Sampling"))
        box.addView(tempBlock)
        box.addView(topKBlock)
        box.addView(topPBlock)
        box.addView(minPBlock)

        val scroll = ScrollView(this).apply {
            addView(box)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                (resources.displayMetrics.heightPixels * 0.56f).roundToInt(),
            )
        }

        val settingsDialog = showAppSheet(
            title = "Settings",
            content = scroll,
            actions = listOf(
                SheetAction("Reset", destructive = true) { dialog ->
                    store.resetGlobalSettings()
                    invalidateLoadedRuntime()
                    dialog.dismiss()
                    renderAll()
                    Toast.makeText(this, "Settings reset to defaults", Toast.LENGTH_SHORT).show()
                },
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Save") { dialog ->
                    store.applyGlobalSettings(
                        systemPrompt = systemInput.text?.toString().orEmpty().ifBlank { AppStore.DEFAULT_SYSTEM_PROMPT },
                        contextLength = contextOptions[contextSlider.value.roundToInt()],
                        thinkingEnabled = thinkingSwitch.isChecked,
                        generationThreads = genThreadsSlider.value.roundToInt(),
                        promptThreads = ppThreadsSlider.value.roundToInt(),
                        batchSize = batchOptions[batchSlider.value.roundToInt()],
                        temperature = tempSlider.value,
                        topK = topKSlider.value.roundToInt(),
                        topP = topPSlider.value,
                        minP = minPSlider.value,
                        prettyMode = prettySwitch.isChecked,
                    )
                    invalidateLoadedRuntime()
                    dialog.dismiss()
                    renderAll()
                    Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show()
                },
            ),
        )
        settingsDialog.setCanceledOnTouchOutside(false)
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
        val dialog = showAppSheet(
            title = "Models",
            content = scroll,
            actions = listOf(SheetAction("Close") { it.dismiss() }),
        )
        currentModelDialog = dialog
        dialog.setOnDismissListener { if (currentModelDialog === dialog) currentModelDialog = null }
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
            addView(TextView(this@MainActivity).apply {
                text = "Paste a direct .gguf file URL. Hugging Face /resolve/ links work."
                textSize = 13f
                setTextColor(color(R.color.text_secondary))
                setPadding(dp(2), 0, dp(2), dp(10))
            })
            addView(inputLayout)
        }
        showAppSheet(
            title = "Download model",
            content = box,
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Download") { dialog ->
                    val url = input.text?.toString()?.trim().orEmpty()
                    if (!url.startsWith("http://") && !url.startsWith("https://")) {
                        inputLayout.error = "Paste an http(s) URL"
                    } else {
                        inputLayout.error = null
                        dialog.dismiss()
                        downloadModel(url)
                    }
                },
            ),
        )
    }

    private fun downloadModel(url: String) {
        if (busy) return
        setBusy(true, "Starting model download…")
        onUi { showStatus("Starting model download…", indeterminate = true) }

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
                    onUi {
                        showStatus(text, progress = percent, indeterminate = percent == null)
                    }
                }

                val chat = store.currentChat()
                chat.modelFile = downloadedFile.name
                store.save()
                onUi {
                    renderHeader()
                    showStatus("Download complete. Loading ${downloadedFile.name}…", indeterminate = true)
                }

                ensureModelLoaded(chat)
                onUi {
                    setBusy(false)
                    Toast.makeText(this, "${downloadedFile.name} downloaded and loaded", Toast.LENGTH_LONG).show()
                }
            } catch (t: Throwable) {
                onUi {
                    setBusy(false)
                    val title = if (downloadedFile == null) "Model download failed" else "Model downloaded, but could not load"
                    showError(title, t)
                }
            }
        }.start()
    }

    private fun confirmDeleteModel(file: File) {
        showAppSheet(
            title = "Delete model?",
            message = "${file.name}\n${formatBytes(file.length())}",
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Delete", destructive = true) { dialog ->
                    if (loadedModelName == file.name) {
                        Toast.makeText(this, "Unload this model first.", Toast.LENGTH_SHORT).show()
                        return@SheetAction
                    }
                    if (file.delete()) {
                        store.chats.filter { it.modelFile == file.name }.forEach { it.modelFile = null }
                        store.save()
                        currentModelDialog?.dismiss()
                        dialog.dismiss()
                        renderAll()
                        showModelsDialog()
                    } else {
                        dialog.dismiss()
                        showError("Could not delete model", IllegalStateException("Android could not delete ${file.absolutePath}"))
                    }
                },
            ),
        )
    }

    private fun selectAndLoadModel(file: File) {
        if (busy) return
        val chat = store.currentChat()
        chat.modelFile = file.name
        store.save()
        loadedChatId = null
        renderHeader()
        setBusy(true, "Loading ${file.name}…")
        onUi { showStatus("Loading ${file.name}…", indeterminate = true) }

        Thread {
            try {
                ensureModelLoaded(chat)
                onUi {
                    setBusy(false)
                    Toast.makeText(this, "Model loaded", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                onUi {
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
        onUi { showStatus("Unloading model…", indeterminate = true) }
        Thread {
            try {
                unloadModelBlocking()
                onUi {
                    setBusy(false)
                    Toast.makeText(this, "Model unloaded", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                onUi {
                    setBusy(false)
                    showError("Could not unload model", t)
                }
            }
        }.start()
    }

    private fun stopGeneration() {
        if (!generating || stopRequested) return
        stopRequested = true
        engine.stopGeneration()
        onUi {
            updateControls()
            val speed = lastTps
            showStatus(
                if (speed != null && speed > 0.0) "Stopping… ${formatTps(speed)} tok/s" else "Stopping…",
                indeterminate = true,
            )
        }
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
        messageScroll.jumpToLatest()
        setBusy(true, "Preparing model…")
        onUi { showStatus("Preparing model…", indeterminate = true) }

        Thread {
            var assistant: ChatMessage? = null
            val responseBuffer = StreamingBuffer()
            try {
                ensureModelLoaded(chat)

                val response = ChatMessage("assistant", "")
                assistant = response
                runBlocking {
                    withContext(Dispatchers.Main) {
                        chat.messages += ChatMessage("user", text)
                        chat.messages += response
                        if (chat.title == "New chat") {
                            chat.title = text.replace("\n", " ").take(42).ifBlank { "New chat" }
                        }
                    }
                }
                store.save()

                generating = true
                stopRequested = false
                lastTps = null
                onUi {
                    renderHeader()
                    renderMessages()
                    updateControls()
                    showStatus("Generating…", indeterminate = true)
                }

                val buffer = responseBuffer
                val stream = object : Runnable {
                    override fun run() {
                        if (isDestroyed) return
                        val delta = buffer.drain(chat.prettyMode)
                        if (delta.isNotEmpty()) streamingTextView?.append(delta)
                        // One queued update, bounded independently of model speed.
                        uiHandler.postDelayed(this, if (chat.prettyMode) 32L else 80L)
                    }
                }
                onUi {
                    activeStream = stream
                    uiHandler.post(stream)
                }

                var lastStatsUi = 0L
                var generatedTokens = 0
                var firstTokenNanos = 0L
                runBlocking {
                    engine.sendUserPrompt(text, enableThinking = chat.thinkingEnabled).collect { token ->
                        if (firstTokenNanos == 0L) firstTokenNanos = System.nanoTime()
                        generatedTokens++
                        buffer.append(token)
                        if (stopRequested) engine.stopGeneration()
                        val now = SystemClock.elapsedRealtime()
                        if (firstTokenNanos != 0L && now - lastStatsUi >= 500L) {
                            val elapsedSeconds = (System.nanoTime() - firstTokenNanos) / 1_000_000_000.0
                            if (elapsedSeconds > 0.0) {
                                lastTps = generatedTokens / elapsedSeconds
                                val speed = lastTps!!
                                onUi {
                                    showStatus("Generating… ${formatTps(speed)} tok/s", indeterminate = true)
                                }
                            }
                            lastStatsUi = now
                        }
                    }
                }
                if (firstTokenNanos != 0L && generatedTokens > 0) {
                    val elapsedSeconds = (System.nanoTime() - firstTokenNanos) / 1_000_000_000.0
                    if (elapsedSeconds > 0.0) lastTps = generatedTokens / elapsedSeconds
                }
                assistant.content = buffer.snapshot()
                store.save()
                generating = false
                stopRequested = false
                onUi {
                    stopStreamUpdates()
                    setBusy(false)
                    renderAll()
                }
            } catch (t: Throwable) {
                if (assistant != null) {
                    assistant.content = responseBuffer.snapshot().let { partial ->
                        if (partial.isBlank()) "[generation failed: ${friendlyMessage(t)}]"
                        else "$partial\n\n[Generation interrupted: ${friendlyMessage(t)}]"
                    }
                    store.save()
                }
                generating = false
                stopRequested = false
                onUi {
                    setBusy(false)
                    stopStreamUpdates()
                    renderAll()
                    showError("Generation failed", t)
                }
            }
        }.start()
    }

    private fun onUi(action: () -> Unit) {
        runOnUiThread { if (!isDestroyed) action() }
    }

    private fun stopStreamUpdates() {
        activeStream?.let { uiHandler.removeCallbacks(it) }
        activeStream = null
    }

    override fun onDestroy() {
        stopStreamUpdates()
        messageScroll.onFollowChanged = null
        if (generating) engine.stopGeneration()
        super.onDestroy()
    }

    private fun ensureModelLoaded(chat: ChatSession) {
        val name = chat.modelFile ?: loadedModelName ?: error("No model selected")
        if (chat.modelFile == null) {
            chat.modelFile = name
            store.save()
        }
        val file = File(store.modelsDir, name)
        require(file.exists() && file.isFile) { "Model file is missing: $name" }

        val key = runtimeKey(chat)
        val sameResidentModel =
            loadedModelName == name &&
            loadedContextLength == chat.contextLength &&
            loadedRuntimeKey == key &&
            engine.state.value is InferenceEngine.State.ModelReady

        if (sameResidentModel) {
            if (loadedChatId != chat.id) {
                onUi {
                    showStatus("Switching chat…", indeterminate = true)
                }
                runBlocking {
                    // Native processSystemPrompt resets chat/KV state but does NOT
                    // unload g_model, so the several-GB weight mapping stays hot.
                    engine.setSystemPrompt(effectiveSystemPrompt(chat))
                }
                loadedChatId = chat.id
                onUi { renderHeader() }
            }
            return
        }

        unloadModelBlocking()
        waitForNativeInitialization()

        onUi {
            showStatus("Loading $name with ${formatContext(chat.contextLength)} context…", indeterminate = true)
        }
        runBlocking {
            engine.loadModel(
                file.absolutePath,
                chat.contextLength,
                chat.generationThreads,
                chat.promptThreads,
                chat.batchSize,
                chat.temperature,
                chat.topK,
                chat.topP,
                chat.minP,
                false,
            )
            gpuPpActive = false
            engine.setSystemPrompt(effectiveSystemPrompt(chat))
        }

        loadedModelName = name
        loadedChatId = chat.id
        loadedContextLength = chat.contextLength
        loadedRuntimeKey = key
        onUi { renderHeader() }
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
        loadedRuntimeKey = null
        gpuPpActive = false
    }

    private fun runtimeKey(chat: ChatSession): String = listOf(
        chat.contextLength,
        chat.generationThreads,
        chat.promptThreads,
        chat.batchSize,
        chat.temperature,
        chat.topK,
        chat.topP,
        chat.minP,
    ).joinToString("|")

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
                        onUi {
                            showStatus("Exporting model ${index + 1}/${models.size}: ${model.name}")
                        }
                        zip.putNextEntry(ZipEntry("models/${model.name}"))
                        model.inputStream().buffered(1024 * 1024).use { it.copyTo(zip, 1024 * 1024) }
                        zip.closeEntry()
                    }
                }
                onUi {
                    setBusy(false)
                    Toast.makeText(this, "Export complete", Toast.LENGTH_LONG).show()
                }
            } catch (t: Throwable) {
                onUi {
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

    private fun formatTps(tps: Double): String = java.lang.String.format(java.util.Locale.US, "%.1f", tps)

    private fun formatContext(tokens: Int): String = when {
        tokens >= 1024 && tokens % 1024 == 0 -> "${tokens / 1024}k"
        tokens >= 1000 -> "%.1fk".format(tokens / 1000.0)
        else -> tokens.toString()
    }

    private fun showError(title: String, throwable: Throwable) {
        showAppSheet(
            title = title,
            message = friendlyMessage(throwable),
            actions = listOf(SheetAction("OK") { it.dismiss() }),
        )
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

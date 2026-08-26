#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
if not main.exists():
    raise SystemExit("generated MainActivity.kt is missing")

text = main.read_text()


def replace_function(source: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = source.find(start_marker)
    end = source.find(end_marker, start)
    if start < 0 or end < 0:
        raise SystemExit(f"function boundaries not found: {start_marker!r} -> {end_marker!r}")
    return source[:start] + replacement + source[end:]


# ---------------------------------------------------------------------------
# Imports and drawer fields.
# ---------------------------------------------------------------------------
if "import android.content.ClipData\n" not in text:
    text = text.replace(
        "import android.app.Dialog\n",
        "import android.app.Dialog\nimport android.content.ClipData\nimport android.content.ClipboardManager\nimport android.content.Context\n",
        1,
    )
if "import android.widget.HorizontalScrollView\n" not in text:
    text = text.replace("import android.widget.EditText\n", "import android.widget.EditText\nimport android.widget.HorizontalScrollView\n", 1)
if "import androidx.core.view.GravityCompat\n" not in text:
    text = text.replace("import androidx.core.content.ContextCompat\n", "import androidx.core.content.ContextCompat\nimport androidx.core.view.GravityCompat\nimport androidx.drawerlayout.widget.DrawerLayout\n", 1)

field_anchor = "    private lateinit var menuButton: ImageButton\n"
if field_anchor not in text:
    raise SystemExit("menuButton field anchor missing")
text = text.replace(
    field_anchor,
    field_anchor
    + "    private lateinit var drawerLayout: DrawerLayout\n"
    + "    private lateinit var drawerChatList: LinearLayout\n"
    + "    private lateinit var drawerNewChatButton: MaterialButton\n",
    1,
)

bind_anchor = "        menuButton = findViewById(R.id.menuButton)\n"
if bind_anchor not in text:
    raise SystemExit("menuButton binding anchor missing")
text = text.replace(
    bind_anchor,
    bind_anchor
    + "        drawerLayout = findViewById(R.id.drawerLayout)\n"
    + "        drawerChatList = findViewById(R.id.drawerChatList)\n"
    + "        drawerNewChatButton = findViewById(R.id.drawerNewChatButton)\n",
    1,
)

old_chat_click = "        chatsButton.setOnClickListener { showChatsDialog() }\n"
if old_chat_click not in text:
    raise SystemExit("chats button click anchor missing")
text = text.replace(
    old_chat_click,
    "        chatsButton.setOnClickListener { drawerLayout.openDrawer(GravityCompat.START) }\n"
    "        drawerNewChatButton.setOnClickListener {\n"
    "            if (!busy) {\n"
    "                createNewChat()\n"
    "                drawerLayout.closeDrawer(GravityCompat.START)\n"
    "            }\n"
    "        }\n",
    1,
)

old_render_all = '''    private fun renderAll() {
        renderHeader()
        renderMessages()
        updateControls()
    }'''
new_render_all = '''    private fun renderAll() {
        renderHeader()
        renderMessages()
        renderChatDrawer()
        updateControls()
    }'''
if old_render_all not in text:
    raise SystemExit("renderAll anchor missing")
text = text.replace(old_render_all, new_render_all, 1)

# ---------------------------------------------------------------------------
# Transcript: live Markdown while streaming, code cards with copy buttons after
# completion, and ChatGPT-like per-message actions.
# ---------------------------------------------------------------------------
new_render_messages = r'''    private fun renderMessages() {
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
                            // Keep Markdown live even before the first generated token.
                            markwon.setMarkdown(this, message.content)
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
        messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
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
        loadedChatId = null
        loadedContextLength = null
        loadedRuntimeKey = null
        gpuPpActive = false
        lastTps = null
    }

    private fun renderChatDrawer() {
        drawerChatList.removeAllViews()
        store.chats.forEach { chat ->
            val selected = chat.id == store.currentChatId
            val card = MaterialCardView(this).apply {
                radius = dp(15).toFloat()
                cardElevation = 0f
                strokeWidth = if (selected) dp(1) else 0
                strokeColor = color(if (selected) R.color.accent else R.color.divider)
                setCardBackgroundColor(color(if (selected) R.color.surface_alt else R.color.surface))
                isClickable = true
                isFocusable = true
                setOnClickListener {
                    if (!busy) {
                        store.selectChat(chat.id)
                        invalidateLoadedConversation()
                        drawerLayout.closeDrawer(GravityCompat.START)
                        renderAll()
                    }
                }
            }
            val line = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(12), dp(9), dp(5), dp(9))
            }
            line.addView(TextView(this).apply {
                text = chat.title
                textSize = 14f
                maxLines = 2
                setTextColor(color(R.color.text_primary))
                if (selected) typeface = Typeface.DEFAULT_BOLD
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            line.addView(TextView(this).apply {
                text = "Delete"
                textSize = 12f
                setTextColor(color(R.color.text_secondary))
                setPadding(dp(9), dp(8), dp(7), dp(8))
                isClickable = true
                setOnClickListener {
                    if (!busy) confirmDeleteChat(chat.id, chat.title)
                }
            })
            card.addView(line)
            drawerChatList.addView(card, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(6) })
        }
    }

    private fun confirmDeleteChat(chatId: String, title: String) {
        showAppSheet(
            title = "Delete this chat?",
            message = title,
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Delete", destructive = true) { dialog ->
                    store.deleteChat(chatId)
                    invalidateLoadedConversation()
                    dialog.dismiss()
                    renderAll()
                },
            ),
        )
    }

'''
text = replace_function(text, "    private fun renderMessages() {", "    private fun updateControls() {", new_render_messages)

# ---------------------------------------------------------------------------
# Settings are staged. Only Save commits staged values; Reset explicitly
# restores defaults. The committed settings are global and persist across chats.
# Thinking gets its own visual card.
# ---------------------------------------------------------------------------
new_settings = r'''    private fun showSettingsDialog() {
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

        val gpuSwitch = SwitchCompat(this).apply {
            text = "Experimental GPU prompt processing"
            isChecked = chat.gpuPromptProcessing
            setTextColor(color(R.color.text_primary))
            setPadding(0, dp(8), 0, dp(4))
        }

        box.addView(sectionLabel("Runtime"))
        box.addView(contextBlock)
        box.addView(genThreadsBlock)
        box.addView(ppThreadsBlock)
        box.addView(batchBlock)

        box.addView(sectionLabel("Thinking"))
        box.addView(thinkingCard)

        box.addView(sectionLabel("Sampling"))
        box.addView(tempBlock)
        box.addView(topKBlock)
        box.addView(topPBlock)
        box.addView(minPBlock)

        box.addView(sectionLabel("Experimental"))
        box.addView(gpuSwitch)
        box.addView(TextView(this).apply {
            text = "Vulkan is used only for batched prompt processing. The final prompt token and all generated tokens stay on CPU. This loads a second model context and can use substantially more RAM/VRAM. If Vulkan cannot initialize, AndroidLLM falls back to CPU."
            textSize = 12f
            setTextColor(color(R.color.text_secondary))
            setPadding(dp(2), 0, dp(2), dp(6))
        })

        val scroll = ScrollView(this).apply {
            addView(box)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                (resources.displayMetrics.heightPixels * 0.70f).roundToInt(),
            )
        }

        showAppSheet(
            title = "Settings",
            content = scroll,
            actions = listOf(
                SheetAction("Reset", destructive = true) { dialog ->
                    store.resetGlobalSettings()
                    invalidateLoadedConversation()
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
                        gpuPromptProcessing = gpuSwitch.isChecked,
                    )
                    invalidateLoadedConversation()
                    dialog.dismiss()
                    renderAll()
                    Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show()
                },
            ),
        )
    }

'''
text = replace_function(text, "    private fun showSettingsDialog() {", "    private fun showModelsDialog() {", new_settings)

# ---------------------------------------------------------------------------
# Render streaming Markdown at a throttled cadence. Inference still accumulates
# raw deltas off the UI thread; only the display parse happens ~4-5 times/sec.
# ---------------------------------------------------------------------------
text = text.replace("                val uiChunk = StringBuilder()\n", "", 1)
old_hot_path = '''                        buffer.append(token)
                        uiChunk.append(token)
                        val now = System.currentTimeMillis()
                        if (now - lastUi >= 120L) {
                            val chunk = uiChunk.toString()
                            uiChunk.setLength(0)
                            runOnUiThread {
                                streamingTextView?.append(chunk)
                                messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
                            }
                            lastUi = now
                        }'''
new_hot_path = '''                        buffer.append(token)
                        val now = System.currentTimeMillis()
                        if (now - lastUi >= 220L) {
                            val snapshot = buffer.toString()
                            runOnUiThread {
                                streamingTextView?.let { markwon.setMarkdown(it, snapshot) }
                                messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
                            }
                            lastUi = now
                        }'''
if old_hot_path not in text:
    raise SystemExit("delta streaming hot path not found")
text = text.replace(old_hot_path, new_hot_path, 1)

# New chats inherit global settings in AppStore, while the drawer refreshes via renderAll.
# Keep the old dialog method harmless for any accidental internal call.
old_show_chats_start = "    private fun showChatsDialog() {"
old_show_chats_end = "    private fun confirmDeleteCurrentChat() {"
new_show_chats = '''    private fun showChatsDialog() {
        drawerLayout.openDrawer(GravityCompat.START)
    }

'''
text = replace_function(text, old_show_chats_start, old_show_chats_end, new_show_chats)

# Guards: fail CI if a future patch quietly removes the requested UX behavior.
assert "store.applyGlobalSettings(" in text
assert "store.resetGlobalSettings()" in text
assert 'SheetAction("Save")' in text
assert 'SheetAction("Reset"' in text
assert 'sectionLabel("Thinking")' in text
assert "markwon.setMarkdown(it, snapshot)" in text
assert "streamingTextView?.append(chunk)" not in text
assert "drawerLayout.openDrawer(GravityCompat.START)" in text
assert '"Regenerate" to' in text
assert '"Edit" to' in text
assert 'messageAction("Copy") { copyText(code' in text

main.write_text(text)
print("v0.7.1 UX patch applied: persistent Save/Reset settings, thinking card, live Markdown, swipe drawer, copy/edit/regenerate actions")

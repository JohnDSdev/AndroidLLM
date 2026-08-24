#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
if not main.exists():
    raise SystemExit("MainActivity.kt is missing")

text = main.read_text()


def replace_once(old: str, new: str):
    global text
    if old not in text:
        raise SystemExit(f"Expected MainActivity text not found: {old!r}")
    text = text.replace(old, new, 1)


# Markdown renderer and Material thinking toggle.
replace_once(
    "import com.google.android.material.dialog.MaterialAlertDialogBuilder\n",
    "import com.google.android.material.dialog.MaterialAlertDialogBuilder\n"
    "import com.google.android.material.materialswitch.MaterialSwitch\n"
    "import io.noties.markwon.Markwon\n",
)
replace_once(
    "    private lateinit var engine: InferenceEngine\n",
    "    private lateinit var engine: InferenceEngine\n"
    "    private lateinit var markwon: Markwon\n",
)
replace_once(
    "        engine = AiChat.getInferenceEngine(applicationContext)\n",
    "        engine = AiChat.getInferenceEngine(applicationContext)\n"
    "        markwon = Markwon.create(this)\n",
)

# Stop-generation state plus live generation-speed state.
replace_once(
    "    @Volatile private var busy = false\n",
    "    @Volatile private var busy = false\n"
    "    @Volatile private var generating = false\n"
    "    @Volatile private var stopRequested = false\n"
    "    @Volatile private var lastTps: Double? = null\n",
)

replace_once(
    "        sendButton.setOnClickListener { sendMessage() }",
    "        sendButton.setOnClickListener { if (generating) stopGeneration() else sendMessage() }",
)

# Keep the most recent generation speed visible in the header.
replace_once(
    '''        headerSubtitle.text = when {
            loadedModelName == chat.modelFile && loadedChatId == chat.id && loadedModelName != null ->
                "On-device • model loaded"
            chat.modelFile != null -> "On-device • model selected"
            else -> "On-device • CPU only"
        }''',
    '''        val baseSubtitle = when {
            loadedModelName == chat.modelFile && loadedChatId == chat.id && loadedModelName != null ->
                "On-device • model loaded"
            chat.modelFile != null -> "On-device • model selected"
            else -> "On-device • CPU only"
        }
        val speed = lastTps?.takeIf { it.isFinite() && it > 0.0 }
        headerSubtitle.text = if (speed != null) {
            "$baseSubtitle • ${formatTps(speed)} tok/s"
        } else {
            baseSubtitle
        }''',
)

# Render saved assistant responses as Markdown while keeping user messages literal.
replace_once(
    "                    text = message.content\n",
    "                    if (fromUser) text = message.content else markwon.setMarkdown(this, message.content)\n",
)

replace_once(
    '''    private fun updateControls() {
        sendButton.isEnabled = !busy
        chatsButton.isEnabled = !busy
        newButton.isEnabled = !busy
        menuButton.isEnabled = !busy
        modelCard.isEnabled = !busy
        inputView.isEnabled = !busy
        sendButton.alpha = if (busy) 0.45f else 1f
    }''',
    '''    private fun updateControls() {
        sendButton.isEnabled = !busy || (generating && !stopRequested)
        chatsButton.isEnabled = !busy
        newButton.isEnabled = !busy
        menuButton.isEnabled = !busy
        modelCard.isEnabled = !busy
        inputView.isEnabled = !busy
        sendButton.alpha = if (busy && !generating) 0.45f else if (stopRequested) 0.55f else 1f
        sendButton.setImageResource(if (generating) R.drawable.ic_stop else R.drawable.ic_send)
        sendButton.contentDescription = if (generating) "Stop generation" else "Send message"
    }''',
)

# Thinking is per-chat and is forwarded to llama.cpp's model chat template.
replace_once(
    '''        val contextParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = dp(14) }
''',
    '''        val contextParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = dp(14) }

        val thinkingSwitch = MaterialSwitch(this).apply {
            text = "Thinking"
            isChecked = chat.thinkingEnabled
            setTextColor(color(R.color.text_primary))
        }
        val thinkingParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = dp(12) }
''',
)
replace_once(
    '''        box.addView(TextView(this).apply {
            text = "512–131072 tokens. Larger contexts use more RAM and can fail if the device cannot allocate the KV cache."
            textSize = 12f
            setTextColor(color(R.color.text_secondary))
            setPadding(dp(2), dp(8), dp(2), 0)
        })''',
    '''        box.addView(TextView(this).apply {
            text = "512–131072 tokens. Larger contexts use more RAM and can fail if the device cannot allocate the KV cache."
            textSize = 12f
            setTextColor(color(R.color.text_secondary))
            setPadding(dp(2), dp(8), dp(2), 0)
        })
        box.addView(thinkingSwitch, thinkingParams)
        box.addView(TextView(this).apply {
            text = "When supported by the model's chat template, this enables or disables reasoning/thinking mode."
            textSize = 12f
            setTextColor(color(R.color.text_secondary))
            setPadding(dp(2), 0, dp(2), 0)
        })''',
)
replace_once(
    '''                chat.contextLength = context
                store.save()''',
    '''                chat.contextLength = context
                chat.thinkingEnabled = thinkingSwitch.isChecked
                store.save()''',
)

replace_once(
    "    private fun sendMessage() {",
    '''    private fun stopGeneration() {
        if (!generating || stopRequested) return
        stopRequested = true
        engine.stopGeneration()
        runOnUiThread {
            updateControls()
            val speed = lastTps
            showStatus(
                if (speed != null && speed > 0.0) "Stopping… ${formatTps(speed)} tok/s" else "Stopping…",
                indeterminate = true,
            )
        }
    }

    private fun sendMessage() {''',
)

# Start a fresh speed sample for each response and pass the thinking preference.
replace_once(
    '''                runOnUiThread {
                    renderHeader()
                    renderMessages()
                    showStatus("Generating…", indeterminate = true)
                }

                val buffer = StringBuilder()
                var lastUi = 0L
                runBlocking {
                    engine.sendUserPrompt(text).collect { token ->''',
    '''                generating = true
                stopRequested = false
                lastTps = null
                runOnUiThread {
                    renderHeader()
                    renderMessages()
                    updateControls()
                    showStatus("Generating…", indeterminate = true)
                }

                val buffer = StringBuilder()
                var lastUi = 0L
                var lastStatsUi = 0L
                var generatedTokens = 0
                var firstTokenNanos = 0L
                runBlocking {
                    engine.sendUserPrompt(text, enableThinking = chat.thinkingEnabled).collect { token ->
                        if (firstTokenNanos == 0L) firstTokenNanos = System.nanoTime()
                        generatedTokens++''',
)

# Update the streaming text frequently and TPS a few times per second. TPS counts
# emitted llama tokens and excludes prompt-processing time by starting at token 1.
replace_once(
    '''                        if (now - lastUi >= 55L) {
                            val snapshot = buffer.toString()
                            runOnUiThread {
                                streamingTextView?.text = snapshot
                                messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
                            }
                            lastUi = now
                        }''',
    '''                        if (now - lastUi >= 55L) {
                            val snapshot = buffer.toString()
                            runOnUiThread {
                                streamingTextView?.text = snapshot
                                messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
                            }
                            lastUi = now
                        }
                        if (firstTokenNanos != 0L && now - lastStatsUi >= 250L) {
                            val elapsedSeconds = (System.nanoTime() - firstTokenNanos) / 1_000_000_000.0
                            if (elapsedSeconds > 0.0) {
                                lastTps = generatedTokens / elapsedSeconds
                                val speed = lastTps!!
                                runOnUiThread {
                                    showStatus("Generating… ${formatTps(speed)} tok/s", indeterminate = true)
                                    renderHeader()
                                }
                            }
                            lastStatsUi = now
                        }''',
)

replace_once(
    '''                assistant.content = buffer.toString()
                store.save()
                runOnUiThread {
                    setBusy(false)
                    renderAll()
                }''',
    '''                if (firstTokenNanos != 0L && generatedTokens > 0) {
                    val elapsedSeconds = (System.nanoTime() - firstTokenNanos) / 1_000_000_000.0
                    if (elapsedSeconds > 0.0) lastTps = generatedTokens / elapsedSeconds
                }
                assistant.content = buffer.toString()
                store.save()
                generating = false
                stopRequested = false
                runOnUiThread {
                    setBusy(false)
                    renderAll()
                }''',
)

replace_once(
    '''                runOnUiThread {
                    setBusy(false)
                    renderAll()
                    showError("Generation failed", t)
                }''',
    '''                generating = false
                stopRequested = false
                runOnUiThread {
                    setBusy(false)
                    renderAll()
                    showError("Generation failed", t)
                }''',
)

# Reset stale speed when the user changes to a new chat/model.
replace_once(
    '''        store.newChat()
        loadedChatId = null
        renderAll()''',
    '''        store.newChat()
        loadedChatId = null
        lastTps = null
        renderAll()''',
)
replace_once(
    '''                store.selectChat(chats[which].id)
                loadedChatId = null
                renderAll()''',
    '''                store.selectChat(chats[which].id)
                loadedChatId = null
                lastTps = null
                renderAll()''',
)

replace_once(
    '''    private fun formatContext(tokens: Int): String = when {''',
    '''    private fun formatTps(tps: Double): String = java.lang.String.format(java.util.Locale.US, "%.1f", tps)

    private fun formatContext(tokens: Int): String = when {''',
)

main.write_text(text)
print("AndroidLLM UI patched: stop button, live TPS, thinking toggle, Markdown rendering")

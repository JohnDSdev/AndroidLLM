#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
gradle = root / "vendor/llama.cpp/examples/llama.android/lib/build.gradle.kts"

for path in (main, gradle):
    if not path.exists():
        raise SystemExit(f"missing generated file: {path}")

text = main.read_text()

# ---------------------------------------------------------------------------
# CPU-only build. v0.7.1 proved that the optimized CPU path is fast and the
# experimental Vulkan PP path is not useful enough to justify its build/runtime
# complexity. Keep the generic GPU plumbing dormant for data/API compatibility,
# but do not compile Vulkan and never request GPU offload.
# ---------------------------------------------------------------------------
gradle_text = gradle.read_text()
vulkan_arg = '                arguments += "-DGGML_VULKAN=ON"\n'
if vulkan_arg not in gradle_text:
    raise SystemExit("GGML_VULKAN build flag not found")
gradle.write_text(gradle_text.replace(vulkan_arg, "", 1))

# The generated load call still has the compatibility boolean as its final arg.
if "                chat.gpuPromptProcessing,\n" not in text:
    raise SystemExit("generated GPU PP load argument not found")
text = text.replace("                chat.gpuPromptProcessing,\n", "                false,\n", 1)

# ---------------------------------------------------------------------------
# Imports for the display-only pretty-mode animator.
# ---------------------------------------------------------------------------
if "import android.os.Handler\n" not in text:
    text = text.replace("import android.os.Bundle\n", "import android.os.Bundle\nimport android.os.Handler\nimport android.os.Looper\n", 1)
if "import java.util.concurrent.atomic.AtomicInteger\n" not in text:
    text = text.replace("import java.io.File\n", "import java.io.File\nimport java.util.concurrent.atomic.AtomicInteger\n", 1)

# ---------------------------------------------------------------------------
# Settings UI: remove GPU PP and replace it with a persistent Pretty mode card.
# The AppStore Save action is the only point at which the staged toggle commits.
# ---------------------------------------------------------------------------
gpu_switch = '''        val gpuSwitch = SwitchCompat(this).apply {
            text = "Experimental GPU prompt processing"
            isChecked = chat.gpuPromptProcessing
            setTextColor(color(R.color.text_primary))
            setPadding(0, dp(8), 0, dp(4))
        }

'''
if gpu_switch not in text:
    raise SystemExit("GPU switch block not found")
pretty_block = '''        val prettySwitch = SwitchCompat(this).apply {
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
                    text = "Reveal generated text smoothly letter by letter. Inference still runs at full speed and the TPS counter always reports the model's real token speed."
                    textSize = 12f
                    setTextColor(color(R.color.text_secondary))
                    setPadding(dp(12), 0, dp(12), dp(11))
                })
            })
        }

'''
text = text.replace(gpu_switch, pretty_block, 1)

thinking_section = '''        box.addView(sectionLabel("Thinking"))
        box.addView(thinkingCard)

'''
if thinking_section not in text:
    raise SystemExit("Thinking settings section not found")
text = text.replace(
    thinking_section,
    thinking_section + '''        box.addView(sectionLabel("Display"))
        box.addView(prettyCard)

''',
    1,
)

experimental_section = '''        box.addView(sectionLabel("Experimental"))
        box.addView(gpuSwitch)
        box.addView(TextView(this).apply {
            text = "Vulkan is used only for batched prompt processing. The final prompt token and all generated tokens stay on CPU. This loads a second model context and can use substantially more RAM/VRAM. If Vulkan cannot initialize, AndroidLLM falls back to CPU."
            textSize = 12f
            setTextColor(color(R.color.text_secondary))
            setPadding(dp(2), 0, dp(2), dp(6))
        })

'''
if experimental_section not in text:
    raise SystemExit("Experimental GPU settings section not found")
text = text.replace(experimental_section, "", 1)

save_gpu = "                        gpuPromptProcessing = gpuSwitch.isChecked,\n"
if save_gpu not in text:
    raise SystemExit("GPU Save argument not found")
text = text.replace(save_gpu, "                        prettyMode = prettySwitch.isChecked,\n", 1)

# ---------------------------------------------------------------------------
# Stable autoscroll. ScrollView.fullScroll() performs focus navigation and our
# selectable Markdown TextViews can briefly win that focus, producing the
# visible top -> bottom jump. Directly pin to the measured bottom after layout
# instead. No focus search, no temporary trip to y=0.
# ---------------------------------------------------------------------------
scroll_helper = '''    private fun scrollMessagesToBottom() {
        messageContainer.post {
            messageScroll.postOnAnimation {
                val viewport = (messageScroll.height - messageScroll.paddingTop - messageScroll.paddingBottom)
                    .coerceAtLeast(0)
                val target = (messageContainer.height - viewport).coerceAtLeast(0)
                if (messageScroll.scrollY != target) {
                    messageScroll.scrollTo(0, target)
                }
            }
        }
    }

'''
update_marker = "    private fun updateControls() {"
if update_marker not in text:
    raise SystemExit("updateControls marker missing")
text = text.replace(update_marker, scroll_helper + update_marker, 1)

focus_scroll = "messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }"
if focus_scroll not in text:
    raise SystemExit("focus-based message autoscroll not found")
text = text.replace(focus_scroll, "scrollMessagesToBottom()")

# ---------------------------------------------------------------------------
# Pretty mode. The model continues producing tokens as fast as possible. A UI
# animator consumes the already-generated character buffer one character at a
# time. TPS remains based on actual emitted llama tokens, not animation speed.
# Markdown is refreshed periodically while individual characters are appended
# between parses, which keeps both the animation and live formatting responsive.
# ---------------------------------------------------------------------------
setup_old = '''                val buffer = StringBuilder()
                var lastUi = 0L
                var lastStatsUi = 0L
                var generatedTokens = 0
                var firstTokenNanos = 0L
                runBlocking {'''
setup_new = '''                val buffer = StringBuilder()
                val prettyEnabled = chat.prettyMode
                val prettyVisibleChars = AtomicInteger(0)
                val prettyHandler = Handler(Looper.getMainLooper())
                var prettyLastMarkdownMs = 0L
                lateinit var prettyRunnable: Runnable
                prettyRunnable = object : Runnable {
                    override fun run() {
                        val totalChars = synchronized(buffer) { buffer.length }
                        val visibleChars = prettyVisibleChars.get()
                        if (visibleChars < totalChars) {
                            val nextVisible = visibleChars + 1
                            val nextChar = synchronized(buffer) {
                                buffer.substring(visibleChars, nextVisible)
                            }
                            streamingTextView?.append(nextChar)
                            prettyVisibleChars.set(nextVisible)

                            val now = System.currentTimeMillis()
                            if (now - prettyLastMarkdownMs >= 180L) {
                                val visibleMarkdown = synchronized(buffer) {
                                    buffer.substring(0, nextVisible)
                                }
                                streamingTextView?.let { markwon.setMarkdown(it, visibleMarkdown) }
                                prettyLastMarkdownMs = now
                            }
                            scrollMessagesToBottom()
                        }

                        val remaining = synchronized(buffer) { buffer.length } - prettyVisibleChars.get()
                        if (generating || remaining > 0) {
                            // Normally one character per ~8 ms. Once inference has
                            // finished, drain any tiny visual backlog faster without
                            // changing the measured model TPS.
                            prettyHandler.postDelayed(this, if (!generating || remaining > 48) 3L else 8L)
                        }
                    }
                }
                if (prettyEnabled) {
                    runOnUiThread { prettyHandler.post(prettyRunnable) }
                }

                var lastUi = 0L
                var lastStatsUi = 0L
                var generatedTokens = 0
                var firstTokenNanos = 0L
                runBlocking {'''
if setup_old not in text:
    raise SystemExit("streaming setup block not found")
text = text.replace(setup_old, setup_new, 1)

hot_old = '''                        buffer.append(token)
                        val now = System.currentTimeMillis()
                        if (now - lastUi >= 220L) {
                            val snapshot = buffer.toString()
                            runOnUiThread {
                                streamingTextView?.let { markwon.setMarkdown(it, snapshot) }
                                scrollMessagesToBottom()
                            }
                            lastUi = now
                        }'''
hot_new = '''                        synchronized(buffer) { buffer.append(token) }
                        val now = System.currentTimeMillis()
                        if (!prettyEnabled && now - lastUi >= 220L) {
                            val snapshot = synchronized(buffer) { buffer.toString() }
                            runOnUiThread {
                                streamingTextView?.let { markwon.setMarkdown(it, snapshot) }
                                scrollMessagesToBottom()
                            }
                            lastUi = now
                        }'''
if hot_old not in text:
    raise SystemExit("live Markdown hot path not found")
text = text.replace(hot_old, hot_new, 1)

final_old = '''                assistant.content = buffer.toString()
                store.save()
                generating = false
                stopRequested = false
                runOnUiThread {
                    setBusy(false)
                    renderAll()
                }'''
final_new = '''                if (prettyEnabled) {
                    // Let the letter animation catch the real model output before
                    // replacing the streaming view with the final rendered message.
                    val deadline = System.currentTimeMillis() + 1800L
                    while (
                        prettyVisibleChars.get() < synchronized(buffer) { buffer.length } &&
                        System.currentTimeMillis() < deadline
                    ) {
                        Thread.sleep(4L)
                    }
                }
                assistant.content = synchronized(buffer) { buffer.toString() }
                store.save()
                generating = false
                stopRequested = false
                runOnUiThread {
                    prettyHandler.removeCallbacks(prettyRunnable)
                    setBusy(false)
                    renderAll()
                }'''
if final_old not in text:
    raise SystemExit("generation finalization block not found")
text = text.replace(final_old, final_new, 1)

# Make the error path terminate the pretty animator naturally. The runnable's
# continuation condition uses `generating`, which this existing path clears.

main.write_text(text)

final_text = main.read_text()
final_gradle = gradle.read_text()
assert "GGML_VULKAN=ON" not in final_gradle
assert "Experimental GPU prompt processing" not in final_text
assert "prettyMode = prettySwitch.isChecked" in final_text
assert 'text = "Pretty mode"' in final_text
assert "scrollMessagesToBottom()" in final_text
assert "fullScroll(View.FOCUS_DOWN)" not in final_text
assert "prettyVisibleChars" in final_text
assert "generatedTokens / elapsedSeconds" in final_text
# Only the load-call argument must be gone. A dormant compatibility field can
# still appear in runtime identity/status code and is forced false by AppStore.
assert "                chat.gpuPromptProcessing,\n" not in final_text

print("v0.7.2 CPU/UX patch applied: stable bottom pinning + pretty letter animation + Vulkan removed")

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


replace_once(
    "    @Volatile private var busy = false\n",
    "    @Volatile private var busy = false\n"
    "    @Volatile private var generating = false\n"
    "    @Volatile private var stopRequested = false\n",
)

replace_once(
    "        sendButton.setOnClickListener { sendMessage() }",
    "        sendButton.setOnClickListener { if (generating) stopGeneration() else sendMessage() }",
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

replace_once(
    "    private fun sendMessage() {",
    '''    private fun stopGeneration() {
        if (!generating || stopRequested) return
        stopRequested = true
        engine.stopGeneration()
        runOnUiThread {
            updateControls()
            showStatus("Stopping…", indeterminate = true)
        }
    }

    private fun sendMessage() {''',
)

replace_once(
    '''                runOnUiThread {
                    renderHeader()
                    renderMessages()
                    showStatus("Generating…", indeterminate = true)
                }

                val buffer = StringBuilder()''',
    '''                generating = true
                stopRequested = false
                runOnUiThread {
                    renderHeader()
                    renderMessages()
                    updateControls()
                    showStatus("Generating…", indeterminate = true)
                }

                val buffer = StringBuilder()''',
)

replace_once(
    '''                assistant.content = buffer.toString()
                store.save()
                runOnUiThread {
                    setBusy(false)
                    renderAll()
                }''',
    '''                assistant.content = buffer.toString()
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

main.write_text(text)
print("AndroidLLM UI patched: send button becomes a stop button during generation")

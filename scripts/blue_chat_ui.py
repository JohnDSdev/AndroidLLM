#!/usr/bin/env python3
"""Apply the display-only redesign after the existing inference patch chain."""
from pathlib import Path
import shutil
root = Path(__file__).resolve().parents[1]
main = root/'app/src/main/java/com/johndsdev/androidllm/MainActivity.kt'
s = main.read_text()
def replace(old, new):
    global s
    if s.count(old) != 1:
        raise SystemExit(f'Expected one UI anchor: {old[:100]!r}, got {s.count(old)}')
    s = s.replace(old, new, 1)
for line in ['    private lateinit var newButton: ImageButton\n', '        newButton = findViewById(R.id.newButton)\n', '        newButton.setOnClickListener { createNewChat() }\n', '        newButton.isEnabled = !busy\n']:
    replace(line, '')
replace('        menuButton.setOnClickListener { showMenuDialog() }', '''        menuButton.setOnClickListener {
            drawerLayout.closeDrawer(GravityCompat.START)
            showSettingsDialog()
        }
        findViewById<View>(R.id.appOptionsButton).setOnClickListener {
            drawerLayout.closeDrawer(GravityCompat.START)
            showMenuDialog()
        }''')
replace('        contextView.text = formatContext(chat.contextLength)', '''        contextView.text = formatContext(chat.contextLength)
        modelCard.contentDescription = "Choose model: ${chat.modelFile?.removeSuffix(".gguf") ?: "none selected"}, ${formatContext(chat.contextLength)} context"''')
replace('                text = "Choose a local model above and start chatting."', '                text = "Your ideas, your device.\\nChoose a model below to get started."')
replace('                typeface = Typeface.DEFAULT_BOLD\n                gravity = Gravity.CENTER', '                typeface = Typeface.create("sans-serif", Typeface.NORMAL)\n                gravity = Gravity.CENTER')
replace('    private var currentModelDialog: Dialog? = null', '''    private var currentModelDialog: Dialog? = null
    private var activeReveal: PrettyTextReveal? = null''')
a = s.index('        var shown = 0\n        var finished = false // accessed only on UI thread')
b = s.index('        Thread {', a)
s = s[:a]+'''        val reveal = PrettyTextReveal(
            buffer, chat.prettyMode,
            object : PrettyTextReveal.Scheduler {
                override fun post(task: Runnable, delay: Long) { handler.postDelayed(task, delay) }
                override fun remove(task: Runnable) { handler.removeCallbacks(task) }
            },
            { android.os.SystemClock.uptimeMillis() },
            { delta ->
                if (isDestroyed) activeReveal?.cancel()
                else streamingTextView?.append(delta)
            },
        )
        activeReveal = reveal
        reveal.start()
'''+s[b:]
replace('                    handler.post(reveal)\n', '')
replace('                        synchronized(buffer) { buffer.setLength(0); shown = 0 }', '''                        synchronized(buffer) { buffer.setLength(0) }
                        reveal.reset()''')
replace('''                    finished = true
                    handler.removeCallbacks(reveal)
                    setBusy(false)
                    renderAll()''', '''                    if (isDestroyed) {
                        reveal.cancel()
                        activeReveal = null
                    } else {
                        reveal.finish {
                            activeReveal = null
                            setBusy(false)
                            renderAll()
                        }
                    }''')
replace('    private fun bindUi() {', '''    override fun onDestroy() {
        activeReveal?.cancel()
        activeReveal = null
        super.onDestroy()
    }

    private fun bindUi() {''')
# Keep drawer navigation usable during visual catch-up but protect actual changes.
replace('        modelCard.isEnabled = !busy\n', '        modelCard.isEnabled = !busy\n        drawerNewChatButton.isEnabled = !busy\n        findViewById<View>(R.id.appOptionsButton).isEnabled = !busy\n')
main.write_text(s)
for path in (root/'ui-res').rglob('*.xml'):
    target = root/'app/src/main/res'/path.relative_to(root/'ui-res')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
print('Blue chat UI applied; inference producer and native runtime unchanged')

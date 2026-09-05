#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
if not main.exists():
    raise SystemExit("generated MainActivity.kt is missing")

text = main.read_text()

# ---------------------------------------------------------------------------
# v0.7.5 streaming Markdown performance patch.
#
# Keep the inference hot path close to v0.7.0: append only newly generated text
# to the TextView on the normal UI cadence. Reparse the whole visible Markdown
# only when syntax likely changed, and never more often than the syntax throttle
# or the slow periodic refresh. This prevents response-length-squared copying and
# Markwon allocation/GC pressure from competing with llama.cpp.
#
# Open fenced code blocks remain plain while they are being generated. A closing
# ``` makes Markdown eligible for refresh again; the existing completed-message
# renderer turns finished fences into the native code cards.
# ---------------------------------------------------------------------------

pretty_state_old = '''                var prettyLastMarkdownMs = 0L
                lateinit var prettyRunnable: Runnable'''
pretty_state_new = '''                var prettyLastMarkdownMs = System.currentTimeMillis()
                var prettyMarkdownSignalPending = false
                var prettyFenceOpen = false
                var prettyBacktickRun = 0
                lateinit var prettyRunnable: Runnable'''
if pretty_state_old not in text:
    raise SystemExit("pretty Markdown state anchor not found")
text = text.replace(pretty_state_old, pretty_state_new, 1)

pretty_refresh_old = '''                            val now = System.currentTimeMillis()
                            if (now - prettyLastMarkdownMs >= 180L) {
                                val visibleMarkdown = synchronized(buffer) {
                                    buffer.substring(0, nextVisible)
                                }
                                streamingTextView?.let { markwon.setMarkdown(it, visibleMarkdown) }
                                prettyLastMarkdownMs = now
                            }
                            scrollMessagesToBottom()'''
pretty_refresh_new = '''                            val visibleChar = nextChar[0]
                            if (visibleChar == '`') {
                                prettyBacktickRun += 1
                                if (prettyBacktickRun == 3) {
                                    prettyFenceOpen = !prettyFenceOpen
                                    prettyMarkdownSignalPending = true
                                    prettyBacktickRun = 0
                                }
                            } else {
                                prettyBacktickRun = 0
                                if (visibleChar == '\\n' || visibleChar == '*' || visibleChar == '#' || visibleChar == '_') {
                                    prettyMarkdownSignalPending = true
                                }
                            }

                            val now = System.currentTimeMillis()
                            val syntaxRefreshDue =
                                prettyMarkdownSignalPending && now - prettyLastMarkdownMs >= 450L
                            val periodicRefreshDue = now - prettyLastMarkdownMs >= 900L
                            if (!prettyFenceOpen && (syntaxRefreshDue || periodicRefreshDue)) {
                                val visibleMarkdown = synchronized(buffer) {
                                    buffer.substring(0, nextVisible)
                                }
                                streamingTextView?.let { markwon.setMarkdown(it, visibleMarkdown) }
                                prettyMarkdownSignalPending = false
                                prettyLastMarkdownMs = now
                            }
                            scrollMessagesToBottom()'''
if pretty_refresh_old not in text:
    raise SystemExit("pretty 180 ms Markdown refresh block not found")
text = text.replace(pretty_refresh_old, pretty_refresh_new, 1)

normal_state_old = '''                var lastUi = 0L
                var lastStatsUi = 0L'''
normal_state_new = '''                var lastUi = 0L
                val liveUiDelta = StringBuilder()
                var lastMarkdownUi = System.currentTimeMillis()
                var markdownSignalPending = false
                var markdownFenceOpen = false
                var markdownBacktickRun = 0
                var lastStatsUi = 0L'''
if normal_state_old not in text:
    raise SystemExit("normal streaming state anchor not found")
text = text.replace(normal_state_old, normal_state_new, 1)

hot_old = '''                        synchronized(buffer) { buffer.append(token) }
                        val now = System.currentTimeMillis()
                        if (!prettyEnabled && now - lastUi >= 220L) {
                            val snapshot = synchronized(buffer) { buffer.toString() }
                            runOnUiThread {
                                streamingTextView?.let { markwon.setMarkdown(it, snapshot) }
                                scrollMessagesToBottom()
                            }
                            lastUi = now
                        }'''
hot_new = '''                        synchronized(buffer) { buffer.append(token) }
                        if (!prettyEnabled) {
                            liveUiDelta.append(token)

                            for (ch in token) {
                                if (ch == '`') {
                                    markdownBacktickRun += 1
                                    if (markdownBacktickRun == 3) {
                                        markdownFenceOpen = !markdownFenceOpen
                                        markdownSignalPending = true
                                        markdownBacktickRun = 0
                                    }
                                } else {
                                    markdownBacktickRun = 0
                                    if (ch == '\\n' || ch == '*' || ch == '#' || ch == '_') {
                                        markdownSignalPending = true
                                    }
                                }
                            }

                            val now = System.currentTimeMillis()
                            if (now - lastUi >= 120L) {
                                val delta = liveUiDelta.toString()
                                liveUiDelta.setLength(0)

                                val syntaxRefreshDue =
                                    markdownSignalPending && now - lastMarkdownUi >= 450L
                                val periodicRefreshDue = now - lastMarkdownUi >= 900L
                                val shouldRefreshMarkdown =
                                    !markdownFenceOpen && (syntaxRefreshDue || periodicRefreshDue)
                                val snapshot = if (shouldRefreshMarkdown) {
                                    synchronized(buffer) { buffer.toString() }
                                } else {
                                    null
                                }
                                if (shouldRefreshMarkdown) {
                                    markdownSignalPending = false
                                    lastMarkdownUi = now
                                }

                                runOnUiThread {
                                    streamingTextView?.let { view ->
                                        if (snapshot != null) {
                                            markwon.setMarkdown(view, snapshot)
                                        } else if (delta.isNotEmpty()) {
                                            view.append(delta)
                                        }
                                    }
                                    scrollMessagesToBottom()
                                }
                                lastUi = now
                            }
                        }'''
if hot_old not in text:
    raise SystemExit("220 ms full-Markdown hot path not found")
text = text.replace(hot_old, hot_new, 1)

main.write_text(text)

final_text = main.read_text()
assert "now - lastUi >= 220L" not in final_text
assert "now - prettyLastMarkdownMs >= 180L" not in final_text
assert "now - lastUi >= 120L" in final_text
assert "now - lastMarkdownUi >= 900L" in final_text
assert "now - prettyLastMarkdownMs >= 900L" in final_text
assert "view.append(delta)" in final_text
assert "markwon.setMarkdown(view, snapshot)" in final_text
assert "markdownFenceOpen" in final_text
assert "prettyFenceOpen" in final_text

print("v0.7.5 streaming patch applied: delta appends + syntax/900 ms Markdown refresh + fence suppression")

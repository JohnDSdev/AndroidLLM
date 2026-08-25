#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
if not main.exists():
    raise SystemExit("generated MainActivity.kt is missing")

text = main.read_text()

# Keep the compact model chip readable instead of spending most of the header on
# the .gguf suffix and a redundant "ctx" label.
old_model = '        modelNameView.text = chat.modelFile ?: "Choose a GGUF model"\n'
new_model = '        modelNameView.text = chat.modelFile?.removeSuffix(".gguf") ?: "Choose model"\n'
if old_model not in text:
    raise SystemExit("model label line not found")
text = text.replace(old_model, new_model, 1)

old_context = '        contextView.text = "${formatContext(chat.contextLength)} ctx"\n'
new_context = '        contextView.text = formatContext(chat.contextLength)\n'
if old_context not in text:
    raise SystemExit("context label line not found")
text = text.replace(old_context, new_context, 1)

# Replace the old card-for-everything transcript with a ChatGPT-style layout:
# user messages are compact right-side bubbles; assistant messages sit directly
# on the page with generous spacing and Markdown formatting.
start_marker = "    private fun renderMessages() {"
end_marker = "    private fun updateControls() {"
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("renderMessages function boundaries not found")

new_render = r'''    private fun renderMessages() {
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
                    val row = LinearLayout(this).apply {
                        orientation = LinearLayout.HORIZONTAL
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
                    row.addView(
                        card,
                        LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.WRAP_CONTENT,
                            LinearLayout.LayoutParams.WRAP_CONTENT,
                        ),
                    )
                    messageContainer.addView(
                        row,
                        LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            LinearLayout.LayoutParams.WRAP_CONTENT,
                        ),
                    )
                } else {
                    val row = LinearLayout(this).apply {
                        orientation = LinearLayout.VERTICAL
                        gravity = Gravity.START
                        setPadding(0, dp(10), 0, dp(13))
                    }
                    val body = TextView(this).apply {
                        textSize = 16f
                        setTextColor(color(R.color.assistant_text))
                        setTextIsSelectable(true)
                        setLineSpacing(0f, 1.12f)
                        setPadding(0, dp(2), 0, dp(2))
                        if (isStreamingAssistant) {
                            text = message.content
                        } else {
                            markwon.setMarkdown(this, message.content)
                        }
                    }
                    row.addView(
                        body,
                        LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            LinearLayout.LayoutParams.WRAP_CONTENT,
                        ),
                    )
                    messageContainer.addView(
                        row,
                        LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            LinearLayout.LayoutParams.WRAP_CONTENT,
                        ),
                    )
                    if (isStreamingAssistant) {
                        streamingTextView = body
                    }
                }
            }
        }
        messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
    }

'''
text = text[:start] + new_render + text[end:]

# Build-time guards. If another patch changes the transcript function enough to
# undo the redesign, fail loudly instead of quietly shipping the old wall of cards.
assert 'What can I help with?' in text
assert 'setCardBackgroundColor(color(R.color.user_bubble))' in text
assert 'markwon.setMarkdown(this, message.content)' in text
assert 'strokeWidth = if (fromUser)' not in text

main.write_text(text)
print("ChatGPT-style transcript UI patch applied")

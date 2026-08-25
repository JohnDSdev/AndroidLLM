#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
interface = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/InferenceEngine.kt"
impl = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/internal/InferenceEngineImpl.kt"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"

for path in (interface, impl, cpp, main):
    if not path.exists():
        raise SystemExit(f"Missing generated file: {path}")


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1))


# No artificial response-token cap. A response now ends only on EOG, explicit
# Stop, or the configured context window becoming full.
replace_once(
    interface,
    "fun sendUserPrompt(message: String, predictLength: Int = DEFAULT_PREDICT_LENGTH, enableThinking: Boolean = true): Flow<String>",
    "fun sendUserPrompt(message: String, enableThinking: Boolean = true): Flow<String>",
)
replace_once(
    impl,
    "private external fun processUserPrompt(userPrompt: String, predictLength: Int, enableThinking: Boolean): Int",
    "private external fun processUserPrompt(userPrompt: String, enableThinking: Boolean): Int",
)
replace_once(
    impl,
    """    override fun sendUserPrompt(
        message: String,
        predictLength: Int,
        enableThinking: Boolean,
    ): Flow<String> = flow {""",
    """    override fun sendUserPrompt(
        message: String,
        enableThinking: Boolean,
    ): Flow<String> = flow {""",
)
replace_once(
    impl,
    "processUserPrompt(message, predictLength, enableThinking).let { result ->",
    "processUserPrompt(message, enableThinking).let { result ->",
)

cpp_text = cpp.read_text()
old_sig = """        jobject /*unused*/,
        jstring juser_prompt,
        jint n_predict,
        jboolean jenable_thinking
) {"""
new_sig = """        jobject /*unused*/,
        jstring juser_prompt,
        jboolean jenable_thinking
) {"""
if old_sig not in cpp_text:
    raise SystemExit("Could not locate processUserPrompt JNI signature")
cpp_text = cpp_text.replace(old_sig, new_sig, 1)

old_stop_pos = "stop_generation_position = current_position + user_prompt_size + n_predict;"
new_stop_pos = "stop_generation_position = g_context_size - OVERFLOW_HEADROOM;"
if old_stop_pos not in cpp_text:
    raise SystemExit("Could not locate artificial prediction stop position")
cpp_text = cpp_text.replace(old_stop_pos, new_stop_pos, 1)

old_shift_generation = """    // Infinite text generation via context shifting
    if (current_position >= g_context_size - OVERFLOW_HEADROOM) {
        LOGw("%s: Context full! Shifting...", __func__);
        shift_context();
    }

    // Stop if reaching the marked position"""
new_shift_generation = """    // A response may use all remaining configured context, but does not shift the
    // context indefinitely. Once the window is full, generation is complete.
    if (current_position >= g_context_size - OVERFLOW_HEADROOM) {
        LOGi("%s: STOP: configured context window exhausted at %d tokens", __func__, current_position);
        return nullptr;
    }

    // Stop if reaching the marked position"""
if old_shift_generation not in cpp_text:
    raise SystemExit("Could not locate generation context-shift block")
cpp_text = cpp_text.replace(old_shift_generation, new_shift_generation, 1)

# Remove verbose logging from token hot paths. Android log writes are expensive
# enough to introduce visible stalls during token-by-token generation.
for block in (
    '''    for (auto id: system_tokens) {
        LOGv("token: `%s`\\t -> `%d`", common_token_to_piece(g_context, id).c_str(), id);
    }
''',
    '''    for (auto id: user_tokens) {
        LOGv("token: `%s`\\t -> `%d`", common_token_to_piece(g_context, id).c_str(), id);
    }
''',
):
    if block in cpp_text:
        cpp_text = cpp_text.replace(block, "", 1)

cpp_text = cpp_text.replace(
    '''        LOGv("id: %d,\\tcached: `%s`,\\tnew: `%s`", new_token_id, cached_token_chars.c_str(), new_token_chars.c_str());

        assistant_ss << cached_token_chars;''',
    '''        assistant_ss << cached_token_chars;''',
    1,
)
cpp_text = cpp_text.replace(
    '''    } else {
        LOGv("id: %d,\\tappend to cache", new_token_id);
        result = env->NewStringUTF("");
    }''',
    '''    } else {
        result = env->NewStringUTF("");
    }''',
    1,
)
cpp.write_text(cpp_text)

# Reduce Kotlin/Android allocation and redraw pressure while streaming. Stream
# only deltas at ~8 Hz and update the TPS status at ~2 Hz.
main_text = main.read_text()
old_stream_setup = """                val buffer = StringBuilder()
                var lastUi = 0L
                var lastStatsUi = 0L
                var generatedTokens = 0
                var firstTokenNanos = 0L"""
new_stream_setup = """                val buffer = StringBuilder()
                val uiChunk = StringBuilder()
                var lastUi = 0L
                var lastStatsUi = 0L
                var generatedTokens = 0
                var firstTokenNanos = 0L"""
if old_stream_setup not in main_text:
    raise SystemExit("Could not locate streaming setup")
main_text = main_text.replace(old_stream_setup, new_stream_setup, 1)

old_token_hot_path = """                        buffer.append(token)
                        assistant.content = buffer.toString()
                        val now = System.currentTimeMillis()
                        if (now - lastUi >= 55L) {
                            val snapshot = buffer.toString()
                            runOnUiThread {
                                streamingTextView?.text = snapshot
                                messageScroll.post { messageScroll.fullScroll(View.FOCUS_DOWN) }
                            }
                            lastUi = now
                        }"""
new_token_hot_path = """                        buffer.append(token)
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
                        }"""
if old_token_hot_path not in main_text:
    raise SystemExit("Could not locate allocation-heavy token UI path")
main_text = main_text.replace(old_token_hot_path, new_token_hot_path, 1)

main_text = main_text.replace("now - lastStatsUi >= 250L", "now - lastStatsUi >= 500L", 1)
old_stats_ui = '''                                runOnUiThread {
                                    showStatus("Generating… ${formatTps(speed)} tok/s", indeterminate = true)
                                    renderHeader()
                                }'''
new_stats_ui = '''                                runOnUiThread {
                                    showStatus("Generating… ${formatTps(speed)} tok/s", indeterminate = true)
                                }'''
if old_stats_ui not in main_text:
    raise SystemExit("Could not locate TPS header redraw")
main_text = main_text.replace(old_stats_ui, new_stats_ui, 1)
main.write_text(main_text)

# Build-time regression guards.
interface_text = interface.read_text()
impl_text = impl.read_text()
cpp_text = cpp.read_text()
main_text = main.read_text()
assert "predictLength" not in interface_text
assert "processUserPrompt(userPrompt: String, enableThinking: Boolean)" in impl_text
assert "stop_generation_position = g_context_size - OVERFLOW_HEADROOM;" in cpp_text
assert "Context full! Shifting" not in cpp_text
assert 'LOGv("id: %d' not in cpp_text
assert main_text.count("assistant.content = buffer.toString()") == 1
assert "streamingTextView?.append(chunk)" in main_text
assert "now - lastUi >= 120L" in main_text
assert "now - lastStatsUi >= 500L" in main_text

print("runtime performance patch applied: context-only generation, no token hot-path logs, delta UI streaming")

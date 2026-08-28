#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
impl = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/internal/InferenceEngineImpl.kt"
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"

for path in (impl, main):
    if not path.exists():
        raise SystemExit(f"missing generated file: {path}")


def replace_function(source: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = source.find(start_marker)
    end = source.find(end_marker, start)
    if start < 0 or end < 0:
        raise SystemExit(f"function boundaries not found: {start_marker!r} -> {end_marker!r}")
    return source[:start] + replacement.rstrip() + "\n\n" + source[end:]


# ---------------------------------------------------------------------------
# A system prompt is also our conversation/KV reset operation. llama.cpp's
# processSystemPrompt() already clears chat_msgs, current_position and the KV
# cache before decoding the new prompt, so there is no reason to free/reload the
# several-GB model just to bind another chat to the same resident weights.
# ---------------------------------------------------------------------------
impl_text = impl.read_text()
ready_guard = '''            check(_readyForSystemPrompt) { "System prompt must be set ** RIGHT AFTER ** model loaded!" }\n'''
if ready_guard not in impl_text:
    raise SystemExit("one-shot system-prompt guard not found")
impl_text = impl_text.replace(
    ready_guard,
    '''            // AndroidLLM may reset/rebind a conversation while the model weights stay loaded.\n''',
    1,
)
impl.write_text(impl_text)

main_text = main.read_text()

# Conversation invalidation must only invalidate KV/chat identity. Runtime/model
# invalidation remains separate for actual context/thread/sampling changes.
old_invalidate = '''    private fun invalidateLoadedConversation() {
        loadedChatId = null
        loadedContextLength = null
        loadedRuntimeKey = null
        gpuPpActive = false
        lastTps = null
    }'''
new_invalidate = '''    private fun invalidateLoadedConversation() {
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
    }'''
if old_invalidate not in main_text:
    raise SystemExit("conversation invalidation block not found")
main_text = main_text.replace(old_invalidate, new_invalidate, 1)

# Settings can really change context/thread/sampler construction, so keep their
# stronger invalidation semantics. Edit/regenerate/chat switching stay light.
settings_start = main_text.find("    private fun showSettingsDialog() {")
settings_end = main_text.find("    private fun showModelsDialog() {", settings_start)
if settings_start < 0 or settings_end < 0:
    raise SystemExit("settings function boundaries not found")
settings_block = main_text[settings_start:settings_end]
if "invalidateLoadedConversation()" not in settings_block:
    raise SystemExit("settings invalidation calls not found")
settings_block = settings_block.replace("invalidateLoadedConversation()", "invalidateLoadedRuntime()")
main_text = main_text[:settings_start] + settings_block + main_text[settings_end:]

# A newly-created chat inherits the currently resident model. This makes model
# selection app-level while the process is alive, instead of presenting an empty
# model selector and then needlessly reloading the exact same file.
new_chat = '''    private fun createNewChat() {
        if (busy) return
        val chat = store.newChat()
        loadedModelName?.let { loaded ->
            if (chat.modelFile != loaded) {
                chat.modelFile = loaded
                store.save()
            }
        }
        invalidateLoadedConversation()
        renderAll()
    }'''
main_text = replace_function(
    main_text,
    "    private fun createNewChat() {",
    "    private fun showChatsDialog() {",
    new_chat,
)

# Existing chats also follow the currently resident model when switching via the
# drawer. Deliberately selecting another model in the model picker can still
# replace the resident model; merely changing chats cannot.
drawer_old = '''                        store.selectChat(chat.id)
                        invalidateLoadedConversation()
                        drawerLayout.closeDrawer(GravityCompat.START)'''
drawer_new = '''                        store.selectChat(chat.id)
                        loadedModelName?.let { loaded ->
                            val selectedChat = store.currentChat()
                            if (selectedChat.modelFile != loaded) {
                                selectedChat.modelFile = loaded
                                store.save()
                            }
                        }
                        invalidateLoadedConversation()
                        drawerLayout.closeDrawer(GravityCompat.START)'''
if drawer_old not in main_text:
    raise SystemExit("drawer chat-switch block not found")
main_text = main_text.replace(drawer_old, drawer_new, 1)

# Deleting the active chat can select/create another chat. Keep the same loaded
# model attached to that replacement too.
delete_old = '''                    store.deleteChat(chatId)
                    invalidateLoadedConversation()
                    dialog.dismiss()'''
delete_new = '''                    store.deleteChat(chatId)
                    loadedModelName?.let { loaded ->
                        val selectedChat = store.currentChat()
                        if (selectedChat.modelFile != loaded) {
                            selectedChat.modelFile = loaded
                            store.save()
                        }
                    }
                    invalidateLoadedConversation()
                    dialog.dismiss()'''
if delete_old not in main_text:
    raise SystemExit("drawer chat-delete block not found")
main_text = main_text.replace(delete_old, delete_new, 1)

# Model runtime identity contains only things that require rebuilding the native
# model/context/sampler. Chat id and system prompt are conversation state, not
# model-weight identity.
runtime_key = '''    private fun runtimeKey(chat: ChatSession): String = listOf(
        chat.contextLength,
        chat.generationThreads,
        chat.promptThreads,
        chat.batchSize,
        chat.temperature,
        chat.topK,
        chat.topP,
        chat.minP,
    ).joinToString("|")'''
main_text = replace_function(
    main_text,
    "    private fun runtimeKey(chat: ChatSession): String = listOf(",
    "    private fun effectiveSystemPrompt(chat: ChatSession): String {",
    runtime_key,
)

# The hot fix: if the same model + runtime is already resident, switching chats
# only clears/rebuilds conversation/KV state through setSystemPrompt(). The full
# cleanUp()/loadModel() path is reserved for an actually different model/runtime.
ensure_loaded = '''    private fun ensureModelLoaded(chat: ChatSession) {
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
                runOnUiThread {
                    showStatus("Switching chat…", indeterminate = true)
                }
                runBlocking {
                    // Native processSystemPrompt resets chat/KV state but does NOT
                    // unload g_model, so the several-GB weight mapping stays hot.
                    engine.setSystemPrompt(effectiveSystemPrompt(chat))
                }
                loadedChatId = chat.id
                runOnUiThread { renderHeader() }
            }
            return
        }

        unloadModelBlocking()
        waitForNativeInitialization()

        runOnUiThread {
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
        runOnUiThread { renderHeader() }
    }'''
main_text = replace_function(
    main_text,
    "    private fun ensureModelLoaded(chat: ChatSession) {",
    "    private fun waitForNativeInitialization() {",
    ensure_loaded,
)

# Header should describe the weights as loaded even between selecting a chat and
# rebinding its KV state. loadedChatId tracks conversation state, not residency.
old_loaded_here = "        val loadedHere = loadedModelName == chat.modelFile && loadedChatId == chat.id && loadedModelName != null\n"
new_loaded_here = "        val loadedHere = loadedModelName == chat.modelFile && loadedModelName != null\n"
if old_loaded_here not in main_text:
    raise SystemExit("header loaded-state anchor not found")
main_text = main_text.replace(old_loaded_here, new_loaded_here, 1)

main.write_text(main_text)

final_impl = impl.read_text()
final_main = main.read_text()
assert "System prompt must be set ** RIGHT AFTER ** model loaded!" not in final_impl
assert "private fun invalidateLoadedRuntime()" in final_main
assert "Switching chat…" in final_main
assert "sameResidentModel" in final_main
assert "engine.setSystemPrompt(effectiveSystemPrompt(chat))" in final_main
assert "loadedRuntimeKey = key" in final_main
assert "chat.systemPrompt," not in final_main[final_main.find("private fun runtimeKey"):final_main.find("private fun effectiveSystemPrompt")]
assert "loadedChatId == chat.id &&" not in final_main[final_main.find("private fun renderHeader"):final_main.find("private fun renderMessages")]

print("persistent model patch applied: chat switches reset KV only; weights stay resident until unload/model change")

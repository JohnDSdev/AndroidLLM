#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
if not llama.exists():
    raise SystemExit("vendor/llama.cpp is missing; clone the pinned llama.cpp release first")

interface = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/InferenceEngine.kt"
impl = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/internal/InferenceEngineImpl.kt"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
chat_h = llama / "common/chat.h"
chat_cpp = llama / "common/chat.cpp"
cmake = llama / "examples/llama.android/lib/src/main/cpp/CMakeLists.txt"
gradle = llama / "examples/llama.android/lib/build.gradle.kts"


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1))


# Configurable context length.
replace_once(
    interface,
    "suspend fun loadModel(pathToModel: String)",
    "suspend fun loadModel(pathToModel: String, contextLength: Int)",
)

# Public stop control plus a per-request thinking flag. The latter is passed into
# llama.cpp's Jinja chat-template machinery, so models whose templates support
# `enable_thinking` (Qwen3/Qwen3.5 and others) can actually switch modes.
replace_once(
    interface,
    "fun sendUserPrompt(message: String, predictLength: Int = DEFAULT_PREDICT_LENGTH): Flow<String>",
    "fun sendUserPrompt(message: String, predictLength: Int = DEFAULT_PREDICT_LENGTH, enableThinking: Boolean = true): Flow<String>\n\n    /** Stops an in-progress response without unloading the model. */\n    fun stopGeneration()",
)
replace_once(
    impl,
    "private external fun prepare(): Int",
    "private external fun prepare(contextLength: Int): Int\n\n    @FastNative\n    private external fun lastNativeError(): String",
)
replace_once(
    impl,
    "private external fun processUserPrompt(userPrompt: String, predictLength: Int): Int",
    "private external fun processUserPrompt(userPrompt: String, predictLength: Int, enableThinking: Boolean): Int\n\n    @FastNative\n    private external fun finishStoppedGeneration()",
)
replace_once(
    impl,
    "override suspend fun loadModel(pathToModel: String) =",
    "override suspend fun loadModel(pathToModel: String, contextLength: Int) =",
)
replace_once(
    impl,
    """                load(pathToModel).let {
                    // TODO-han.yin: find a better way to pass other error codes
                    if (it != 0) throw UnsupportedArchitectureException()
                }
                prepare().let {""",
    """                load(pathToModel).let {
                    if (it != 0) {
                        val nativeMessage = lastNativeError().trim()
                        throw IOException(
                            nativeMessage.ifBlank {
                                "llama.cpp could not load this GGUF model. The file may be incomplete, corrupt, or incompatible with this llama.cpp release."
                            }
                        )
                    }
                }
                prepare(contextLength).let {""",
)
replace_once(
    impl,
    """    override fun sendUserPrompt(
        message: String,
        predictLength: Int,
    ): Flow<String> = flow {""",
    """    override fun sendUserPrompt(
        message: String,
        predictLength: Int,
        enableThinking: Boolean,
    ): Flow<String> = flow {""",
)
replace_once(
    impl,
    """            Log.i(TAG, "Sending user prompt...")
            _readyForSystemPrompt = false
            _state.value = InferenceEngine.State.ProcessingUserPrompt""",
    """            Log.i(TAG, "Sending user prompt...")
            _readyForSystemPrompt = false
            _cancelGeneration = false
            _state.value = InferenceEngine.State.ProcessingUserPrompt""",
)
replace_once(
    impl,
    "processUserPrompt(message, predictLength).let { result ->",
    "processUserPrompt(message, predictLength, enableThinking).let { result ->",
)
replace_once(
    impl,
    """            if (_cancelGeneration) {
                Log.i(TAG, "Assistant generation aborted per requested.")
            } else {
                Log.i(TAG, "Assistant generation complete. Awaiting user prompt...")
            }
            _state.value = InferenceEngine.State.ModelReady""",
    """            if (_cancelGeneration) {
                Log.i(TAG, "Assistant generation aborted per requested.")
                finishStoppedGeneration()
            } else {
                Log.i(TAG, "Assistant generation complete. Awaiting user prompt...")
            }
            _cancelGeneration = false
            _state.value = InferenceEngine.State.ModelReady""",
)
replace_once(
    impl,
    """        } catch (e: CancellationException) {
            Log.i(TAG, "Assistant generation's flow collection cancelled.")
            _state.value = InferenceEngine.State.ModelReady""",
    """        } catch (e: CancellationException) {
            Log.i(TAG, "Assistant generation's flow collection cancelled.")
            _cancelGeneration = false
            _state.value = InferenceEngine.State.ModelReady""",
)
replace_once(
    impl,
    """    }.flowOn(llamaDispatcher)

    /**
     * Benchmark the model""",
    """    }.flowOn(llamaDispatcher)

    override fun stopGeneration() {
        if (
            _state.value is InferenceEngine.State.Generating ||
            _state.value is InferenceEngine.State.ProcessingUserPrompt
        ) {
            _cancelGeneration = true
        }
    }

    /**
     * Benchmark the model""",
)

# Teach common_chat_format_single to forward enable_thinking to Jinja templates.
replace_once(
    chat_h,
    """                                      bool                                 add_ass,
                                      bool                                 use_jinja);""",
    """                                      bool                                 add_ass,
                                      bool                                 use_jinja,
                                      bool                                 enable_thinking = true);""",
)
replace_once(
    chat_cpp,
    """                                      bool                                 add_ass,
                                      bool                                 use_jinja) {
    common_chat_templates_inputs inputs;
    inputs.use_jinja = use_jinja;""",
    """                                      bool                                 add_ass,
                                      bool                                 use_jinja,
                                      bool                                 enable_thinking) {
    common_chat_templates_inputs inputs;
    inputs.use_jinja = use_jinja;
    inputs.enable_thinking = enable_thinking;""",
)

# Native loader diagnostics, context size, thinking-aware formatting, and clean
# finalization of partial assistant text after the user hits Stop.
cpp_text = cpp.read_text()
marker = "static common_sampler                   * g_sampler;"
if marker not in cpp_text:
    raise SystemExit("Could not locate llama.cpp Android globals")
cpp_text = cpp_text.replace(
    marker,
    marker + '''\nstatic int                                g_context_size = DEFAULT_CONTEXT_SIZE;
static std::string                        g_last_native_error;

static void aichat_capture_log_callback(enum ggml_log_level level, const char * text, void * /*user*/) {
    aichat_android_log_callback(level, text, nullptr);
    if (level == GGML_LOG_LEVEL_ERROR || level == GGML_LOG_LEVEL_WARN) {
        if (g_last_native_error.size() > 12000) {
            g_last_native_error.erase(0, g_last_native_error.size() - 8000);
        }
        g_last_native_error.append(text ? text : "");
    }
}''',
    1,
)
cpp_text = cpp_text.replace(
    "llama_log_set(aichat_android_log_callback, nullptr);",
    "llama_log_set(aichat_capture_log_callback, nullptr);",
    1,
)

old_backend_init = '''    // Loading all CPU backend variants
    const auto *path_to_backend = env->GetStringUTFChars(nativeLibDir, 0);
    LOGi("Loading backends from %s", path_to_backend);
    ggml_backend_load_all_from_path(path_to_backend);
    env->ReleaseStringUTFChars(nativeLibDir, path_to_backend);

    // Initialize backends
    llama_backend_init();
    LOGi("Backend initiated; Log handler set.");'''
new_backend_init = '''    (void) env;
    (void) nativeLibDir;

    // The CPU backend is linked into the app, so registry construction is enough.
    llama_backend_init();
    const size_t backend_count = ggml_backend_reg_count();
    LOGi("Backend initiated; %zu backend(s) registered.", backend_count);
    for (size_t i = 0; i < backend_count; ++i) {
        auto *reg = ggml_backend_reg_get(i);
        LOGi("Registered backend: %s", ggml_backend_reg_name(reg));
    }'''
if old_backend_init not in cpp_text:
    raise SystemExit("Could not locate dynamic Android backend initialization block")
cpp_text = cpp_text.replace(old_backend_init, new_backend_init, 1)

load_marker = '''Java_com_arm_aichat_internal_InferenceEngineImpl_load(JNIEnv *env, jobject, jstring jmodel_path) {
    llama_model_params model_params = llama_model_default_params();'''
if load_marker not in cpp_text:
    raise SystemExit("Could not locate native load() implementation")
cpp_text = cpp_text.replace(
    load_marker,
    load_marker + '''
    g_last_native_error.clear();
    if (ggml_backend_reg_count() == 0) {
        g_last_native_error = "AndroidLLM started without a registered llama.cpp backend";
        return 2;
    }''',
    1,
)
old_load_failure = '''    if (!model) {
        return 1;
    }'''
new_load_failure = '''    if (!model) {
        if (g_last_native_error.empty()) {
            g_last_native_error = "llama_model_load_from_file() returned null without an error message";
        }
        return 1;
    }'''
if old_load_failure not in cpp_text:
    raise SystemExit("Could not locate native model load failure branch")
cpp_text = cpp_text.replace(old_load_failure, new_load_failure, 1)

last_error_jni = '''
extern "C"
JNIEXPORT jstring JNICALL
Java_com_arm_aichat_internal_InferenceEngineImpl_lastNativeError(JNIEnv *env, jobject /*unused*/) {
    return env->NewStringUTF(g_last_native_error.c_str());
}

'''
insert_before = "static llama_context *init_context"
if insert_before not in cpp_text:
    raise SystemExit("Could not locate native context helper")
cpp_text = cpp_text.replace(insert_before, last_error_jni + insert_before, 1)

old_prepare = '''Java_com_arm_aichat_internal_InferenceEngineImpl_prepare(JNIEnv * /*env*/, jobject /*unused*/) {
    auto *context = init_context(g_model);'''
new_prepare = '''Java_com_arm_aichat_internal_InferenceEngineImpl_prepare(JNIEnv * /*env*/, jobject /*unused*/, jint context_size) {
    g_context_size = std::max(512, (int) context_size);
    auto *context = init_context(g_model, g_context_size);'''
if old_prepare not in cpp_text:
    raise SystemExit("Could not locate native prepare() implementation")
cpp_text = cpp_text.replace(old_prepare, new_prepare, 1)
cpp_text = cpp_text.replace("DEFAULT_CONTEXT_SIZE - OVERFLOW_HEADROOM", "g_context_size - OVERFLOW_HEADROOM")

old_chat_format = '''    auto formatted = common_chat_format_single(
            g_chat_templates.get(), chat_msgs, new_msg, role == ROLE_USER, /* use_jinja */ false);'''
new_chat_format = '''    const bool use_jinja = common_chat_templates_support_enable_thinking(g_chat_templates.get());
    auto formatted = common_chat_format_single(
            g_chat_templates.get(), chat_msgs, new_msg, role == ROLE_USER, use_jinja, enable_thinking);'''
if old_chat_format not in cpp_text:
    raise SystemExit("Could not locate Android single-message chat formatting")
cpp_text = cpp_text.replace(
    "static std::string chat_add_and_format(const std::string &role, const std::string &content) {",
    "static std::string chat_add_and_format(const std::string &role, const std::string &content, const bool enable_thinking = true) {",
    1,
)
cpp_text = cpp_text.replace(old_chat_format, new_chat_format, 1)

old_user_sig = '''        jobject /*unused*/,
        jstring juser_prompt,
        jint n_predict
) {'''
new_user_sig = '''        jobject /*unused*/,
        jstring juser_prompt,
        jint n_predict,
        jboolean jenable_thinking
) {'''
if old_user_sig not in cpp_text:
    raise SystemExit("Could not locate native processUserPrompt signature")
cpp_text = cpp_text.replace(old_user_sig, new_user_sig, 1)
cpp_text = cpp_text.replace(
    "formatted_user_prompt = chat_add_and_format(ROLE_USER, user_prompt);",
    "formatted_user_prompt = chat_add_and_format(ROLE_USER, user_prompt, jenable_thinking == JNI_TRUE);",
    1,
)

finish_stopped_jni = '''
extern "C"
JNIEXPORT void JNICALL
Java_com_arm_aichat_internal_InferenceEngineImpl_finishStoppedGeneration(JNIEnv * /*env*/, jobject /*unused*/) {
    if (!assistant_ss.str().empty()) {
        chat_add_and_format(ROLE_ASSISTANT, assistant_ss.str());
    }
}

'''
gen_marker = "extern \"C\"\nJNIEXPORT jstring JNICALL\nJava_com_arm_aichat_internal_InferenceEngineImpl_generateNextToken"
if gen_marker not in cpp_text:
    raise SystemExit("Could not locate generateNextToken JNI")
cpp_text = cpp_text.replace(gen_marker, finish_stopped_jni + gen_marker, 1)
cpp.write_text(cpp_text)

# Match the released Android toolchain, but use a monolithic CPU build instead of
# runtime-loaded backend modules. armv8.2 + dotprod + fp16 is supported by the
# target ARM64 devices and is substantially better than baseline-only ARMv8.
cmake_text = cmake.read_text()
cmake_text = cmake_text.replace("set(GGML_CPU_KLEIDIAI ON)", "set(GGML_CPU_KLEIDIAI OFF)")
cmake_text = cmake_text.replace("set(GGML_OPENMP ON)", "set(GGML_OPENMP OFF)")
cmake.write_text(cmake_text)

gradle_text = gradle.read_text()
gradle_text = gradle_text.replace(
    'abiFilters += listOf("arm64-v8a", "x86_64")',
    'abiFilters += listOf("arm64-v8a")',
)
gradle_text = gradle_text.replace(
    'ndkVersion = "29.0.13113456"',
    'ndkVersion = "29.0.14206865"',
)
gradle_text = gradle_text.replace(
    'arguments += "-DBUILD_SHARED_LIBS=ON"',
    'arguments += "-DBUILD_SHARED_LIBS=OFF"',
)
gradle_text = gradle_text.replace(
    'arguments += "-DGGML_BACKEND_DL=ON"',
    'arguments += "-DGGML_BACKEND_DL=OFF"',
)
gradle_text = gradle_text.replace(
    'arguments += "-DGGML_CPU_ALL_VARIANTS=ON"',
    'arguments += "-DGGML_CPU_ALL_VARIANTS=OFF"\n                arguments += "-DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16"',
)
gradle.write_text(gradle_text)

print("llama.cpp Android binding patched: static CPU backend, context, diagnostics, stop, thinking toggle")

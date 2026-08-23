#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
if not llama.exists():
    raise SystemExit("vendor/llama.cpp is missing; clone the pinned llama.cpp release first")

interface = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/InferenceEngine.kt"
impl = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/internal/InferenceEngineImpl.kt"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
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
replace_once(
    impl,
    "private external fun prepare(): Int",
    "private external fun prepare(contextLength: Int): Int\n\n    @FastNative\n    private external fun lastNativeError(): String",
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

# Native loader diagnostics and context size.
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
load_marker = '''Java_com_arm_aichat_internal_InferenceEngineImpl_load(JNIEnv *env, jobject, jstring jmodel_path) {
    llama_model_params model_params = llama_model_default_params();'''
if load_marker not in cpp_text:
    raise SystemExit("Could not locate native load() implementation")
cpp_text = cpp_text.replace(
    load_marker,
    load_marker + '''
    g_last_native_error.clear();''',
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
cpp.write_text(cpp_text)

# Match the released Android llama.cpp build more closely. In particular, the
# release build disables OpenMP and does not enable KleidiAI explicitly.
cmake_text = cmake.read_text()
cmake_text = cmake_text.replace("set(GGML_CPU_KLEIDIAI ON)", "set(GGML_CPU_KLEIDIAI OFF)")
cmake_text = cmake_text.replace("set(GGML_OPENMP ON)", "set(GGML_OPENMP OFF)")
cmake.write_text(cmake_text)

# ARM64 only, and use the NDK revision used by the b10516 Android release build.
gradle_text = gradle.read_text()
gradle_text = gradle_text.replace(
    'abiFilters += listOf("arm64-v8a", "x86_64")',
    'abiFilters += listOf("arm64-v8a")',
)
gradle_text = gradle_text.replace(
    'ndkVersion = "29.0.13113456"',
    'ndkVersion = "29.0.14206865"',
)
gradle.write_text(gradle_text)

print("llama.cpp Android binding patched: context length, native diagnostics, release-aligned ARM64 CPU build")

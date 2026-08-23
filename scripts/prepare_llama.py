#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
if not llama.exists():
    raise SystemExit("vendor/llama.cpp is missing; clone the pinned llama.cpp release first")

interface = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/InferenceEngine.kt"
impl = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/internal/InferenceEngineImpl.kt"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
gradle = llama / "examples/llama.android/lib/build.gradle.kts"


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old!r}")
    text = text.replace(old, new, 1)
    path.write_text(text)


replace_once(
    interface,
    "suspend fun loadModel(pathToModel: String)",
    "suspend fun loadModel(pathToModel: String, contextLength: Int)",
)

replace_once(
    impl,
    "private external fun prepare(): Int",
    "private external fun prepare(contextLength: Int): Int",
)
replace_once(
    impl,
    "override suspend fun loadModel(pathToModel: String) =",
    "override suspend fun loadModel(pathToModel: String, contextLength: Int) =",
)
replace_once(
    impl,
    "prepare().let {",
    "prepare(contextLength).let {",
)

cpp_text = cpp.read_text()
if "static int                              g_context_size" not in cpp_text:
    marker = "static common_sampler                   * g_sampler;"
    if marker not in cpp_text:
        raise SystemExit("Could not locate llama.cpp Android globals")
    cpp_text = cpp_text.replace(
        marker,
        marker + "\nstatic int                                g_context_size = DEFAULT_CONTEXT_SIZE;",
        1,
    )

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

# This app currently targets modern arm64 Android phones only. Keeping the x86_64
# variant roughly doubles native build work and APK size for no benefit here.
gradle_text = gradle.read_text()
gradle_text = gradle_text.replace(
    'abiFilters += listOf("arm64-v8a", "x86_64")',
    'abiFilters += listOf("arm64-v8a")',
)
gradle.write_text(gradle_text)

print("llama.cpp Android binding patched for configurable context length and arm64-only CPU inference")

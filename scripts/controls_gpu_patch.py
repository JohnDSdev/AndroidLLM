#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
interface = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/InferenceEngine.kt"
impl = llama / "examples/llama.android/lib/src/main/java/com/arm/aichat/internal/InferenceEngineImpl.kt"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
gradle = llama / "examples/llama.android/lib/build.gradle.kts"
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"

for path in (interface, impl, cpp, gradle, main):
    if not path.exists():
        raise SystemExit(f"missing file: {path}")


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"expected text not found in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1))


def replace_function(text: str, start_marker: str, next_marker: str, replacement: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"function start not found: {start_marker}")
    end = text.find(next_marker, start)
    if end < 0:
        raise SystemExit(f"function end not found after {start_marker}: {next_marker}")
    return text[:start] + replacement.rstrip() + "\n\n" + text[end:]


# ---------------------------------------------------------------------------
# Kotlin/JNI API: expose runtime controls and whether experimental GPU PP
# actually initialized. Generation remains CPU-only by design.
# ---------------------------------------------------------------------------
replace_once(
    interface,
    "suspend fun loadModel(pathToModel: String, contextLength: Int)",
    """suspend fun loadModel(
        pathToModel: String,
        contextLength: Int,
        generationThreads: Int,
        promptThreads: Int,
        batchSize: Int,
        temperature: Float,
        topK: Int,
        topP: Float,
        minP: Float,
        gpuPromptProcessing: Boolean,
    )""",
)
replace_once(
    interface,
    "    fun stopGeneration()",
    "    fun stopGeneration()\n\n    /** True only when the experimental Vulkan prompt-processing context initialized. */\n    fun isGpuPromptProcessingActive(): Boolean",
)

replace_once(
    impl,
    "private external fun load(modelPath: String): Int",
    "private external fun load(modelPath: String, gpuPromptProcessing: Boolean): Int",
)
replace_once(
    impl,
    "private external fun prepare(contextLength: Int): Int",
    """private external fun prepare(
        contextLength: Int,
        generationThreads: Int,
        promptThreads: Int,
        batchSize: Int,
        temperature: Float,
        topK: Int,
        topP: Float,
        minP: Float,
    ): Int""",
)
replace_once(
    impl,
    "    private external fun lastNativeError(): String",
    "    private external fun lastNativeError(): String\n\n    @FastNative\n    private external fun gpuPromptProcessingActiveNative(): Boolean",
)
replace_once(
    impl,
    "override suspend fun loadModel(pathToModel: String, contextLength: Int) =",
    """override suspend fun loadModel(
        pathToModel: String,
        contextLength: Int,
        generationThreads: Int,
        promptThreads: Int,
        batchSize: Int,
        temperature: Float,
        topK: Int,
        topP: Float,
        minP: Float,
        gpuPromptProcessing: Boolean,
    ) =""",
)
replace_once(impl, "load(pathToModel).let {", "load(pathToModel, gpuPromptProcessing).let {")
replace_once(
    impl,
    "prepare(contextLength).let {",
    """prepare(
                    contextLength,
                    generationThreads,
                    promptThreads,
                    batchSize,
                    temperature,
                    topK,
                    topP,
                    minP,
                ).let {""",
)
replace_once(
    impl,
    "    /**\n     * Benchmark the model",
    "    override fun isGpuPromptProcessingActive(): Boolean = gpuPromptProcessingActiveNative()\n\n    /**\n     * Benchmark the model",
)

# ---------------------------------------------------------------------------
# Native runtime. CPU model/context is authoritative. When GPU PP is enabled,
# a second Vulkan-offloaded model/context processes prompt batches. We copy the
# sequence/KV state between contexts and always decode the final prompt token on
# CPU so the logits used for sampling, and every generated token thereafter,
# are CPU-produced. This deliberately does NOT use n_gpu_layers on the TG model.
# ---------------------------------------------------------------------------
cpp_text = cpp.read_text()

old_globals = """static int                                g_context_size = DEFAULT_CONTEXT_SIZE;
static std::string                        g_last_native_error;"""
new_globals = """static int                                g_context_size = DEFAULT_CONTEXT_SIZE;
static std::string                        g_last_native_error;
static int                                g_generation_threads = 4;
static int                                g_prompt_threads = 6;
static int                                g_batch_size = 512;
static float                              g_temperature = 0.8f;
static int                                g_top_k = 40;
static float                              g_top_p = 0.95f;
static float                              g_min_p = 0.05f;
static bool                               g_gpu_pp_requested = false;
static bool                               g_gpu_pp_active = false;
static llama_model                      * g_pp_model = nullptr;
static llama_context                    * g_pp_context = nullptr;"""
if old_globals not in cpp_text:
    raise SystemExit("runtime globals marker not found")
cpp_text = cpp_text.replace(old_globals, new_globals, 1)

load_start = "extern \"C\"\nJNIEXPORT jint JNICALL\nJava_com_arm_aichat_internal_InferenceEngineImpl_load"
load_end = "extern \"C\"\nJNIEXPORT jstring JNICALL\nJava_com_arm_aichat_internal_InferenceEngineImpl_lastNativeError"
new_load = r'''extern "C"
JNIEXPORT jint JNICALL
Java_com_arm_aichat_internal_InferenceEngineImpl_load(
        JNIEnv *env,
        jobject,
        jstring jmodel_path,
        jboolean jgpu_prompt_processing
) {
    g_last_native_error.clear();
    if (ggml_backend_reg_count() == 0) {
        g_last_native_error = "AndroidLLM started without a registered llama.cpp backend";
        return 2;
    }

    g_gpu_pp_requested = jgpu_prompt_processing == JNI_TRUE;
    g_gpu_pp_active = false;

    const auto *model_path = env->GetStringUTFChars(jmodel_path, 0);
    LOGi("%s: Loading CPU generation model from %s", __func__, model_path);

    llama_model_params cpu_params = llama_model_default_params();
    cpu_params.n_gpu_layers = 0;
    auto *model = llama_model_load_from_file(model_path, cpu_params);
    if (!model) {
        env->ReleaseStringUTFChars(jmodel_path, model_path);
        if (g_last_native_error.empty()) {
            g_last_native_error = "llama_model_load_from_file() returned null without an error message";
        }
        return 1;
    }
    g_model = model;

    if (g_gpu_pp_requested) {
        bool gpu_device_found = false;
        for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
            auto *dev = ggml_backend_dev_get(i);
            const auto type = ggml_backend_dev_type(dev);
            if (type == GGML_BACKEND_DEVICE_TYPE_GPU || type == GGML_BACKEND_DEVICE_TYPE_IGPU) {
                gpu_device_found = true;
                LOGi("Experimental GPU PP candidate: %s (%s)",
                     ggml_backend_dev_name(dev), ggml_backend_dev_description(dev));
                break;
            }
        }

        if (gpu_device_found) {
            g_last_native_error.clear();
            llama_model_params pp_params = llama_model_default_params();
            pp_params.n_gpu_layers = -1;
            g_pp_model = llama_model_load_from_file(model_path, pp_params);
            if (g_pp_model) {
                g_gpu_pp_active = true;
                LOGi("Experimental Vulkan prompt-processing model loaded; text generation remains CPU-only");
            } else {
                LOGw("Experimental GPU PP model could not be loaded; falling back to CPU prompt processing");
                g_last_native_error.clear();
            }
        } else {
            LOGw("Experimental GPU PP requested but no GPU backend device is registered; using CPU");
        }
    }

    env->ReleaseStringUTFChars(jmodel_path, model_path);
    return 0;
}
'''
cpp_text = replace_function(cpp_text, load_start, load_end, new_load)

# Put the native status getter immediately after lastNativeError().
status_insert = r'''
extern "C"
JNIEXPORT jboolean JNICALL
Java_com_arm_aichat_internal_InferenceEngineImpl_gpuPromptProcessingActiveNative(JNIEnv *, jobject) {
    return (g_gpu_pp_active && g_pp_model != nullptr && g_pp_context != nullptr) ? JNI_TRUE : JNI_FALSE;
}

'''
init_context_marker = "static llama_context *init_context"
pos = cpp_text.find(init_context_marker)
if pos < 0:
    raise SystemExit("init_context marker missing")
cpp_text = cpp_text[:pos] + status_insert + cpp_text[pos:]

ctx_start = "static llama_context *init_context"
ctx_end = "static common_sampler *new_sampler"
new_context = r'''static llama_context *init_context(
        llama_model *model,
        const int n_ctx,
        const int generation_threads,
        const int prompt_threads,
        const int batch_size) {
    if (!model) {
        LOGe("%s: model cannot be null", __func__);
        return nullptr;
    }

    const int n_threads = std::max(1, generation_threads);
    const int n_threads_batch = std::max(1, prompt_threads);
    LOGi("%s: threads tg=%d pp=%d batch=%d", __func__, n_threads, n_threads_batch, batch_size);

    llama_context_params ctx_params = llama_context_default_params();
    const int trained_context_size = llama_model_n_ctx_train(model);
    if (n_ctx > trained_context_size) {
        LOGw("%s: Model trained for %d context; requested %d", __func__, trained_context_size, n_ctx);
    }
    ctx_params.n_ctx = n_ctx;
    ctx_params.n_batch = batch_size;
    ctx_params.n_ubatch = batch_size;
    ctx_params.n_threads = n_threads;
    ctx_params.n_threads_batch = n_threads_batch;

    auto *context = llama_init_from_model(model, ctx_params);
    if (context == nullptr) {
        LOGe("%s: llama_init_from_model() returned null", __func__);
    }
    return context;
}

'''
cpp_text = replace_function(cpp_text, ctx_start, ctx_end, new_context)

sampler_start = "static common_sampler *new_sampler"
sampler_end = "extern \"C\"\nJNIEXPORT jint JNICALL\nJava_com_arm_aichat_internal_InferenceEngineImpl_prepare"
new_sampler = r'''static common_sampler *new_sampler() {
    common_params_sampling sparams;
    sparams.temp = g_temperature;
    sparams.top_k = g_top_k;
    sparams.top_p = g_top_p;
    sparams.min_p = g_min_p;
    return common_sampler_init(g_model, sparams);
}

'''
cpp_text = replace_function(cpp_text, sampler_start, sampler_end, new_sampler)

prepare_start = "extern \"C\"\nJNIEXPORT jint JNICALL\nJava_com_arm_aichat_internal_InferenceEngineImpl_prepare"
prepare_end = "static std::string get_backend()"
new_prepare = r'''extern "C"
JNIEXPORT jint JNICALL
Java_com_arm_aichat_internal_InferenceEngineImpl_prepare(
        JNIEnv *,
        jobject,
        jint context_size,
        jint generation_threads,
        jint prompt_threads,
        jint batch_size,
        jfloat temperature,
        jint top_k,
        jfloat top_p,
        jfloat min_p
) {
    g_context_size = std::max(512, (int) context_size);
    g_generation_threads = std::max(1, std::min(32, (int) generation_threads));
    g_prompt_threads = std::max(1, std::min(32, (int) prompt_threads));
    g_batch_size = std::max(32, std::min(2048, (int) batch_size));
    g_temperature = std::max(0.0f, std::min(2.0f, (float) temperature));
    g_top_k = std::max(0, std::min(200, (int) top_k));
    g_top_p = std::max(0.0f, std::min(1.0f, (float) top_p));
    g_min_p = std::max(0.0f, std::min(1.0f, (float) min_p));

    g_context = init_context(
            g_model,
            g_context_size,
            g_generation_threads,
            g_prompt_threads,
            g_batch_size);
    if (!g_context) {
        return 1;
    }

    if (g_gpu_pp_active && g_pp_model) {
        g_pp_context = init_context(
                g_pp_model,
                g_context_size,
                g_prompt_threads,
                g_prompt_threads,
                g_batch_size);
        if (!g_pp_context) {
            LOGw("Experimental GPU PP context initialization failed; using CPU prompt processing");
            llama_model_free(g_pp_model);
            g_pp_model = nullptr;
            g_gpu_pp_active = false;
        }
    }

    g_batch = llama_batch_init(g_batch_size, 0, 1);
    g_chat_templates = common_chat_templates_init(g_model, "");
    g_sampler = new_sampler();
    return g_sampler ? 0 : 2;
}

'''
cpp_text = replace_function(cpp_text, prepare_start, prepare_end, new_prepare)

# Bench uses the helper too. It is not the app hot path, but it must compile with
# the new signature and should remain CPU-only.
cpp_text = cpp_text.replace(
    "auto *context = init_context(g_model, pp);",
    "auto *context = init_context(g_model, pp, g_generation_threads, g_prompt_threads, g_batch_size);",
    1,
)

# Reset both contexts, and add host-mediated sequence-state transfer helpers.
old_reset = '''    if (clear_kv_cache)
        llama_memory_clear(llama_get_memory(g_context), false);
}'''
new_reset = '''    if (clear_kv_cache) {
        if (g_context) llama_memory_clear(llama_get_memory(g_context), false);
        if (g_pp_context) llama_memory_clear(llama_get_memory(g_pp_context), false);
    }
}

static bool copy_sequence_state(llama_context *src, llama_context *dst) {
    if (!src || !dst) return false;
    const size_t size = llama_state_seq_get_size(src, 0);
    if (size == 0) return false;
    std::vector<uint8_t> state(size);
    const size_t copied = llama_state_seq_get_data(src, state.data(), state.size(), 0);
    if (copied == 0) return false;
    llama_memory_clear(llama_get_memory(dst), false);
    const size_t restored = llama_state_seq_set_data(dst, state.data(), copied, 0);
    return restored > 0;
}

static bool sync_cpu_to_gpu_pp() {
    if (!g_gpu_pp_active || !g_pp_context) return false;
    return copy_sequence_state(g_context, g_pp_context);
}

static bool sync_gpu_pp_to_cpu() {
    if (!g_gpu_pp_active || !g_pp_context) return false;
    return copy_sequence_state(g_pp_context, g_context);
}'''
if old_reset not in cpp_text:
    raise SystemExit("reset_long_term_states block not found")
cpp_text = cpp_text.replace(old_reset, new_reset, 1)

# Replace the decoder with a runtime batch-size implementation. Context shifting
# is deliberately not attempted on the secondary GPU context.
decode_start = "static int decode_tokens_in_batches("
decode_end = "extern \"C\"\nJNIEXPORT jint JNICALL\nJava_com_arm_aichat_internal_InferenceEngineImpl_processSystemPrompt"
new_decode = r'''static int decode_tokens_in_batches(
        llama_context *context,
        llama_batch &batch,
        const llama_tokens &tokens,
        const llama_pos start_pos,
        const bool compute_last_logit = false) {
    if (tokens.empty()) return 0;
    LOGd("%s: Decode %d tokens starting at position %d", __func__, (int) tokens.size(), start_pos);
    for (int i = 0; i < (int) tokens.size(); i += g_batch_size) {
        const int cur_batch_size = std::min((int) tokens.size() - i, g_batch_size);
        if (start_pos + i + cur_batch_size >= g_context_size - OVERFLOW_HEADROOM) {
            LOGe("%s: prompt batch would exceed configured context", __func__);
            return 2;
        }

        common_batch_clear(batch);
        for (int j = 0; j < cur_batch_size; ++j) {
            const llama_token token_id = tokens[i + j];
            const llama_pos position = start_pos + i + j;
            const bool want_logit = compute_last_logit && (i + j == (int) tokens.size() - 1);
            common_batch_add(batch, token_id, position, {0}, want_logit);
        }

        const int decode_result = llama_decode(context, batch);
        if (decode_result) {
            LOGe("%s: llama_decode failed w/ %d", __func__, decode_result);
            return 1;
        }
    }
    return 0;
}

'''
cpp_text = replace_function(cpp_text, decode_start, decode_end, new_decode)

# System prompt may be fully processed on GPU because generation does not sample
# from its logits. Copy the resulting sequence state into the CPU context.
system_old = '''    // Decode system tokens in batches
    if (decode_tokens_in_batches(g_context, g_batch, system_tokens, current_position)) {
        LOGe("%s: llama_decode() failed!", __func__);
        return 2;
    }

    // Update position'''
system_new = '''    // Decode system tokens. Experimental GPU PP can own this whole batch because
    // no token is sampled from the system-prompt logits.
    if (g_gpu_pp_active && g_pp_context) {
        if (decode_tokens_in_batches(g_pp_context, g_batch, system_tokens, current_position)) {
            LOGw("GPU system-prompt decode failed; disabling experimental GPU PP");
            g_gpu_pp_active = false;
            llama_memory_clear(llama_get_memory(g_context), false);
            if (decode_tokens_in_batches(g_context, g_batch, system_tokens, current_position)) return 2;
        } else if (!sync_gpu_pp_to_cpu()) {
            LOGw("GPU->CPU prompt-state transfer failed; disabling experimental GPU PP");
            g_gpu_pp_active = false;
            llama_memory_clear(llama_get_memory(g_context), false);
            if (decode_tokens_in_batches(g_context, g_batch, system_tokens, current_position)) return 2;
        }
    } else if (decode_tokens_in_batches(g_context, g_batch, system_tokens, current_position)) {
        LOGe("%s: llama_decode() failed!", __func__);
        return 2;
    }

    // Update position'''
if system_old not in cpp_text:
    raise SystemExit("system decode block not found")
cpp_text = cpp_text.replace(system_old, system_new, 1)

# User prompt: GPU does every token except the final one. The state is transferred
# to CPU, then CPU decodes that final prompt token to produce authoritative logits.
user_old = '''    // Decode user tokens in batches
    if (decode_tokens_in_batches(g_context, g_batch, user_tokens, current_position, true)) {
        LOGe("%s: llama_decode() failed!", __func__);
        return 2;
    }

    // Update position
    current_position += user_prompt_size;'''
user_new = '''    // Decode user prompt. GPU is used only for the batched prefix; the final prompt
    // token is always decoded by CPU so sampling and every generated token stay CPU-only.
    bool prompt_ok = false;
    if (g_gpu_pp_active && g_pp_context && user_tokens.size() > 1 && sync_cpu_to_gpu_pp()) {
        llama_tokens gpu_prefix(user_tokens.begin(), user_tokens.end() - 1);
        llama_tokens cpu_tail(1, user_tokens.back());
        if (decode_tokens_in_batches(g_pp_context, g_batch, gpu_prefix, current_position) == 0 &&
            sync_gpu_pp_to_cpu() &&
            decode_tokens_in_batches(
                g_context,
                g_batch,
                cpu_tail,
                current_position + (llama_pos) gpu_prefix.size(),
                true) == 0) {
            prompt_ok = true;
        } else {
            LOGw("Experimental GPU PP failed during user prompt; retrying this prompt on CPU");
            g_gpu_pp_active = false;
        }
    }

    if (!prompt_ok) {
        // Restore the CPU context to the pre-prompt state if the experimental path
        // failed after mutating it. The safest fallback is to reload conversation
        // state on the next app turn rather than return silently corrupted logits.
        if (decode_tokens_in_batches(g_context, g_batch, user_tokens, current_position, true)) {
            LOGe("%s: llama_decode() failed!", __func__);
            return 2;
        }
    }

    // Update position
    current_position += (int) user_tokens.size();'''
if user_old not in cpp_text:
    raise SystemExit("user decode block not found")
cpp_text = cpp_text.replace(user_old, user_new, 1)

# Runtime batch size also governs prompt truncation limits.
cpp_text = cpp_text.replace(
    "const int max_batch_size = g_context_size - OVERFLOW_HEADROOM;",
    "const int max_batch_size = g_context_size - OVERFLOW_HEADROOM;",
)

# Free both contexts/models. The secondary model is never used by generation.
unload_start = "extern \"C\"\nJNIEXPORT void JNICALL\nJava_com_arm_aichat_internal_InferenceEngineImpl_unload"
unload_end = "extern \"C\"\nJNIEXPORT void JNICALL\nJava_com_arm_aichat_internal_InferenceEngineImpl_shutdown"
new_unload = r'''extern "C"
JNIEXPORT void JNICALL
Java_com_arm_aichat_internal_InferenceEngineImpl_unload(JNIEnv *, jobject) {
    reset_long_term_states();
    reset_short_term_states();

    if (g_sampler) common_sampler_free(g_sampler);
    g_sampler = nullptr;
    g_chat_templates.reset();
    llama_batch_free(g_batch);

    if (g_pp_context) llama_free(g_pp_context);
    g_pp_context = nullptr;
    if (g_context) llama_free(g_context);
    g_context = nullptr;

    if (g_pp_model) llama_model_free(g_pp_model);
    g_pp_model = nullptr;
    if (g_model) llama_model_free(g_model);
    g_model = nullptr;

    g_gpu_pp_active = false;
    g_gpu_pp_requested = false;
}

'''
cpp_text = replace_function(cpp_text, unload_start, unload_end, new_unload)

cpp.write_text(cpp_text)

# ---------------------------------------------------------------------------
# Compile Vulkan statically into libai-chat. CPU remains linked in and is always
# the text-generation backend. Vulkan is used only by the secondary PP model.
# ---------------------------------------------------------------------------
gradle_text = gradle.read_text()
arch_line = '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.6-a+dotprod+fp16+i8mm"\n'
if arch_line not in gradle_text:
    raise SystemExit("optimized ARM architecture flag not found")
gradle_text = gradle_text.replace(
    arch_line,
    arch_line + '                arguments += "-DGGML_VULKAN=ON"\n',
    1,
)
gradle.write_text(gradle_text)

# ---------------------------------------------------------------------------
# MainActivity: no stock/default Android menus. Everything is rendered as a
# custom in-app bottom sheet, and settings use Material sliders.
# ---------------------------------------------------------------------------
main_text = main.read_text()

main_text = main_text.replace("import android.graphics.Typeface\n", "import android.app.Dialog\nimport android.graphics.Color\nimport android.graphics.Typeface\nimport android.graphics.drawable.ColorDrawable\n", 1)
main_text = main_text.replace("import android.view.Gravity\n", "import android.view.Gravity\nimport android.view.Window\nimport android.view.WindowManager\n", 1)
main_text = main_text.replace("import com.google.android.material.dialog.MaterialAlertDialogBuilder\n", "", 1)
if "import com.google.android.material.slider.Slider\n" not in main_text:
    main_text = main_text.replace(
        "import com.google.android.material.card.MaterialCardView\n",
        "import com.google.android.material.card.MaterialCardView\nimport com.google.android.material.slider.Slider\n",
        1,
    )

main_text = main_text.replace(
    "private var currentModelDialog: androidx.appcompat.app.AlertDialog? = null",
    "private var currentModelDialog: Dialog? = null",
    1,
)
main_text = main_text.replace(
    "    @Volatile private var loadedContextLength: Int? = null\n",
    "    @Volatile private var loadedContextLength: Int? = null\n    @Volatile private var loadedRuntimeKey: String? = null\n    @Volatile private var gpuPpActive = false\n",
    1,
)

old_header = '''        val baseSubtitle = when {
            loadedModelName == chat.modelFile && loadedChatId == chat.id && loadedModelName != null ->
                "On-device • model loaded"
            chat.modelFile != null -> "On-device • model selected"
            else -> "On-device • CPU only"
        }
        val speed = lastTps?.takeIf { it.isFinite() && it > 0.0 }'''
new_header = '''        val loadedHere = loadedModelName == chat.modelFile && loadedChatId == chat.id && loadedModelName != null
        val computeLabel = when {
            loadedHere && gpuPpActive -> "Vulkan PP • CPU TG"
            loadedHere && chat.gpuPromptProcessing -> "GPU PP unavailable • CPU"
            loadedHere -> "CPU"
            chat.modelFile != null -> "model selected"
            else -> "CPU"
        }
        val baseSubtitle = "On-device • $computeLabel"
        val speed = lastTps?.takeIf { it.isFinite() && it > 0.0 }'''
if old_header not in main_text:
    raise SystemExit("header status block not found")
main_text = main_text.replace(old_header, new_header, 1)

helpers = r'''    private data class SheetAction(
        val label: String,
        val destructive: Boolean = false,
        val onClick: (Dialog) -> Unit,
    )

    private fun showAppSheet(
        title: String,
        content: View? = null,
        message: String? = null,
        actions: List<SheetAction> = listOf(SheetAction("Close") { it.dismiss() }),
    ): Dialog {
        val dialog = Dialog(this)
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)

        val card = MaterialCardView(this).apply {
            radius = dp(26).toFloat()
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = color(R.color.divider)
            setCardBackgroundColor(color(R.color.surface))
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(10), dp(18), dp(14))
        }
        root.addView(View(this).apply {
            setBackgroundColor(color(R.color.divider))
        }, LinearLayout.LayoutParams(dp(42), dp(4)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            bottomMargin = dp(13)
        })
        root.addView(TextView(this).apply {
            text = title
            textSize = 20f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(color(R.color.text_primary))
            setPadding(dp(2), 0, dp(2), dp(12))
        })
        if (!message.isNullOrBlank()) {
            root.addView(TextView(this).apply {
                text = message
                textSize = 14f
                setTextColor(color(R.color.text_secondary))
                setPadding(dp(2), 0, dp(2), dp(14))
            })
        }
        if (content != null) {
            root.addView(content, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ))
        }

        if (actions.isNotEmpty()) {
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.END
                setPadding(0, dp(14), 0, 0)
            }
            actions.forEach { action ->
                row.addView(MaterialButton(
                    this,
                    null,
                    com.google.android.material.R.attr.materialButtonOutlinedStyle,
                ).apply {
                    text = action.label
                    isAllCaps = false
                    cornerRadius = dp(15)
                    if (action.destructive) setTextColor(color(R.color.danger))
                    setOnClickListener { action.onClick(dialog) }
                }, LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                ).apply { marginStart = dp(8) })
            }
            root.addView(row)
        }

        card.addView(root)
        dialog.setContentView(card)
        dialog.setCanceledOnTouchOutside(true)
        dialog.show()
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.WRAP_CONTENT)
            setGravity(Gravity.BOTTOM)
            addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            setDimAmount(0.58f)
        }
        return dialog
    }

    private fun sheetRow(
        title: String,
        subtitle: String? = null,
        destructive: Boolean = false,
        onClick: () -> Unit,
    ): View {
        val card = MaterialCardView(this).apply {
            radius = dp(16).toFloat()
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = color(R.color.divider)
            setCardBackgroundColor(color(R.color.surface_alt))
            isClickable = true
            isFocusable = true
            setOnClickListener { onClick() }
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
        }
        box.addView(TextView(this).apply {
            text = title
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(color(if (destructive) R.color.danger else R.color.text_primary))
        })
        if (!subtitle.isNullOrBlank()) {
            box.addView(TextView(this).apply {
                text = subtitle
                textSize = 12f
                setTextColor(color(R.color.text_secondary))
                setPadding(0, dp(3), 0, 0)
            })
        }
        card.addView(box)
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(card, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(8) })
        }
    }

    private fun makeSlider(
        label: String,
        valueFrom: Float,
        valueTo: Float,
        step: Float,
        initial: Float,
        format: (Float) -> String,
    ): Pair<LinearLayout, Slider> {
        val valueView = TextView(this).apply {
            text = format(initial)
            textSize = 13f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(color(R.color.text_secondary))
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(TextView(this@MainActivity).apply {
                text = label
                textSize = 14f
                setTextColor(color(R.color.text_primary))
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(valueView)
        }
        val slider = Slider(this).apply {
            this.valueFrom = valueFrom
            this.valueTo = valueTo
            stepSize = step
            value = initial.coerceIn(valueFrom, valueTo)
            addOnChangeListener { _, newValue, _ -> valueView.text = format(newValue) }
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(7), 0, dp(5))
            addView(header)
            addView(slider)
        } to slider
    }

    private fun sectionLabel(label: String) = TextView(this).apply {
        text = label.uppercase()
        textSize = 11f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(color(R.color.text_secondary))
        setPadding(dp(2), dp(18), dp(2), dp(6))
    }

'''
insert_at = main_text.find("    private fun createNewChat() {")
if insert_at < 0:
    raise SystemExit("createNewChat marker not found")
main_text = main_text[:insert_at] + helpers + main_text[insert_at:]

new_chats = r'''    private fun showChatsDialog() {
        val chats = store.chats.toList()
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        var dialog: Dialog? = null
        chats.forEach { chat ->
            box.addView(sheetRow(
                title = chat.title,
                subtitle = if (chat.id == store.currentChatId) "Current chat" else null,
            ) {
                store.selectChat(chat.id)
                loadedChatId = null
                loadedRuntimeKey = null
                lastTps = null
                dialog?.dismiss()
                renderAll()
            })
        }
        val scroll = ScrollView(this).apply {
            addView(box)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                (resources.displayMetrics.heightPixels * 0.58f).roundToInt(),
            )
        }
        dialog = showAppSheet(
            title = "Chats",
            content = scroll,
            actions = listOf(
                SheetAction("Delete current", destructive = true) {
                    it.dismiss()
                    confirmDeleteCurrentChat()
                },
                SheetAction("Close") { it.dismiss() },
            ),
        )
    }
'''
main_text = replace_function(main_text, "    private fun showChatsDialog() {", "    private fun confirmDeleteCurrentChat() {", new_chats)

new_confirm_chat = r'''    private fun confirmDeleteCurrentChat() {
        val current = store.currentChat()
        showAppSheet(
            title = "Delete this chat?",
            message = current.title,
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Delete", destructive = true) { dialog ->
                    store.deleteChat(current.id)
                    loadedChatId = null
                    loadedRuntimeKey = null
                    lastTps = null
                    dialog.dismiss()
                    renderAll()
                },
            ),
        )
    }
'''
main_text = replace_function(main_text, "    private fun confirmDeleteCurrentChat() {", "    private fun showMenuDialog() {", new_confirm_chat)

new_menu = r'''    private fun showMenuDialog() {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        var dialog: Dialog? = null
        box.addView(sheetRow("Chat settings", "Runtime, sampling, context, thinking, GPU PP") {
            dialog?.dismiss()
            showSettingsDialog()
        })
        box.addView(sheetRow("Export all data", "Chats and downloaded GGUF models") {
            dialog?.dismiss()
            exportLauncher.launch("AndroidLLM-export.zip")
        })
        box.addView(sheetRow("Unload model", "Free model RAM and GPU resources") {
            dialog?.dismiss()
            unloadModelAsync()
        })
        dialog = showAppSheet("AndroidLLM", content = box)
    }
'''
main_text = replace_function(main_text, "    private fun showMenuDialog() {", "    private fun showSettingsDialog() {", new_menu)

new_settings = r'''    private fun showSettingsDialog() {
        val chat = store.currentChat()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(2), 0, dp(2), dp(4))
        }

        val systemInput = TextInputEditText(this).apply {
            setText(chat.systemPrompt)
            minLines = 3
            maxLines = 7
            gravity = Gravity.TOP
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        val systemLayout = TextInputLayout(this).apply {
            hint = "System prompt"
            boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            boxStrokeColor = color(R.color.accent)
            addView(systemInput)
        }
        box.addView(systemLayout)

        val contextOptions = intArrayOf(512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072)
        val contextIndex = contextOptions.indexOf(chat.contextLength).takeIf { it >= 0 } ?: 3
        val (contextBlock, contextSlider) = makeSlider(
            "Context length", 0f, (contextOptions.size - 1).toFloat(), 1f, contextIndex.toFloat(),
        ) { contextOptions[it.roundToInt()].let(::formatContext) }

        val maxThreads = Runtime.getRuntime().availableProcessors().coerceIn(2, 16)
        val (genThreadsBlock, genThreadsSlider) = makeSlider(
            "Generation threads", 1f, maxThreads.toFloat(), 1f,
            chat.generationThreads.coerceIn(1, maxThreads).toFloat(),
        ) { it.roundToInt().toString() }
        val (ppThreadsBlock, ppThreadsSlider) = makeSlider(
            "Prompt threads", 1f, maxThreads.toFloat(), 1f,
            chat.promptThreads.coerceIn(1, maxThreads).toFloat(),
        ) { it.roundToInt().toString() }

        val batchOptions = intArrayOf(64, 128, 256, 512, 1024, 2048)
        val batchIndex = batchOptions.indexOf(chat.batchSize).takeIf { it >= 0 } ?: 3
        val (batchBlock, batchSlider) = makeSlider(
            "Prompt batch size", 0f, (batchOptions.size - 1).toFloat(), 1f, batchIndex.toFloat(),
        ) { batchOptions[it.roundToInt()].toString() }

        val (tempBlock, tempSlider) = makeSlider(
            "Temperature", 0f, 2f, 0.05f, chat.temperature,
        ) { java.lang.String.format(java.util.Locale.US, "%.2f", it) }
        val (topKBlock, topKSlider) = makeSlider(
            "Top-k", 0f, 100f, 1f, chat.topK.coerceIn(0, 100).toFloat(),
        ) { it.roundToInt().toString() }
        val (topPBlock, topPSlider) = makeSlider(
            "Top-p", 0.1f, 1f, 0.01f, chat.topP.coerceIn(0.1f, 1f),
        ) { java.lang.String.format(java.util.Locale.US, "%.2f", it) }
        val (minPBlock, minPSlider) = makeSlider(
            "Min-p", 0f, 0.5f, 0.01f, chat.minP.coerceIn(0f, 0.5f),
        ) { java.lang.String.format(java.util.Locale.US, "%.2f", it) }

        val thinkingSwitch = SwitchCompat(this).apply {
            text = "Thinking mode"
            isChecked = chat.thinkingEnabled
            setTextColor(color(R.color.text_primary))
            setPadding(0, dp(8), 0, dp(8))
        }
        val gpuSwitch = SwitchCompat(this).apply {
            text = "Experimental GPU prompt processing"
            isChecked = chat.gpuPromptProcessing
            setTextColor(color(R.color.text_primary))
            setPadding(0, dp(8), 0, dp(4))
        }

        box.addView(sectionLabel("Runtime"))
        box.addView(contextBlock)
        box.addView(genThreadsBlock)
        box.addView(ppThreadsBlock)
        box.addView(batchBlock)
        box.addView(thinkingSwitch)

        box.addView(sectionLabel("Sampling"))
        box.addView(tempBlock)
        box.addView(topKBlock)
        box.addView(topPBlock)
        box.addView(minPBlock)

        box.addView(sectionLabel("Experimental"))
        box.addView(gpuSwitch)
        box.addView(TextView(this).apply {
            text = "Vulkan is used only for batched prompt processing. The final prompt token and all generated tokens stay on CPU. This loads a second model context and can use substantially more RAM/VRAM. If Vulkan cannot initialize, AndroidLLM falls back to CPU."
            textSize = 12f
            setTextColor(color(R.color.text_secondary))
            setPadding(dp(2), 0, dp(2), dp(6))
        })

        val scroll = ScrollView(this).apply {
            addView(box)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                (resources.displayMetrics.heightPixels * 0.70f).roundToInt(),
            )
        }

        showAppSheet(
            title = "Chat settings",
            content = scroll,
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Save") { dialog ->
                    chat.systemPrompt = systemInput.text?.toString().orEmpty().ifBlank { "You are a helpful assistant." }
                    chat.contextLength = contextOptions[contextSlider.value.roundToInt()]
                    chat.generationThreads = genThreadsSlider.value.roundToInt()
                    chat.promptThreads = ppThreadsSlider.value.roundToInt()
                    chat.batchSize = batchOptions[batchSlider.value.roundToInt()]
                    chat.temperature = tempSlider.value
                    chat.topK = topKSlider.value.roundToInt()
                    chat.topP = topPSlider.value
                    chat.minP = minPSlider.value
                    chat.thinkingEnabled = thinkingSwitch.isChecked
                    chat.gpuPromptProcessing = gpuSwitch.isChecked
                    store.save()
                    loadedChatId = null
                    loadedContextLength = null
                    loadedRuntimeKey = null
                    gpuPpActive = false
                    dialog.dismiss()
                    renderAll()
                },
            ),
        )
    }
'''
main_text = replace_function(main_text, "    private fun showSettingsDialog() {", "    private fun showModelsDialog() {", new_settings)

# Models keeps its existing custom rows but replaces the AlertDialog shell.
old_models_tail = '''        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle("Models")
            .setView(scroll)
            .setNegativeButton("Close", null)
            .create()
        currentModelDialog = dialog
        dialog.setOnDismissListener { if (currentModelDialog === dialog) currentModelDialog = null }
        dialog.show()'''
new_models_tail = '''        val dialog = showAppSheet(
            title = "Models",
            content = scroll,
            actions = listOf(SheetAction("Close") { it.dismiss() }),
        )
        currentModelDialog = dialog
        dialog.setOnDismissListener { if (currentModelDialog === dialog) currentModelDialog = null }'''
if old_models_tail not in main_text:
    raise SystemExit("models AlertDialog shell not found")
main_text = main_text.replace(old_models_tail, new_models_tail, 1)

new_download = r'''    private fun showDownloadDialog() {
        val input = TextInputEditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine(false)
            minLines = 2
            maxLines = 4
        }
        val inputLayout = TextInputLayout(this).apply {
            hint = "Direct GGUF URL"
            boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            boxStrokeColor = color(R.color.accent)
            addView(input)
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(TextView(this@MainActivity).apply {
                text = "Paste a direct .gguf file URL. Hugging Face /resolve/ links work."
                textSize = 13f
                setTextColor(color(R.color.text_secondary))
                setPadding(dp(2), 0, dp(2), dp(10))
            })
            addView(inputLayout)
        }
        showAppSheet(
            title = "Download model",
            content = box,
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Download") { dialog ->
                    val url = input.text?.toString()?.trim().orEmpty()
                    if (!url.startsWith("http://") && !url.startsWith("https://")) {
                        inputLayout.error = "Paste an http(s) URL"
                    } else {
                        inputLayout.error = null
                        dialog.dismiss()
                        downloadModel(url)
                    }
                },
            ),
        )
    }
'''
main_text = replace_function(main_text, "    private fun showDownloadDialog() {", "    private fun downloadModel(url: String) {", new_download)

new_confirm_model = r'''    private fun confirmDeleteModel(file: File) {
        showAppSheet(
            title = "Delete model?",
            message = "${file.name}\n${formatBytes(file.length())}",
            actions = listOf(
                SheetAction("Cancel") { it.dismiss() },
                SheetAction("Delete", destructive = true) { dialog ->
                    if (loadedModelName == file.name) {
                        Toast.makeText(this, "Unload this model first.", Toast.LENGTH_SHORT).show()
                        return@SheetAction
                    }
                    if (file.delete()) {
                        store.chats.filter { it.modelFile == file.name }.forEach { it.modelFile = null }
                        store.save()
                        currentModelDialog?.dismiss()
                        dialog.dismiss()
                        renderAll()
                        showModelsDialog()
                    } else {
                        dialog.dismiss()
                        showError("Could not delete model", IllegalStateException("Android could not delete ${file.absolutePath}"))
                    }
                },
            ),
        )
    }
'''
main_text = replace_function(main_text, "    private fun confirmDeleteModel(file: File) {", "    private fun selectAndLoadModel(file: File) {", new_confirm_model)

# Runtime identity + new native load args.
old_loaded_condition = '''            loadedChatId == chat.id &&
            loadedContextLength == chat.contextLength &&
            engine.state.value is InferenceEngine.State.ModelReady'''
new_loaded_condition = '''            loadedChatId == chat.id &&
            loadedContextLength == chat.contextLength &&
            loadedRuntimeKey == runtimeKey(chat) &&
            engine.state.value is InferenceEngine.State.ModelReady'''
if old_loaded_condition not in main_text:
    raise SystemExit("model loaded condition not found")
main_text = main_text.replace(old_loaded_condition, new_loaded_condition, 1)

old_load_call = '''            engine.loadModel(file.absolutePath, chat.contextLength)
            engine.setSystemPrompt(effectiveSystemPrompt(chat))'''
new_load_call = '''            engine.loadModel(
                file.absolutePath,
                chat.contextLength,
                chat.generationThreads,
                chat.promptThreads,
                chat.batchSize,
                chat.temperature,
                chat.topK,
                chat.topP,
                chat.minP,
                chat.gpuPromptProcessing,
            )
            gpuPpActive = engine.isGpuPromptProcessingActive()
            engine.setSystemPrompt(effectiveSystemPrompt(chat))'''
if old_load_call not in main_text:
    raise SystemExit("engine.loadModel call not found")
main_text = main_text.replace(old_load_call, new_load_call, 1)

main_text = main_text.replace(
    '''        loadedContextLength = chat.contextLength
        runOnUiThread { renderHeader() }''',
    '''        loadedContextLength = chat.contextLength
        loadedRuntimeKey = runtimeKey(chat)
        runOnUiThread { renderHeader() }''',
    1,
)
main_text = main_text.replace(
    '''        loadedContextLength = null
    }

    private fun effectiveSystemPrompt''',
    '''        loadedContextLength = null
        loadedRuntimeKey = null
        gpuPpActive = false
    }

    private fun runtimeKey(chat: ChatSession): String = listOf(
        chat.contextLength,
        chat.generationThreads,
        chat.promptThreads,
        chat.batchSize,
        chat.temperature,
        chat.topK,
        chat.topP,
        chat.minP,
        chat.gpuPromptProcessing,
        chat.systemPrompt,
    ).joinToString("|")

    private fun effectiveSystemPrompt''',
    1,
)

# Replace the last stock Material error dialog too.
error_start = "    private fun showError(title: String, throwable: Throwable) {"
error_end = "    private fun friendlyMessage(throwable: Throwable): String {"
new_error = r'''    private fun showError(title: String, throwable: Throwable) {
        showAppSheet(
            title = title,
            message = friendlyMessage(throwable),
            actions = listOf(SheetAction("OK") { it.dismiss() }),
        )
    }
'''
main_text = replace_function(main_text, error_start, error_end, new_error)

# No app-owned stock menu/dialog builders remain.
if "MaterialAlertDialogBuilder" in main_text:
    raise SystemExit("stock MaterialAlertDialogBuilder remained after custom-sheet patch")

main.write_text(main_text)

# Regression guards for what this feature promises.
assert "fun isGpuPromptProcessingActive(): Boolean" in interface.read_text()
assert "gpuPromptProcessingActiveNative" in impl.read_text()
assert "cpu_params.n_gpu_layers = 0;" in cpp.read_text()
assert "pp_params.n_gpu_layers = -1;" in cpp.read_text()
assert "cpu_tail" in cpp.read_text()
assert "-DGGML_VULKAN=ON" in gradle.read_text()
assert "Experimental GPU prompt processing" in main.read_text()
assert "Generation threads" in main.read_text()
assert "MaterialAlertDialogBuilder" not in main.read_text()

print("v0.7 controls patch applied: custom sheets, runtime/sampling sliders, experimental Vulkan PP-only path")

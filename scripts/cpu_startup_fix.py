#!/usr/bin/env python3
"""Reduce mobile load/TTFT costs and reuse CPU workers across graph splits."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
lib = root / 'vendor/llama.cpp/examples/llama.android/lib'
cpp = lib / 'src/main/cpp/ai_chat.cpp'
impl = lib / 'src/main/java/com/arm/aichat/internal/InferenceEngineImpl.kt'
repack = root / 'vendor/llama.cpp/ggml/src/ggml-cpu/repack.cpp'

def replace(s, old, new):
    if s.count(old) != 1:
        raise SystemExit(f'Expected one anchor: {old!r}, found {s.count(old)}')
    return s.replace(old, new, 1)

s = impl.read_text()
s = replace(s, 'import java.io.File', 'import kotlinx.coroutines.asCoroutineDispatcher\nimport java.util.concurrent.Executors\nimport java.io.File')
s = replace(s, 'private val llamaDispatcher = Dispatchers.IO.limitedParallelism(1)', '''private val llamaDispatcher = Executors.newSingleThreadExecutor { task ->
        Thread(task, "AndroidLLM-inference")
    }.asCoroutineDispatcher()''')
s = replace(s, '        llamaScope.cancel()\n', '        llamaScope.cancel()\n        llamaDispatcher.close()\n')
impl.write_text(s)

s = cpp.read_text()
s = replace(s, '#include <sampling.h>', '#include <sampling.h>\n#include <fstream>\n#include <sched.h>\n#include "ggml-cpu.h"')
marker = 'static int                                g_context_size = DEFAULT_CONTEXT_SIZE;'
s = replace(s, marker, marker + r'''
static ggml_threadpool_t g_cpu_pool = nullptr;

// Use the allowed performance cores when Android exposes heterogeneous CPU
// capacity. Never hard-code S23 CPU IDs; emulators/uniform CPUs use all cores.
static std::vector<int> performance_cpus() {
    cpu_set_t allowed;
    CPU_ZERO(&allowed);
    if (sched_getaffinity(getpid(), sizeof(allowed), &allowed) != 0) return {};
    std::vector<std::pair<int, int>> cpus;
    int minimum = INT_MAX;
    int maximum = 0;
    for (int cpu = 0; cpu < CPU_SETSIZE && cpu < GGML_MAX_N_THREADS; ++cpu) {
        if (!CPU_ISSET(cpu, &allowed)) continue;
        int capacity = 0;
        std::ifstream file("/sys/devices/system/cpu/cpu" + std::to_string(cpu) + "/cpu_capacity");
        file >> capacity;
        if (capacity <= 0) return {}; // no reliable topology: normal scheduling
        cpus.emplace_back(cpu, capacity);
        minimum = std::min(minimum, capacity);
        maximum = std::max(maximum, capacity);
    }
    if (cpus.empty() || maximum < minimum * 1.25) return {};
    std::vector<int> result;
    for (const auto & cpu : cpus) {
        if (cpu.second > minimum * 1.10) result.push_back(cpu.first);
    }
    return result;
}

static void release_cpu_pool() {
    if (g_context) llama_detach_threadpool(g_context);
    if (g_cpu_pool) ggml_threadpool_free(g_cpu_pool);
    g_cpu_pool = nullptr;
}
''')
s = replace(s, '#include <fstream>', '#include <fstream>\n#include <climits>')
s = replace(s, '    cpu_params.n_gpu_layers = 0;', '''    cpu_params.n_gpu_layers = 0;
    cpu_params.load_mode = LLAMA_LOAD_MODE_MMAP;
    const int64_t load_start = ggml_time_us();''')
s = replace(s, '    g_model = model;', '''    g_model = model;
    LOGi("AndroidLLM timings: weights loaded in %.3f seconds", (ggml_time_us() - load_start) / 1e6);''')
# Small physical batches limit activation/work-buffer reservations on phones.
# Logical batches remain user-controlled; llama_decode splits them internally.
s = replace(s, '    ctx_params.n_ubatch = batch_size;', '    ctx_params.n_ubatch = std::min(batch_size, 64);')
s = replace(s, '    g_context = init_context(', '''    const auto fast_cpus = performance_cpus();
    if (!fast_cpus.empty()) {
        g_generation_threads = std::min(g_generation_threads, (int) fast_cpus.size());
        g_prompt_threads = std::min(g_prompt_threads, (int) fast_cpus.size());
    }
    const int64_t context_start = ggml_time_us();
    g_context = init_context(''')
anchor = '''    g_batch = llama_batch_init(g_batch_size, 0, 1);'''
s = replace(s, anchor, '''    // One persistent pool serves both prefill and decode. The graph plan picks
    // the active thread count, so idle prefill workers never compete with TG.
    auto pool_params = ggml_threadpool_params_default(std::max(g_generation_threads, g_prompt_threads));
    pool_params.poll = 20;
    pool_params.paused = true;
    for (int cpu : fast_cpus) pool_params.cpumask[cpu] = true;
    g_cpu_pool = ggml_threadpool_new(&pool_params);
    if (!g_cpu_pool) return 3;
    llama_attach_threadpool(g_context, g_cpu_pool, g_cpu_pool);
    LOGi("AndroidLLM persistent CPU pool: tg=%d pp=%d fast_cores=%zu ubatch=64", g_generation_threads, g_prompt_threads, fast_cpus.size());
    LOGi("AndroidLLM timings: context prepared in %.3f seconds", (ggml_time_us() - context_start) / 1e6);

''' + anchor)
s = replace(s, '''Java_com_arm_aichat_internal_InferenceEngineImpl_unload(JNIEnv *, jobject) {
''', '''Java_com_arm_aichat_internal_InferenceEngineImpl_unload(JNIEnv *, jobject) {
    release_cpu_pool();
''')
# Measure actual prefill separately from startup and decode in device logs.
s = replace(s, '    // Obtain and tokenize user prompt\n', '    const int64_t prompt_start = ggml_time_us();\n    // Obtain and tokenize user prompt\n')
s = replace(s, '    current_position += (int) user_tokens.size();', '''    current_position += (int) user_tokens.size();
    LOGi("AndroidLLM timings: user prefill %zu tokens in %.3f seconds", user_tokens.size(), (ggml_time_us() - prompt_start) / 1e6);''')
cpp.write_text(s)

# Repacking all MoE expert tensors copies gigabytes into anonymous memory at
# every load. On phones this competes with the mapped GGUF and can force zram
# traffic. Keep 3D expert tensors mmap-backed; 2D shared/dense weights still use
# optimized repacking, and the normal expert kernels retain ARM dotprod/I8MM.
s = repack.read_text()
s = replace(s, '''static const ggml::cpu::tensor_traits * ggml_repack_get_optimal_repack_type(const struct ggml_tensor * cur) {''', '''static const ggml::cpu::tensor_traits * ggml_repack_get_optimal_repack_type(const struct ggml_tensor * cur) {
    // AndroidLLM: preserve zero-copy mmap for MoE expert banks.
    if (ggml_n_dims(cur) > 2) return nullptr;''')
repack.write_text(s)
print('Startup fix: mmap expert banks, 64-token microbatches, persistent CPU pool and topology-aware affinity')

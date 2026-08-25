#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
vulkan_cmake = llama / "ggml/src/ggml-vulkan/CMakeLists.txt"

for path in (cpp, vulkan_cmake):
    if not path.exists():
        raise SystemExit(f"missing generated llama.cpp file: {path}")

# Android CMake runs in cross-compilation mode and normally searches only the
# target sysroot. SPIRV-Headers is a host-side shader-build dependency, so allow
# this one package lookup to escape the Android root and find Ubuntu's installed
# CMake package config.
cmake_text = vulkan_cmake.read_text()
old_find = "find_package(SPIRV-Headers CONFIG REQUIRED)"
new_find = "find_package(SPIRV-Headers CONFIG REQUIRED NO_CMAKE_FIND_ROOT_PATH)"
if old_find not in cmake_text:
    raise SystemExit("SPIRV-Headers find_package line not found")
vulkan_cmake.write_text(cmake_text.replace(old_find, new_find, 1))

cpp_text = cpp.read_text()

# Make state transfer transactional. The experimental PP path is allowed to
# mutate the authoritative CPU KV cache only if the entire GPU-prefix -> CPU-tail
# handoff succeeds. If anything fails, restore the exact pre-prompt CPU state and
# retry the whole prompt on CPU.
helper_start = cpp_text.find("static bool copy_sequence_state(llama_context *src, llama_context *dst) {")
helper_end_marker = "static bool sync_gpu_pp_to_cpu() {"
helper_end_start = cpp_text.find(helper_end_marker, helper_start)
if helper_start < 0 or helper_end_start < 0:
    raise SystemExit("GPU PP state-transfer helper block not found")
helper_end = cpp_text.find("\n}", helper_end_start)
if helper_end < 0:
    raise SystemExit("GPU PP sync helper end not found")
helper_end += 2

new_helpers = r'''static bool save_sequence_state(llama_context *ctx, std::vector<uint8_t> &state) {
    if (!ctx) return false;
    const size_t size = llama_state_seq_get_size(ctx, 0);
    if (size == 0) return false;
    state.resize(size);
    const size_t copied = llama_state_seq_get_data(ctx, state.data(), state.size(), 0);
    if (copied == 0) {
        state.clear();
        return false;
    }
    state.resize(copied);
    return true;
}

static bool restore_sequence_state(llama_context *ctx, const std::vector<uint8_t> &state) {
    if (!ctx || state.empty()) return false;
    llama_memory_clear(llama_get_memory(ctx), false);
    return llama_state_seq_set_data(ctx, state.data(), state.size(), 0) > 0;
}

static bool copy_sequence_state(llama_context *src, llama_context *dst) {
    std::vector<uint8_t> state;
    return save_sequence_state(src, state) && restore_sequence_state(dst, state);
}

static bool sync_cpu_to_gpu_pp() {
    if (!g_gpu_pp_active || !g_pp_context) return false;
    return copy_sequence_state(g_context, g_pp_context);
}

static bool sync_gpu_pp_to_cpu() {
    if (!g_gpu_pp_active || !g_pp_context) return false;
    return copy_sequence_state(g_pp_context, g_context);
}'''
cpp_text = cpp_text[:helper_start] + new_helpers + cpp_text[helper_end:]

user_start_marker = "    bool prompt_ok = false;\n    if (g_gpu_pp_active && g_pp_context && user_tokens.size() > 1 && sync_cpu_to_gpu_pp()) {"
user_start = cpp_text.find(user_start_marker)
user_end_marker = "\n\n    // Update position\n    current_position += (int) user_tokens.size();"
user_end = cpp_text.find(user_end_marker, user_start)
if user_start < 0 or user_end < 0:
    raise SystemExit("experimental GPU user-prompt block not found")

new_user_block = r'''    bool prompt_ok = false;
    std::vector<uint8_t> cpu_state_before_gpu;
    const bool have_cpu_backup =
            g_gpu_pp_active &&
            g_pp_context &&
            user_tokens.size() > 1 &&
            save_sequence_state(g_context, cpu_state_before_gpu);

    if (have_cpu_backup && sync_cpu_to_gpu_pp()) {
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
            LOGw("Experimental GPU PP failed during user prompt; restoring CPU state and retrying on CPU");
            g_gpu_pp_active = false;
            if (!restore_sequence_state(g_context, cpu_state_before_gpu)) {
                LOGe("Could not restore CPU sequence state after GPU PP failure");
                return 3;
            }
        }
    }

    if (!prompt_ok) {
        if (decode_tokens_in_batches(g_context, g_batch, user_tokens, current_position, true)) {
            LOGe("%s: llama_decode() failed!", __func__);
            return 2;
        }
    }'''
cpp_text = cpp_text[:user_start] + new_user_block + cpp_text[user_end:]
cpp.write_text(cpp_text)

final_cpp = cpp.read_text()
final_cmake = vulkan_cmake.read_text()
assert "cpu_state_before_gpu" in final_cpp
assert "restore_sequence_state(g_context, cpu_state_before_gpu)" in final_cpp
assert "NO_CMAKE_FIND_ROOT_PATH" in final_cmake

print("GPU PP reliability patch applied: host SPIR-V discovery + transactional CPU KV fallback")

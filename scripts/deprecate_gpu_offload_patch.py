#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
gradle = llama / "examples/llama.android/lib/build.gradle.kts"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"

for path in (gradle, cpp, main):
    if not path.exists():
        raise SystemExit(f"missing generated file: {path}")

# Vulkan prompt processing is deprecated. Keep the old API/data plumbing only so
# upgrades from v0.7.x do not break, but make the native build explicitly CPU-only.
gradle_text = gradle.read_text()
gradle_text = gradle_text.replace('                arguments += "-DGGML_VULKAN=ON"\n', "")
arch_line = '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.6-a+dotprod+fp16+i8mm"\n'
vulkan_off = '                arguments += "-DGGML_VULKAN=OFF"\n'
if arch_line not in gradle_text:
    raise SystemExit("optimized ARM architecture flag not found")
if vulkan_off not in gradle_text:
    gradle_text = gradle_text.replace(arch_line, arch_line + vulkan_off, 1)
gradle.write_text(gradle_text)

# Ignore the compatibility boolean even if an old caller somehow passes true.
# This prevents stale saved settings or an older UI from reactivating GPU PP.
cpp_text = cpp.read_text()
old_request = "    g_gpu_pp_requested = jgpu_prompt_processing == JNI_TRUE;\n"
new_request = '''    g_gpu_pp_requested = false;
    if (jgpu_prompt_processing == JNI_TRUE) {
        LOGw("GPU prompt processing is deprecated and ignored; using CPU-only inference");
    }
'''
if old_request in cpp_text:
    cpp_text = cpp_text.replace(old_request, new_request, 1)
elif "g_gpu_pp_requested = false;" not in cpp_text:
    raise SystemExit("GPU prompt-processing request assignment not found")
cpp.write_text(cpp_text)

# The generated app must never request the compatibility path.
main_text = main.read_text()
main_text = main_text.replace("                chat.gpuPromptProcessing,\n", "                false,\n")
main.write_text(main_text)

final_gradle = gradle.read_text()
final_cpp = cpp.read_text()
final_main = main.read_text()
assert "GGML_VULKAN=ON" not in final_gradle
assert "GGML_VULKAN=OFF" in final_gradle
assert "g_gpu_pp_requested = false;" in final_cpp
assert "GPU prompt processing is deprecated and ignored" in final_cpp
assert "                chat.gpuPromptProcessing,\n" not in final_main

print("GPU prompt processing deprecated: Vulkan forced OFF and runtime requests ignored")

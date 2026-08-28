#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
gradle = llama / "examples/llama.android/lib/build.gradle.kts"
cmake = llama / "examples/llama.android/lib/src/main/cpp/CMakeLists.txt"

for path in (gradle, cmake):
    if not path.exists():
        raise SystemExit(f"missing generated llama.cpp file: {path}")

# Restore the CPU configuration that AndroidLLM used before the v0.7.0
# armv8.6/KleidiAI experiment. The known-fast Android/Termux comparison used
# llama.cpp's normal generic AArch64 CPU kernels. Keep the reliable monolithic
# backend (no Android dlopen), but stop forcing one ISA/kernel family globally.
gradle_text = gradle.read_text()
required = [
    '-DBUILD_SHARED_LIBS=OFF',
    '-DGGML_BACKEND_DL=OFF',
    '-DGGML_CPU_ALL_VARIANTS=OFF',
    '-DGGML_VULKAN=OFF',
]
for flag in required:
    if flag not in gradle_text:
        raise SystemExit(f"expected final CPU build flag not found: {flag}")

for arch in (
    '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.6-a+dotprod+fp16+i8mm"\n',
    '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16"\n',
):
    gradle_text = gradle_text.replace(arch, "")

gradle.write_text(gradle_text)

# KleidiAI is useful for the tensor types it implements, but the q4_K model that
# exposed the current regression explicitly falls back because KleidiAI has no
# q4_K kernel. Enabling its extra buffer/repack path anyway adds model-load work
# without accelerating that hot quant. Restore upstream/known-good OFF behavior.
cmake_text = cmake.read_text()
if 'set(GGML_CPU_KLEIDIAI ON)' in cmake_text:
    cmake_text = cmake_text.replace('set(GGML_CPU_KLEIDIAI ON)', 'set(GGML_CPU_KLEIDIAI OFF)', 1)
elif 'set(GGML_CPU_KLEIDIAI OFF)' not in cmake_text:
    raise SystemExit("GGML_CPU_KLEIDIAI setting not found")
cmake.write_text(cmake_text)

final_gradle = gradle.read_text()
final_cmake = cmake.read_text()
assert '-DBUILD_SHARED_LIBS=OFF' in final_gradle
assert '-DGGML_BACKEND_DL=OFF' in final_gradle
assert '-DGGML_CPU_ALL_VARIANTS=OFF' in final_gradle
assert '-DGGML_VULKAN=OFF' in final_gradle
assert 'GGML_CPU_ARM_ARCH' not in final_gradle
assert 'set(GGML_CPU_KLEIDIAI OFF)' in final_cmake
assert 'set(GGML_CPU_KLEIDIAI ON)' not in final_cmake

print("stable CPU performance restored: static generic AArch64 backend, KleidiAI OFF, Vulkan OFF")

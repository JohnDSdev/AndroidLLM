#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
gradle = llama / "examples/llama.android/lib/build.gradle.kts"
cmake = llama / "examples/llama.android/lib/src/main/cpp/CMakeLists.txt"

for path in (cpp, gradle, cmake):
    if not path.exists():
        raise SystemExit(f"missing generated llama.cpp file: {path}")

# Keep the reliable static backend introduced in v0.5.1, but stop compiling it
# as baseline AArch64. AndroidLLM targets modern ARM64 phones; armv8.6 gives ggml
# dot-product, FP16 vector arithmetic and I8MM kernels without Android's plugin
# loading problems. This is especially important for K-quants and mixed MoE
# quantization while restoring the fast dense-model path seen in older builds.
gradle_text = gradle.read_text()
required = [
    '-DBUILD_SHARED_LIBS=OFF',
    '-DGGML_BACKEND_DL=OFF',
    '-DGGML_CPU_ALL_VARIANTS=OFF',
]
for flag in required:
    if flag not in gradle_text:
        raise SystemExit(f"expected static CPU build flag not found: {flag}")

old_arch = '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16"\n'
new_arch = '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.6-a+dotprod+fp16+i8mm"\n'
if old_arch not in gradle_text:
    raise SystemExit("expected ARM architecture line not found")
gradle_text = gradle_text.replace(old_arch, new_arch, 1)
gradle.write_text(gradle_text)

# Upstream's Android binding enables Arm KleidiAI, but our reliability patches
# had disabled it. Re-enable its optimized quantized matmul kernels now that the
# CPU backend is linked statically and no longer depends on runtime dlopen().
cmake_text = cmake.read_text()
if 'set(GGML_CPU_KLEIDIAI OFF)' not in cmake_text:
    raise SystemExit("expected KleidiAI OFF setting not found")
cmake_text = cmake_text.replace('set(GGML_CPU_KLEIDIAI OFF)', 'set(GGML_CPU_KLEIDIAI ON)', 1)
cmake.write_text(cmake_text)

# Keep the static initialization and load guard inserted by prepare_llama.py.
cpp_text = cpp.read_text()
if 'ggml_backend_load(' in cpp_text or 'ggml_backend_load_all_from_path' in cpp_text:
    raise SystemExit("unexpected dynamic backend loader in generated Android binding")
if 'llama_backend_init();' not in cpp_text:
    raise SystemExit("static backend initialization call missing")
if 'ggml_backend_reg_count() == 0' not in cpp_text:
    raise SystemExit("backend registration guard missing")

final_gradle = gradle.read_text()
final_cmake = cmake.read_text()
assert '-DBUILD_SHARED_LIBS=OFF' in final_gradle
assert '-DGGML_BACKEND_DL=OFF' in final_gradle
assert '-DGGML_CPU_ALL_VARIANTS=OFF' in final_gradle
assert '-DGGML_CPU_ARM_ARCH=armv8.6-a+dotprod+fp16+i8mm' in final_gradle
assert 'set(GGML_CPU_KLEIDIAI ON)' in final_cmake

print("performance patch applied: static armv8.6 dotprod/fp16/i8mm CPU backend with KleidiAI")

#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
gradle = llama / "examples/llama.android/lib/build.gradle.kts"

for path in (cpp, gradle):
    if not path.exists():
        raise SystemExit(f"missing generated llama.cpp file: {path}")

# v0.5.0 packaged a Termux-style dynamic libggml-cpu.so and attempted to load it
# with ggml_backend_load(). On some Android installs dlopen() of that backend
# fails even though the file exists in nativeLibraryDir. Avoid the plugin loader
# completely: keep the generic ARM CPU configuration that matches the fast Termux
# build, but link the CPU backend directly into libai-chat.so so GGML_USE_CPU
# registers it during normal registry construction.
#
# prepare_llama.py already configures the reliable static backend build:
#   BUILD_SHARED_LIBS=OFF
#   GGML_BACKEND_DL=OFF
#   GGML_CPU_ALL_VARIANTS=OFF
#   GGML_OPENMP=OFF
# The only performance-hostile part was the forced armv8.2+dotprod+fp16 ISA.
# Remove that override and let ggml build its normal generic aarch64 CPU kernels.
gradle_text = gradle.read_text()
required = [
    '-DBUILD_SHARED_LIBS=OFF',
    '-DGGML_BACKEND_DL=OFF',
    '-DGGML_CPU_ALL_VARIANTS=OFF',
]
for flag in required:
    if flag not in gradle_text:
        raise SystemExit(f"expected static CPU build flag not found: {flag}")

arm_arch_line = '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16"\n'
if arm_arch_line not in gradle_text:
    raise SystemExit("forced ARM architecture line not found")
gradle_text = gradle_text.replace(arm_arch_line, "", 1)
gradle.write_text(gradle_text)

# Keep the static initialization and load guard inserted by prepare_llama.py.
# With GGML_BACKEND_DL=OFF and GGML_CPU enabled, ggml-backend-reg.cpp compiles
# GGML_USE_CPU and registers ggml_backend_cpu_reg() inside the process. There is
# no directory scan or dlopen step left to fail on Android.
cpp_text = cpp.read_text()
if 'ggml_backend_load(' in cpp_text or 'ggml_backend_load_all_from_path' in cpp_text:
    raise SystemExit("unexpected dynamic backend loader in generated Android binding")
if 'llama_backend_init();' not in cpp_text:
    raise SystemExit("static backend initialization call missing")
if 'ggml_backend_reg_count() == 0' not in cpp_text:
    raise SystemExit("backend registration guard missing")

final_gradle = gradle.read_text()
assert '-DBUILD_SHARED_LIBS=OFF' in final_gradle
assert '-DGGML_BACKEND_DL=OFF' in final_gradle
assert '-DGGML_CPU_ALL_VARIANTS=OFF' in final_gradle
assert 'GGML_CPU_ARM_ARCH' not in final_gradle

print("performance patch applied: generic ARM CPU backend linked statically; no Android dlopen path")

#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
llama = root / "vendor" / "llama.cpp"
cpp = llama / "examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
cmake = llama / "examples/llama.android/lib/src/main/cpp/CMakeLists.txt"
gradle = llama / "examples/llama.android/lib/build.gradle.kts"

for path in (cpp, cmake, gradle):
    if not path.exists():
        raise SystemExit(f"missing generated llama.cpp file: {path}")

# The same Ling GGUF reaches ~17 tok/s in Termux's b10516 package. Mirror its
# CPU-side build strategy instead of guessing at a device-specific -march:
# shared libraries + dynamic backend loading + generic ARM CPU backend + no
# OpenMP. The previous AndroidLLM build forced armv8.2+dotprod+fp16 into a
# statically linked backend and is catastrophically slow on this workload.
cpp_text = cpp.read_text()
old_init = '''    (void) env;
    (void) nativeLibDir;

    // The CPU backend is linked into the app, so registry construction is enough.
    llama_backend_init();
    const size_t backend_count = ggml_backend_reg_count();
    LOGi("Backend initiated; %zu backend(s) registered.", backend_count);
    for (size_t i = 0; i < backend_count; ++i) {
        auto *reg = ggml_backend_reg_get(i);
        LOGi("Registered backend: %s", ggml_backend_reg_name(reg));
    }'''
new_init = '''    const auto *path_to_backend = env->GetStringUTFChars(nativeLibDir, nullptr);
    LOGi("Loading CPU backend from %s", path_to_backend);
    ggml_backend_load_all_from_path(path_to_backend);
    env->ReleaseStringUTFChars(nativeLibDir, path_to_backend);

    llama_backend_init();
    const size_t backend_count = ggml_backend_reg_count();
    LOGi("Backend initialization complete; %zu backend(s) registered.", backend_count);
    for (size_t i = 0; i < backend_count; ++i) {
        auto *reg = ggml_backend_reg_get(i);
        LOGi("Registered backend: %s", ggml_backend_reg_name(reg));
    }'''
if old_init not in cpp_text:
    raise SystemExit("static Android backend initialization block not found")
cpp.write_text(cpp_text.replace(old_init, new_init, 1))

# Undo the forced static ARMv8.2 build. This intentionally matches the current
# Termux llama-cpp package at b10516 for the CPU-relevant flags:
#   BUILD_SHARED_LIBS=ON, GGML_BACKEND_DL=ON, GGML_OPENMP=OFF,
#   GGML_CPU_ALL_VARIANTS=OFF, and no GGML_CPU_ARM_ARCH override.
gradle_text = gradle.read_text()
replacements = {
    'arguments += "-DBUILD_SHARED_LIBS=OFF"': 'arguments += "-DBUILD_SHARED_LIBS=ON"',
    'arguments += "-DGGML_BACKEND_DL=OFF"': 'arguments += "-DGGML_BACKEND_DL=ON"',
}
for old, new in replacements.items():
    if old not in gradle_text:
        raise SystemExit(f"expected single-backend Gradle flag not found: {old}")
    gradle_text = gradle_text.replace(old, new, 1)

# Keep ALL_VARIANTS off, but remove the forced ARM ISA so ggml builds its normal
# generic Android/aarch64 CPU module, just like Termux.
if 'arguments += "-DGGML_CPU_ALL_VARIANTS=OFF"' not in gradle_text:
    raise SystemExit("expected GGML_CPU_ALL_VARIANTS=OFF flag not found")
arm_arch_line = '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16"\n'
if arm_arch_line not in gradle_text:
    raise SystemExit("forced ARM architecture line not found")
gradle_text = gradle_text.replace(arm_arch_line, "", 1)
gradle.write_text(gradle_text)

# Dynamic backend modules are not linked to ai-chat by design, so Gradle may skip
# building libggml-cpu.so when it only asks for the JNI target. Make the generic
# CPU backend an explicit build dependency; the workflow then copies it into the
# APK's jniLibs directory and verifies it is actually present.
cmake_text = cmake.read_text()
marker = '''target_link_libraries(${CMAKE_PROJECT_NAME}
        llama
        llama-common
        android
        log)
'''
if marker not in cmake_text:
    raise SystemExit("ai-chat target_link_libraries block not found")
backend_block = marker + '''
# AndroidLLM: the runtime-loaded CPU module must be built even though ai-chat
# does not link against it directly.
if(ANDROID_ABI STREQUAL "arm64-v8a" AND TARGET ggml-cpu)
    add_dependencies(${CMAKE_PROJECT_NAME} ggml-cpu)
endif()
'''
cmake.write_text(cmake_text.replace(marker, backend_block, 1))

# Regression guards. These encode the known-good Termux comparison so a future
# cleanup cannot silently restore the 0.5 tok/s static build.
assert 'ggml_backend_load_all_from_path' in cpp.read_text()
final_gradle = gradle.read_text()
assert '-DBUILD_SHARED_LIBS=ON' in final_gradle
assert '-DGGML_BACKEND_DL=ON' in final_gradle
assert '-DGGML_CPU_ALL_VARIANTS=OFF' in final_gradle
assert 'GGML_CPU_ARM_ARCH' not in final_gradle
assert 'add_dependencies(${CMAKE_PROJECT_NAME} ggml-cpu)' in cmake.read_text()

print("performance patch applied: Termux-matched dynamic generic ARM CPU backend")

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

# Restore llama.cpp's runtime backend loader. The previous reliability fix linked
# one armv8.2+dotprod+fp16 CPU backend statically; that made model loading robust,
# but some quantized/MoE workloads fall back to painfully slow kernels. Build and
# package all official Android ARM variants instead, then let llama.cpp score and
# select the best compatible backend on the actual phone.
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
    LOGi("Loading optimized CPU backends from %s", path_to_backend);
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

# Undo the single-backend Gradle settings inserted by prepare_llama.py and match
# llama.cpp's released Android CPU build strategy: shared backend modules,
# runtime dynamic loading, GGML_NATIVE off, and all ARM CPU variants.
gradle_text = gradle.read_text()
replacements = {
    'arguments += "-DBUILD_SHARED_LIBS=OFF"': 'arguments += "-DBUILD_SHARED_LIBS=ON"',
    'arguments += "-DGGML_BACKEND_DL=OFF"': 'arguments += "-DGGML_BACKEND_DL=ON"',
    'arguments += "-DGGML_CPU_ALL_VARIANTS=OFF"': 'arguments += "-DGGML_CPU_ALL_VARIANTS=ON"',
}
for old, new in replacements.items():
    if old not in gradle_text:
        raise SystemExit(f"expected single-backend Gradle flag not found: {old}")
    gradle_text = gradle_text.replace(old, new, 1)
arm_arch_line = '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16"\n'
if arm_arch_line not in gradle_text:
    raise SystemExit("forced ARM architecture line not found")
gradle_text = gradle_text.replace(arm_arch_line, "", 1)
gradle.write_text(gradle_text)

# Android Gradle normally builds only the JNI library and its linked dependency
# graph. Dynamic CPU backend modules are deliberately not linked to ai-chat, so
# force their targets into that graph. The if(TARGET) guards keep this resilient
# if upstream changes which variants are available on a particular tag.
cmake_text = cmake.read_text()
marker = '''target_link_libraries(${CMAKE_PROJECT_NAME}
        llama
        llama-common
        android
        log)
'''
if marker not in cmake_text:
    raise SystemExit("ai-chat target_link_libraries block not found")
variant_block = marker + '''
# AndroidLLM: force runtime-selectable ARM CPU backend modules to be built.
if(ANDROID_ABI STREQUAL "arm64-v8a")
    set(ANDROIDLLM_CPU_VARIANTS
        ggml-cpu-android_armv8.0_1
        ggml-cpu-android_armv8.2_1
        ggml-cpu-android_armv8.2_2
        ggml-cpu-android_armv8.6_1
        ggml-cpu-android_armv9.0_1
        ggml-cpu-android_armv9.2_1
        ggml-cpu-android_armv9.2_2
    )
    foreach(cpu_variant IN LISTS ANDROIDLLM_CPU_VARIANTS)
        if(TARGET ${cpu_variant})
            add_dependencies(${CMAKE_PROJECT_NAME} ${cpu_variant})
        endif()
    endforeach()
endif()
'''
cmake_text = cmake_text.replace(marker, variant_block, 1)
cmake.write_text(cmake_text)

# Regression guards. A build that silently returns to the single generic backend
# is worse than a failed CI run because it looks healthy while running 30x slower.
assert 'ggml_backend_load_all_from_path' in cpp.read_text()
final_gradle = gradle.read_text()
assert '-DGGML_BACKEND_DL=ON' in final_gradle
assert '-DGGML_CPU_ALL_VARIANTS=ON' in final_gradle
assert 'GGML_CPU_ARM_ARCH' not in final_gradle
assert 'ggml-cpu-android_armv8.6_1' in cmake.read_text()

print("performance patch applied: dynamic runtime-selected ARM CPU variants")

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

# The same Ling GGUF reaches ~17 tok/s in Termux's b10516 package. Keep the
# CPU-side build strategy aligned with Termux: shared libraries + dynamic backend
# loading + a generic ARM CPU backend + no OpenMP and no forced -march.
#
# Android wrinkle: directory enumeration inside applicationInfo.nativeLibraryDir
# is not reliable on every device/install layout even when dlopen() of an exact
# library path works. v0.4.0 used ggml_backend_load_all_from_path(), so the CPU
# .so could be packaged correctly and still never get registered. Load the exact
# libggml-cpu.so plugin instead and retry it lazily before model loading.
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
    g_native_lib_dir = path_to_backend ? path_to_backend : "";
    env->ReleaseStringUTFChars(nativeLibDir, path_to_backend);

    // Load the exact CPU plugin. Avoid relying on std::filesystem directory
    // iteration over Android's nativeLibraryDir, which can fail on some installs.
    ensure_cpu_backend_loaded();
    llama_backend_init();

    const size_t backend_count = ggml_backend_reg_count();
    LOGi("Backend initialization complete; %zu backend(s) registered.", backend_count);
    for (size_t i = 0; i < backend_count; ++i) {
        auto *reg = ggml_backend_reg_get(i);
        LOGi("Registered backend: %s", ggml_backend_reg_name(reg));
    }'''
if old_init not in cpp_text:
    raise SystemExit("static Android backend initialization block not found")

# Insert persistent native-lib path + an idempotent exact-path loader before init.
init_marker = '''extern "C"\nJNIEXPORT void JNICALL\nJava_com_arm_aichat_internal_InferenceEngineImpl_init'''
if init_marker not in cpp_text:
    raise SystemExit("JNI init marker not found")
helper = '''static std::string g_native_lib_dir;\n\nstatic bool ensure_cpu_backend_loaded() {\n    if (ggml_backend_reg_count() > 0) {\n        return true;\n    }\n    if (g_native_lib_dir.empty()) {\n        g_last_native_error = "Android native library directory is unavailable";\n        LOGe("%s", g_last_native_error.c_str());\n        return false;\n    }\n\n    const std::string cpu_backend_path = g_native_lib_dir + "/libggml-cpu.so";\n    LOGi("Loading CPU backend explicitly from %s", cpu_backend_path.c_str());\n    ggml_backend_reg_t cpu_reg = ggml_backend_load(cpu_backend_path.c_str());\n    if (cpu_reg == nullptr) {\n        g_last_native_error = "Could not load llama.cpp CPU backend from " + cpu_backend_path;\n        LOGe("%s", g_last_native_error.c_str());\n        return false;\n    }\n\n    LOGi("Loaded CPU backend: %s", ggml_backend_reg_name(cpu_reg));\n    return ggml_backend_reg_count() > 0;\n}\n\n'''
cpp_text = cpp_text.replace(init_marker, helper + init_marker, 1)
cpp_text = cpp_text.replace(old_init, new_init, 1)

# prepare_llama.py added a defensive backend-count check. Make it self-healing:
# clear stale diagnostics, explicitly retry the exact CPU plugin, then fail with
# the real loader error only if registration is still absent.
old_load_guard = '''    g_last_native_error.clear();
    if (ggml_backend_reg_count() == 0) {
        g_last_native_error = "AndroidLLM started without a registered llama.cpp backend";
        return 2;
    }'''
new_load_guard = '''    g_last_native_error.clear();
    if (!ensure_cpu_backend_loaded()) {
        if (g_last_native_error.empty()) {
            g_last_native_error = "AndroidLLM could not register the llama.cpp CPU backend";
        }
        return 2;
    }'''
if old_load_guard not in cpp_text:
    raise SystemExit("generated backend-count guard not found")
cpp_text = cpp_text.replace(old_load_guard, new_load_guard, 1)
cpp.write_text(cpp_text)

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

# Regression guards. A build must both package the Termux-style backend and call
# the exact-path plugin loader rather than depending solely on directory scans.
final_cpp = cpp.read_text()
final_gradle = gradle.read_text()
assert 'ggml_backend_load(cpu_backend_path.c_str())' in final_cpp
assert 'ensure_cpu_backend_loaded()' in final_cpp
assert 'ggml_backend_load_all_from_path(path_to_backend)' not in final_cpp
assert '-DBUILD_SHARED_LIBS=ON' in final_gradle
assert '-DGGML_BACKEND_DL=ON' in final_gradle
assert '-DGGML_CPU_ALL_VARIANTS=OFF' in final_gradle
assert 'GGML_CPU_ARM_ARCH' not in final_gradle
assert 'add_dependencies(${CMAKE_PROJECT_NAME} ggml-cpu)' in cmake.read_text()

print("performance patch applied: exact-path Termux-style Android CPU backend loader")

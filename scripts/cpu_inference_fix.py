#!/usr/bin/env python3
"""Final generated-source patch: CPU ISA, GC-safe JNI and frame-paced reveal."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
lib = root / 'vendor/llama.cpp/examples/llama.android/lib'
gradle = lib / 'build.gradle.kts'
impl = lib / 'src/main/java/com/arm/aichat/internal/InferenceEngineImpl.kt'
main = root / 'app/src/main/java/com/johndsdev/androidllm/MainActivity.kt'

def replace(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f'Expected one patch anchor: {old!r}')
    return text.replace(old, new, 1)

# Match the known-fast v0.7.0 ISA on Snapdragon 8 Gen 2. GGML_NATIVE is OFF
# during cross-compilation, so deleting this flag silently loses dotprod/I8MM.
s = gradle.read_text()
s = replace(s, '                arguments += "-DGGML_CPU_ALL_VARIANTS=OFF"',
    '                arguments += "-DGGML_CPU_ALL_VARIANTS=OFF"\n'
    '                arguments += "-DGGML_CPU_ARM_ARCH=armv8.6-a+dotprod+fp16+i8mm"')
gradle.write_text(s)

# FastNative keeps ART's thread runnable throughout native work and can block
# GC. Model loading, decoding and ggml's barriers are NOT short bounded calls.
# See https://developer.android.com/reference/dalvik/annotation/optimization/FastNative
s = impl.read_text()
assert '    @FastNative\n    private external fun generateNextToken' in s
s = s.replace('import dalvik.annotation.optimization.FastNative\n', '')
s = s.replace('    @FastNative\n', '')
impl.write_text(s)

# Keep the same reveal speed, but append a small batch once per display frame,
# rather than allocating/laying out a TextView every 3-8 ms. Preserve pairs.
s = main.read_text()
s = replace(s, '                            val nextVisible = visibleChars + 1', '''                            val nextVisible = synchronized(buffer) {
                                var end = (visibleChars + if (totalChars - visibleChars > 48) 6 else 2)
                                    .coerceAtMost(buffer.length)
                                if (end < buffer.length && end > visibleChars &&
                                    Character.isHighSurrogate(buffer[end - 1])) end += 1
                                end
                            }''')
s = replace(s, '                            val visibleChar = nextChar[0]\n',
    '                            for (visibleChar in nextChar) {\n')
s = replace(s, '''                            val now = System.currentTimeMillis()
                            val syntaxRefreshDue =''', '''                            }
                            val now = System.currentTimeMillis()
                            val syntaxRefreshDue =''')
s = replace(s, '''                            // Normally one character per ~8 ms. Once inference has
                            // finished, drain any tiny visual backlog faster without
                            // changing the measured model TPS.
                            prettyHandler.postDelayed(this, if (!generating || remaining > 48) 3L else 8L)''',
'''                            // No redraws faster than a display frame, including catch-up.
                            prettyHandler.postDelayed(this, 16L)''')
main.write_text(s)
assert '@FastNative' not in impl.read_text()
assert '-DGGML_VULKAN=OFF' in gradle.read_text()
print('CPU inference fix: armv8.6 dotprod/I8MM, ordinary JNI, frame-paced pretty mode')

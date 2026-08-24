#!/usr/bin/env python3
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
llama_lib = root / "vendor/llama.cpp/examples/llama.android/lib"
dest = root / "app/src/main/jniLibs/arm64-v8a"

if not llama_lib.exists():
    raise SystemExit("llamaLib build tree is missing")

# Find the generic runtime-loaded CPU backend built by llama.cpp. There can be
# duplicate copies in Gradle/CMake intermediate directories; prefer the newest.
matches = [p for p in llama_lib.rglob("libggml-cpu.so") if p.is_file()]
if not matches:
    raise SystemExit("libggml-cpu.so was not built; refusing to publish a backend-less APK")
src = max(matches, key=lambda p: p.stat().st_mtime_ns)

# Remove stale variants from local incremental builds, then stage exactly the
# same style of generic CPU module used by Termux's b10516 package.
dest.mkdir(parents=True, exist_ok=True)
for old in dest.glob("libggml-cpu*.so"):
    old.unlink()

target = dest / "libggml-cpu.so"
shutil.copy2(src, target)
if target.stat().st_size < 1_000_000:
    raise SystemExit(f"staged CPU backend looks suspiciously small: {target.stat().st_size} bytes")

print(f"staged libggml-cpu.so ({target.stat().st_size / 1024 / 1024:.1f} MiB) from {src}")

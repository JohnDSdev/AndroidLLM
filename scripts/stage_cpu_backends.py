#!/usr/bin/env python3
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
llama_lib = root / "vendor/llama.cpp/examples/llama.android/lib"
dest = root / "app/src/main/jniLibs/arm64-v8a"

if not llama_lib.exists():
    raise SystemExit("llamaLib build tree is missing")

# Gradle/CMake can leave the same module in more than one intermediate folder.
# Keep one copy of each unique backend filename.
matches = sorted(llama_lib.rglob("libggml-cpu-android_*.so"))
by_name = {}
for path in matches:
    by_name[path.name] = path

if len(by_name) < 3:
    found = "\n".join(str(p) for p in matches) or "(none)"
    raise SystemExit(f"expected multiple optimized ARM CPU backends, found {len(by_name)}:\n{found}")

# The fp16+dotprod and i8mm-class variants are the important performance paths
# for modern Snapdragon/ARMv9 phones. Refuse to publish an APK without them.
if not any("armv8.2_2" in name for name in by_name):
    raise SystemExit("missing armv8.2+dotprod+fp16 CPU backend")
if not any(("armv8.6" in name or "armv9.0" in name) for name in by_name):
    raise SystemExit("missing i8mm/Armv9-class CPU backend")

dest.mkdir(parents=True, exist_ok=True)
for old in dest.glob("libggml-cpu*.so"):
    old.unlink()

for name, src in sorted(by_name.items()):
    target = dest / name
    shutil.copy2(src, target)
    print(f"staged {name} ({target.stat().st_size / 1024 / 1024:.1f} MiB)")

print(f"staged {len(by_name)} optimized CPU backend variants")

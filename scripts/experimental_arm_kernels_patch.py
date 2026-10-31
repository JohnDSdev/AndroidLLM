#!/usr/bin/env python3
"""Experimental-only KleidiAI ARM kernels; stable release stays generic AArch64."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
cmake=root/"vendor/llama.cpp/examples/llama.android/lib/src/main/cpp/CMakeLists.txt"
s=cmake.read_text()
needle="set(GGML_CPU_KLEIDIAI OFF)"
if needle not in s: raise SystemExit("Expected generic CPU baseline not found")
s=s.replace(needle, "set(GGML_CPU_KLEIDIAI ON)",1)
cmake.write_text(s)
print("Experimental ARM64 KleidiAI kernels enabled. CPU-only; unsupported quants use generic kernels.")

# AndroidLLM

A basic on-device Android chat app built around the official `llama.cpp` Android binding.

## Current features

- CPU-only ARM64 GGUF inference through `llama.cpp`, including K2 Horizon and Inkling 2 Mini (`inkling2_loop` architecture)
- pinned to `llama.cpp` build `b12613` (Inkling 2 Mini looped MoE support)
- download a model by pasting a direct `.gguf` URL
- load, unload, delete, and switch downloaded models
- multiple persistent local chats
- per-chat system prompts
- configurable context length (512–131072 tokens)
- streaming responses
- local JSON chat/settings storage
- export all app data as a ZIP, including downloaded GGUF models

K2 Horizon models require compatible GGUF files. Smaller quantizations (such as 0.9B and 3.7B) are the most practical on phones; model loading and actual generation still depend on memory and device capabilities. The CI build also checks APK installation on an ARM64 Android emulator. Model inference with a K2 Horizon GGUF is not yet covered by the automated tests.

## Inkling 2 Mini compatibility

- The inference engine includes upstream Inkling 2 Mini support and the 2026-11-21 loop-scale correction. Use **mainline-layout** GGUFs, such as `ggml-org/Inkling-2-Mini-GGUF` or Unsloth's `Mainline_Support` directory, not the older fork-only `inkling2` layout.
- The app is **CPU-only** and keeps its existing text-chat flow. Model-specific vision/projector support is **not** added to the stable app.
- Inkling 2 Mini GGUFs are much larger than typical phone RAM. The official IQ4_NL file is around 17.6 GB, so on a 12 GB phone, loading is expected to fail despite the architecture being recognized. This update adds *format support*, not a working low-RAM streaming runtime.
- No full-model on-device inference benchmark is run in CI because of model memory requirements.

## Build

The GitHub Actions workflow clones the pinned `llama.cpp` source, applies the small Android-binding patch in `scripts/prepare_llama.py`, runs the downloader regression test, builds an ARM64 APK, and uploads it as an Actions artifact. Main-branch builds are also published to the `dev-build` GitHub prerelease.

For a local build, clone `llama.cpp` into `vendor/llama.cpp` at tag `b12613`, run `python3 scripts/prepare_llama.py`, install Android API 36 + NDK `29.0.13113456` + CMake `3.31.6`, then run Gradle `:app:assembleDebug` with Gradle 8.14.3.

## Development signing

Development APKs use the checked-in `signing/androidllm-dev.keystore` so successive CI builds have the same signature and can update each other without deleting app data. This key is intentionally public and must never be used for a Play Store or other production release.

## Notes

The upstream Android helper keeps live conversation state while a model stays loaded. If a model is unloaded, the app restores recent prior messages into the system prompt when loading again so the conversation can continue. This is a pragmatic first-version restoration path rather than a perfect KV-cache serialization system.

# AndroidLLM

A basic on-device Android chat app built around the official `llama.cpp` Android binding.

## Current features

- CPU-only ARM64 GGUF inference through `llama.cpp`
- pinned to `llama.cpp` build `b10524`
- download a model by pasting a direct `.gguf` URL
- load, unload, delete, and switch downloaded models
- multiple persistent local chats
- per-chat system prompts
- configurable context length (512–131072 tokens)
- streaming responses
- local JSON chat/settings storage
- export all app data as a ZIP, including downloaded GGUF models

## Build

The GitHub Actions workflow clones the pinned `llama.cpp` source, applies the small Android-binding patch in `scripts/prepare_llama.py`, builds an ARM64 debug APK, uploads it as an Actions artifact, and publishes it to the `dev-build` GitHub prerelease.

For a local build, clone `llama.cpp` into `vendor/llama.cpp` at tag `b10524`, run `python3 scripts/prepare_llama.py`, install Android API 36 + NDK `29.0.13113456` + CMake `3.31.6`, then run Gradle `:app:assembleDebug` with Gradle 8.14.3.

## Notes

The upstream Android helper keeps live conversation state while a model stays loaded. If a model is unloaded, the app restores recent prior messages into the system prompt when loading again so the conversation can continue. This is a pragmatic first-version restoration path rather than a perfect KV-cache serialization system.

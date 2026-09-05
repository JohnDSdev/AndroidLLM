# AndroidLLM

An on-device Android chat app for ARM64 GGUF models, using CPU-only llama.cpp inference.

## Version 0.8.0

- Persistent CPU worker pool: reuse threads across decode graphs, with separate configurable prompt/generation thread counts and sleeping idle workers.
- Stream only new text at bounded intervals, avoiding repeated full-response Markdown parsing and character-by-character layout work. Pretty mode reveals small batches; Markdown and copyable code cards render when generation finishes.
- Follow the latest response until the reader scrolls away; the **Latest response** control resumes following. Focus requests cannot move the transcript during generation.
- Search conversation titles and messages, browse by recent activity/date groups, see previews, and rename chats from their options menu. History rows are recycled.
- Refreshed light/dark palettes. Model weights remain resident when switching chats.
- Keep partial responses on errors; report context overflow instead of silently returning an empty answer.

Existing chats, settings, models, and the development signing identity are preserved. Context (512–131072), sampling, thinking controls, downloads, Stop, edit/regenerate, and ZIP export remain available.

## Build

CI and local builds now use the checked-in app source directly. The old chain of source-rewriting scripts has been replaced by one reviewed patch for the upstream Android binding.

Toolchain: JDK 17, Gradle 8.14.3, Android API 36, build-tools 36.0.0, NDK 29.0.14206865, CMake 3.31.6.

```sh
git clone --depth 1 --branch b10516 https://github.com/ggml-org/llama.cpp.git vendor/llama.cpp
python3 scripts/prepare_llama.py
gradle --no-daemon :app:testDebugUnitTest :app:assembleDebug
```

`prepare_llama.py` checks upstream commit `b95502ba9aa0eb73a2f4fc8878d7fbe6a847a0b9` and applies `patches/android-binding.patch` idempotently. To edit the binding, modify the prepared `vendor/llama.cpp` checkout, then regenerate the patch with `git -C vendor/llama.cpp diff --binary > patches/android-binding.patch`. App UI changes belong directly in `app/src`.

GitHub Actions runs regression tests, builds the APK, and uploads `AndroidLLM-apk`. Only main-branch builds update the `dev-build` prerelease. PR/branch builds do not replace that download.

## Validation on a device

CPU speed depends on model, quantization, device cores, context, and heat; no percentage speedup is claimed without measurements on the same phone. Compare the same GGUF and thread/settings values with a cold prompt and follow-up prompts; record time to first text and steady generation speed after warmup. The displayed tok/s is an estimate based on emitted text pieces, not exact native token accounting.

For scrolling, generate an answer longer than a screen in both display modes. Check that the bottom stays steady, scrolling up stays put, **Latest response** returns to the end, and Stop/completion preserve position. Repeat with the keyboard open and with Markdown/code, emoji, and long saved conversations. Unit tests cover concurrent stream draining, Unicode, history search/grouping, and layout-driven scrolling under Robolectric.

## Development signing

The checked-in `signing/androidllm-dev.keystore` is intentionally public. It lets development APKs update each other without deleting app data and must not be used for a production/Play Store release.

## Conversation restoration

The upstream binding retains live conversation/KV state while a model stays loaded. Switching conversations resets the KV state and restores recent messages through a bounded system-prompt transcript. This is not exact KV serialization or role-preserving chat-template replay.

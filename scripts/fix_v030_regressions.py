#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
cpp = root / "vendor/llama.cpp/examples/llama.android/lib/src/main/cpp/ai_chat.cpp"

if not main.exists():
    raise SystemExit("generated MainActivity.kt is missing")
if not cpp.exists():
    raise SystemExit("patched llama.cpp ai_chat.cpp is missing")

# MaterialSwitch was the only new widget on the settings-dialog path in v0.3.0.
# Use the long-established AppCompat switch instead; it does not depend on the
# MaterialSwitch-specific theme/style machinery at runtime.
main_text = main.read_text()
old_import = "import com.google.android.material.materialswitch.MaterialSwitch\n"
new_import = "import androidx.appcompat.widget.SwitchCompat\n"
if old_import not in main_text:
    raise SystemExit("MaterialSwitch import not found in generated MainActivity")
main_text = main_text.replace(old_import, new_import, 1)

old_switch = "        val thinkingSwitch = MaterialSwitch(this).apply {"
new_switch = "        val thinkingSwitch = SwitchCompat(this).apply {"
if old_switch not in main_text:
    raise SystemExit("MaterialSwitch construction not found in generated MainActivity")
main_text = main_text.replace(old_switch, new_switch, 1)
main.write_text(main_text)

# v0.3.0 enabled the Jinja thinking path for every message role. Qwen3.5's
# template deliberately raises when there is no user query, which is exactly the
# state while AndroidLLM is formatting the initial system prompt during model
# loading. Keep the original/legacy formatting for system + assistant turns and
# use the Jinja enable_thinking path only when formatting an actual user turn.
cpp_text = cpp.read_text()
old_jinja = "    const bool use_jinja = common_chat_templates_support_enable_thinking(g_chat_templates.get());"
new_jinja = "    const bool use_jinja = role == ROLE_USER && common_chat_templates_support_enable_thinking(g_chat_templates.get());"
if old_jinja not in cpp_text:
    raise SystemExit("v0.3 Jinja selection line not found in generated ai_chat.cpp")
cpp_text = cpp_text.replace(old_jinja, new_jinja, 1)
cpp.write_text(cpp_text)

# Build-time regression guards. These intentionally fail CI if a future patch
# silently restores either crash path.
assert "MaterialSwitch(this)" not in main.read_text()
assert "SwitchCompat(this)" in main.read_text()
assert new_jinja in cpp.read_text()

print("v0.3 runtime regressions patched: safe settings switch + user-only thinking Jinja")

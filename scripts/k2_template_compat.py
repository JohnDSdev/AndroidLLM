#!/usr/bin/env python3
"""Make GGUF custom/Jinja templates safe in the Android llama.cpp binding.

K2 Horizon GGUFs require Jinja. Previous AndroidLLM compatibility code
always chose the legacy formatter for the system role, and retried legacy
formatting after any exception, causing an uncaught C++ exception/SIGABRT.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cpp = root / "vendor/llama.cpp/examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
impl = root / "vendor/llama.cpp/examples/llama.android/lib/src/main/java/com/arm/aichat/internal/InferenceEngineImpl.kt"
code = cpp.read_text()

def replace_once(old: str, new: str):
    global code
    count = code.count(old)
    if count != 1:
        raise SystemExit(f"Expected one instance of {old[:95]!r}, found {count}")
    code = code.replace(old, new, 1)

replace_once(
    "static std::string                        g_last_native_error;",
    "static std::string                        g_last_native_error;\n"
    "static bool                               g_chat_template_error = false;",
)

old = '''    std::string formatted;
    try {
        const bool use_jinja = role == ROLE_USER && common_chat_templates_support_enable_thinking(g_chat_templates.get());
        formatted = common_chat_format_single(
                g_chat_templates.get(), chat_msgs, new_msg, role == ROLE_USER, use_jinja, enable_thinking);
    } catch (const std::exception &e) {
        LOGw("Thinking-aware chat template failed (%s); falling back to legacy formatting", e.what());
        formatted = common_chat_format_single(
                g_chat_templates.get(), chat_msgs, new_msg, role == ROLE_USER, /* use_jinja */ false, true);
    }'''
new = '''    // Keep the legacy Qwen system-prompt path; some Qwen Jinja templates
    // reject a conversation with no user turn. Custom GGUFs such as K2 Horizon
    // need Jinja even for system messages, so retry the opposite formatter.
    bool preferred_jinja = false;
    if (role == ROLE_USER) {
        try {
            preferred_jinja = common_chat_templates_support_enable_thinking(g_chat_templates.get());
        } catch (const std::exception &e) {
            LOGw("Could not inspect chat-template thinking support: %s", e.what());
        }
    }
    std::string formatted;
    bool formatted_ok = false;
    std::string template_error;
    for (const bool use_jinja : {preferred_jinja, !preferred_jinja}) {
        try {
            formatted = common_chat_format_single(
                    g_chat_templates.get(), chat_msgs, new_msg, role == ROLE_USER, use_jinja, enable_thinking);
            formatted_ok = true;
            break;
        } catch (const std::exception &e) {
            template_error = e.what();
            LOGw("GGUF chat-template attempt (jinja=%d) failed: %s", use_jinja, e.what());
        }
    }
    if (!formatted_ok) {
        g_chat_template_error = true;
        g_last_native_error = "GGUF chat template could not be formatted: " + template_error;
        LOGe("%s", g_last_native_error.c_str());
        return "";
    }'''
replace_once(old, new)

# Mark a formatting failure as a recoverable JNI status, not a process-fatal
# uncaught C++ exception. The caller releases the Java UTF string before returning.
replace_once(
    '''    // Reset long-term & short-term states
    reset_long_term_states();''',
    '''    // Reset long-term & short-term states
    g_chat_template_error = false;
    reset_long_term_states();''',
)
replace_once(
    '''        formatted_system_prompt = chat_add_and_format(ROLE_SYSTEM, system_prompt);
    }
    env->ReleaseStringUTFChars(jsystem_prompt, system_prompt);''',
    '''        formatted_system_prompt = chat_add_and_format(ROLE_SYSTEM, system_prompt);
    }
    if (g_chat_template_error) {
        env->ReleaseStringUTFChars(jsystem_prompt, system_prompt);
        return 3;
    }
    env->ReleaseStringUTFChars(jsystem_prompt, system_prompt);''',
)
replace_once(
    '''        formatted_user_prompt = chat_add_and_format(ROLE_USER, user_prompt, jenable_thinking == JNI_TRUE);
    }
    env->ReleaseStringUTFChars(juser_prompt, user_prompt);''',
    '''        formatted_user_prompt = chat_add_and_format(ROLE_USER, user_prompt, jenable_thinking == JNI_TRUE);
    }
    if (g_chat_template_error) {
        env->ReleaseStringUTFChars(juser_prompt, user_prompt);
        return 3;
    }
    env->ReleaseStringUTFChars(juser_prompt, user_prompt);''',
)
cpp.write_text(code)

text = impl.read_text()
old_error = 'RuntimeException("Failed to process system prompt: $result")'
if text.count(old_error) != 1:
    raise SystemExit("Expected upstream Kotlin system prompt error handler")
text = text.replace(old_error,
    'RuntimeException("Failed to process system prompt ($result): ${lastNativeError().take(500)}")', 1)
impl.write_text(text)

assert 'for (const bool use_jinja : {preferred_jinja, !preferred_jinja})' in cpp.read_text()
assert 'return 3;' in cpp.read_text()
print("Custom GGUF Jinja compatibility: legacy-first for Qwen system, Jinja fallback for K2, recoverable errors")

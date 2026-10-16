#!/usr/bin/env python3
"""Adapt the older AndroidLLM streaming patches to llama.cpp b11454's common_batch API.

Several existing patches deliberately replace chunks of ai_chat.cpp with the pre-b11454
llama_batch helpers. The upstream Android binding now keeps g_batch as common_batch.
Run this after the other patch scripts so the final translation unit is consistent.
"""
from pathlib import Path

cpp = Path(__file__).resolve().parents[1] / "vendor/llama.cpp/examples/llama.android/lib/src/main/cpp/ai_chat.cpp"
source = cpp.read_text()

def replace_exact(old: str, new: str) -> None:
    global source
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one batch API occurrence ({count}): {old!r}")
    source = source.replace(old, new, 1)

replace_exact(
    "g_batch = llama_batch_init(g_batch_size, 0, 1);",
    "g_batch = common_batch(g_context);",
)
replace_exact(
    "        llama_batch &batch,",
    "        common_batch &batch,",
)
replace_exact(
    "        common_batch_clear(batch);",
    "        batch.clear();",
)
replace_exact(
    "            common_batch_add(batch, token_id, position, {0}, want_logit);",
    "            batch.add(token_id, position, 0, want_logit);",
)
replace_exact(
    "        const int decode_result = llama_decode(context, batch);",
    "        const int decode_result = llama_process(context, LLAMA_PROCESS_TYPE_DECODE, batch.get());",
)
replace_exact(
    "    llama_batch_free(g_batch);",
    "    g_batch = common_batch();",
)

for unsupported in ("llama_batch_init(", "common_batch_clear(", "common_batch_add(", "llama_batch_free("):
    if unsupported in source:
        raise SystemExit(f"Obsolete batch API still present: {unsupported}")
cpp.write_text(source)
print("Updated Android native batch initialization, token decode, and teardown for common_batch")

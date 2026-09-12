#!/usr/bin/env python3
"""Final patch after v0.7.6 generation; keep baseline scripts reproducible."""
from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[1]
subprocess.run(['git', 'apply', '--whitespace=nowarn', str(root / 'patches/inference-search-scroll.patch')], cwd=root, check=True)
p = root / 'vendor/llama.cpp/ggml/src/ggml-cpu/repack.cpp'
s = p.read_text()
old = '    if (ggml_n_dims(cur) > 2) return nullptr;'
assert s.count(old) == 1
s = '#include <cstdlib>\n' + s.replace(old, '''    const char * expert_repack = std::getenv("ANDROIDLLM_REPACK_EXPERTS");
    if (ggml_n_dims(cur) > 2 && expert_repack && expert_repack[0] == '0') return nullptr;''')
p.write_text(s)
print('v0.7.7: selectable optimized MoE kernels, anchored streaming, opt-in model web search')

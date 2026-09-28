#!/usr/bin/env python3
"""Check effective compiler commands, not just requested Gradle options."""
import json
import shlex
from pathlib import Path
files = list(Path('vendor/llama.cpp/examples/llama.android/lib/.cxx').rglob('compile_commands.json'))
commands = []
for file in files:
    for entry in json.loads(file.read_text()):
        if 'ggml-cpu' in entry['file'] and entry['file'].endswith(('quants.c', 'repack.cpp')):
            argv = entry.get('arguments') or shlex.split(entry['command'])
            if '--target=aarch64' in ' '.join(argv):
                commands.append(argv)
assert commands, 'No ARM quantization/repacking compile commands found'
for argv in commands:
    assert '-march=armv8.6-a+dotprod+fp16+i8mm' in argv, argv
    opts = [a for a in argv if a.startswith('-O')]
    assert opts and opts[-1] in ('-O3', '-O2'), opts
print(f'Verified optimized ARM quantization/repacking in {len(commands)} compiler commands')

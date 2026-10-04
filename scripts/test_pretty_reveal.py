#!/usr/bin/env python3
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
    subprocess.run(['javac', '-d', temp, str(root/'app/src/main/java/com/johndsdev/androidllm/PrettyTextReveal.java'), str(root/'tests/PrettyTextRevealTest.java')], check=True)
    subprocess.run(['java', '-cp', temp, 'PrettyTextRevealTest'], check=True)

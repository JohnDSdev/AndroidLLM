#!/usr/bin/env python3
"""Apply the reviewed Android binding to the exact upstream revision, idempotently."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LLAMA = ROOT / "vendor/llama.cpp"
REVISION = "b95502ba9aa0eb73a2f4fc8878d7fbe6a847a0b9"  # b10516
PATCH = ROOT / "patches/android-binding.patch"


def git(*args, **kwargs):
    return subprocess.run(["git", "-C", str(LLAMA), *args], **kwargs)


if __name__ == "__main__":
    revision = git("rev-parse", "HEAD", capture_output=True, text=True, check=True).stdout.strip()
    if revision != REVISION:
        raise SystemExit(f"Expected llama.cpp {REVISION}, found {revision}")
    if git("apply", "--reverse", "--check", str(PATCH), capture_output=True).returncode == 0:
        print("Android binding already prepared")
    else:
        git("apply", "--check", str(PATCH), check=True)
        git("apply", str(PATCH), check=True)
        print("Android binding prepared; app sources are built directly")

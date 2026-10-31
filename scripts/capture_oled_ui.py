#!/usr/bin/env python3
"""Capture real AndroidLLM OLED emulator screenshots for both display modes."""
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path("ui-screenshots")
OUT.mkdir(exist_ok=True)
PKG = "com.johndsdev.androidllm.oled"
ACTIVITY = "com.johndsdev.androidllm.MainActivity"

def adb(*args, capture=False):
    result = subprocess.run(["adb", *args], check=True, stdout=subprocess.PIPE if capture else None, text=True)
    return result.stdout if capture else ""

def tap_by_text(match):
    for attempt in range(6):
        try:
            adb("shell", "uiautomator", "dump", "/sdcard/uidump.xml")
            xml = adb("shell", "cat", "/sdcard/uidump.xml", capture=True)
            root = ET.fromstring(xml)
            for el in root.iter("node"):
                if match(el.attrib):
                    m = re.match(r"\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]", el.get("bounds", ""))
                    if m:
                        x1,y1,x2,y2 = map(int,m.groups())
                        adb("shell", "input", "tap", str((x1+x2)//2), str((y1+y2)//2))
                        time.sleep(1.3)
                        return True
        except Exception as exc:
            print("UI dump attempt failed:", exc, flush=True)
        time.sleep(1.5)
    return False

adb("shell", "am", "start", "-n", f"{PKG}/{ACTIVITY}")
time.sleep(6)
adb("exec-out", "screencap", "-p", capture=False) if False else None
with (OUT / "oled-black.png").open("wb") as f:
    subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=f, check=True)

if not tap_by_text(lambda a: a.get("content-desc") == "Chats"):
    raise RuntimeError("Cannot open drawer; Chats control not found")

with (OUT / "oled-sidebar.png").open("wb") as f:
    subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=f, check=True)

if not tap_by_text(lambda a: a.get("text", "").startswith("Aurora background")):
    raise RuntimeError("Aurora toggle missing from drawer")

# Close the slide-out drawer, exposing the actual gradient background.
adb("shell", "input", "keyevent", "4")
time.sleep(2)
with (OUT / "oled-aurora.png").open("wb") as f:
    subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=f, check=True)

for p in sorted(OUT.iterdir()):
    print(f"Screenshot captured: {p} ({p.stat().st_size} bytes)", flush=True)

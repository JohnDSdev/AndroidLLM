#!/usr/bin/env python3
"""Make the completed OLED app the regular AndroidLLM release; no tuning experiments."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
gradle=root/"app/build.gradle.kts"
manifest=root/"app/src/main/AndroidManifest.xml"
s=gradle.read_text()
needle='applicationIdSuffix = ".oled"\n'
if needle not in s: raise SystemExit("Cannot find experimental app ID suffix")
s=s.replace(needle,"",1)
s=re.sub(r'versionCode = \d+', 'versionCode = 104', s,count=1)
s=re.sub(r'versionName = "[^"]+"', 'versionName = "0.8.4-oled"',s,count=1)
gradle.write_text(s)
m=manifest.read_text()
if 'android:label="AndroidLLM OLED"' not in m: raise SystemExit("App label missing")
manifest.write_text(m.replace('android:label="AndroidLLM OLED"','android:label="AndroidLLM"'))
assert 'applicationIdSuffix = ".oled"' not in gradle.read_text()
print("Standard OLED package: com.johndsdev.androidllm")

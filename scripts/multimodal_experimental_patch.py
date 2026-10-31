#!/usr/bin/env python3
"""Experimental CPU-only libmtmd and multimodal Android screen."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
vendor=root/"vendor/llama.cpp"
cppdir=vendor/"examples/llama.android/lib/src/main/cpp"
(cppdir/"omni_bridge.cpp").write_text((root/"scripts/omni_bridge.cpp").read_text())
cmake=cppdir/"CMakeLists.txt"
s=cmake.read_text()
needle='''add_library(${CMAKE_PROJECT_NAME} SHARED
        ai_chat.cpp)'''
if needle not in s: raise SystemExit("Android native library anchor changed")
s=s.replace(needle,'''add_library(${CMAKE_PROJECT_NAME} SHARED
        ai_chat.cpp
        omni_bridge.cpp)''',1)
needle='''        ${LLAMA_SRC}/ggml/src)'''
if needle not in s: raise SystemExit("Native include block changed")
s=s.replace(needle,'''        ${LLAMA_SRC}/ggml/src
        ${LLAMA_SRC}/tools/mtmd)''',1)
needle='''        llama-common
        android'''
if needle not in s: raise SystemExit("Native link block changed")
s=s.replace(needle,'''        llama-common
        mtmd
        android''',1)
cmake.write_text(s)
ng=vendor/"examples/llama.android/lib/build.gradle.kts"
s=ng.read_text()
needle='''arguments += "-DLLAMA_BUILD_COMMON=ON"'''
if needle not in s: raise SystemExit("CMake argument anchor changed")
s=s.replace(needle,needle+'''
                arguments += "-DLLAMA_BUILD_MTMD=ON"
                arguments += "-DMTMD_VIDEO=OFF"''',1)
ng.write_text(s)
manifest=root/"app/src/main/AndroidManifest.xml"
s=manifest.read_text()
needle='''    <uses-permission android:name="android.permission.INTERNET" />'''
if needle not in s: raise SystemExit("Manifest permissions changed")
s=s.replace(needle,needle+'''
    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    <uses-feature android:name="android.hardware.microphone" android:required="false" />''',1)
needle='''        <activity
            android:name=".MainActivity"'''
if needle not in s: raise SystemExit("Manifest activity changed")
s=s.replace(needle,'''        <activity android:name=".MultimodalActivity" android:exported="false" />
'''+needle,1)
ET.fromstring(s)
manifest.write_text(s)
layout=root/"app/src/main/res/layout/activity_main.xml"
s=layout.read_text()
needle='''        <TextView
            android:id="@+id/drawerSettingsButton"'''
if needle not in s: raise SystemExit("Drawer settings view missing")
s=s.replace(needle,'''        <TextView
            android:id="@+id/drawerMultimodalButton"
            android:layout_width="match_parent"
            android:layout_height="54dp"
            android:gravity="center_vertical"
            android:paddingStart="12dp"
            android:paddingEnd="12dp"
            android:text="Multimodal lab"
            android:textColor="@color/text_primary"
            android:textSize="15sp" />

'''+needle,1)
ET.fromstring(s)
layout.write_text(s)
main=root/"app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
s=main.read_text()
needle='''        findViewById<View>(R.id.drawerSettingsButton).setOnClickListener {'''
if needle not in s: raise SystemExit("Drawer settings click listener missing")
s=s.replace(needle,'''        findViewById<View>(R.id.drawerMultimodalButton).setOnClickListener {
            drawerLayout.closeDrawer(GravityCompat.START)
            startActivity(android.content.Intent(this, MultimodalActivity::class.java))
        }
'''+needle,1)
main.write_text(s)
gradle=root/"app/build.gradle.kts"
s=gradle.read_text()
s=re.sub(r'versionCode = \d+','versionCode = 107',s,count=1)
s=re.sub(r'versionName = "[^"]+"','versionName = "1.0.0-multimodal-experimental"',s,count=1)
gradle.write_text(s)
assert 'mtmd' in cmake.read_text()
assert 'LLAMA_BUILD_MTMD=ON' in ng.read_text()
assert 'RECORD_AUDIO' in manifest.read_text()
assert 'MultimodalActivity' in manifest.read_text()
assert 'MultimodalBridge.infer(' in (root/"app/src/main/java/com/johndsdev/androidllm/MultimodalActivity.kt").read_text()
print("Multimodal Lab linked: libmtmd JNI, local image/audio, mic WAV and spoken output")

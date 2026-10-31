#!/usr/bin/env python3
"""OLED UI polish + HF model browser + experimental Omni-native audio codec."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
layout=root/"app/src/main/res/layout/activity_main.xml"
main=root/"app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
manifest=root/"app/src/main/AndroidManifest.xml"
theme=root/"app/src/main/res/values/themes.xml"
gradle=root/"app/build.gradle.kts"

# Enable model-native Omni speech in same JNI library as image/audio input.
cpp=root/"vendor/llama.cpp/examples/llama.android/lib/src/main/cpp"
(cpp/"omni_native_tts.cpp").write_text((root/"scripts/omni_native_tts.cpp").read_text())
cmake=cpp/"CMakeLists.txt"
s=cmake.read_text()
if "        omni_bridge.cpp)" not in s:raise SystemExit("Native bridge module not found")
s=s.replace("        omni_bridge.cpp)", "        omni_bridge.cpp\n        omni_native_tts.cpp)",1)
cmake.write_text(s)

# The model browser is not exported to other applications.
m=manifest.read_text()
needle='''        <activity android:name=".MultimodalActivity" android:exported="false" />'''
if needle not in m:raise SystemExit("Multimodal activity missing in manifest")
m=m.replace(needle,needle+'''
        <activity android:name=".HuggingFaceBrowserActivity" android:exported="false" />''',1)
ET.fromstring(m)
manifest.write_text(m)

# Consistent app-wide rounded dark Material dialogs, not platform square popups.
t=theme.read_text()
anchor='''    <style name="ThemeOverlay.AndroidLLM.AlertDialog" parent="ThemeOverlay.MaterialComponents.MaterialAlertDialog">'''
if anchor not in t:raise SystemExit("Existing dialog style missing")
t=t.replace(anchor,anchor+'''
        <item name="shapeAppearanceOverlay">@style/ShapeAppearanceOverlay.AndroidLLM.Dialog</item>
        <item name="backgroundTint">@color/surface_elevated</item>
        <item name="android:windowBackground">@drawable/androidllm_dialog_background</item>''',1)
t=t.replace("</resources>",'''    <style name="ShapeAppearanceOverlay.AndroidLLM.Dialog" parent="">
        <item name="cornerFamily">rounded</item>
        <item name="cornerSize">24dp</item>
    </style>
</resources>''')
ET.fromstring(t)
theme.write_text(t)
drawable=root/"app/src/main/res/drawable/androidllm_dialog_background.xml"
drawable.write_text('''<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#232323"/>
    <corners android:radius="24dp"/>
    <stroke android:width="1dp" android:color="#4B4B4B"/>
</shape>
''')

x=layout.read_text()
label_at=x.index('android:text="Android LLM"', x.index('android:id="@+id/chatDrawer"'))
view_start=x.rfind('        <TextView',0,label_at)
view_end=x.index('/>',label_at)+2
if view_start<0 or view_end<=view_start:raise SystemExit("Drawer header title not found")
title='''        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="54dp"
            android:orientation="horizontal"
            android:gravity="center_vertical"
            android:paddingStart="8dp"
            android:paddingEnd="8dp">

            <TextView
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_weight="1"
                android:gravity="center_vertical"
                android:text="Android LLM"
                android:textColor="@color/text_primary"
                android:textSize="24sp"
                android:textStyle="bold"/>

            <ImageButton
                android:id="@+id/drawerSettingsGear"
                android:layout_width="48dp"
                android:layout_height="48dp"
                android:background="@drawable/androidllm_gear_background"
                android:contentDescription="Open settings"
                android:src="@drawable/ic_settings_gear"
                android:scaleType="centerInside"
                android:padding="12dp"/>
        </LinearLayout>'''
x=x[:view_start]+title+x[view_end:]
for view in ["gradientModeButton","drawerOptimizeButton","drawerMultimodalButton","drawerSettingsButton","drawerExportButton"]:
    pat=r'(<TextView\s+android:id="@\+id/'+view+r'"[\s\S]*?)(\s*/>)'
    x,n=re.subn(pat,lambda m:m.group(1)+'\n            android:visibility="gone"'+m.group(2),x,count=1)
    if n!=1:raise SystemExit("Drawer setting row missing: "+view)
ET.fromstring(x)
layout.write_text(x)

(root/"app/src/main/res/drawable/androidllm_gear_background.xml").write_text('''<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#282828"/>
    <corners android:radius="17dp"/>
    <stroke android:width="1dp" android:color="#474747"/>
</shape>''')
(root/"app/src/main/res/drawable/ic_settings_gear.xml").write_text('''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path android:fillColor="@android:color/transparent"
        android:strokeColor="#F0F0F0" android:strokeWidth="1.9"
        android:strokeLineCap="round" android:strokeLineJoin="round"
        android:pathData="M10,2 L14,2 L14.7,4.3 L16.5,5.1 L18.7,4 L21,6.3 L19.9,8.5 L20.7,10.3 L23,11 L23,13 L20.7,13.7 L19.9,15.5 L21,17.7 L18.7,20 L16.5,18.9 L14.7,19.7 L14,22 L10,22 L9.3,19.7 L7.5,18.9 L5.3,20 L3,17.7 L4.1,15.5 L3.3,13.7 L1,13 L1,11 L3.3,10.3 L4.1,8.5 L3,6.3 L5.3,4 L7.5,5.1 L9.3,4.3 Z M12,8 A4,4 0,1 1,11.999,8"/>
</vector>''')

k=main.read_text()
nav='''        findViewById<View>(R.id.drawerSettingsButton).setOnClickListener {'''
if k.count(nav)!=1:raise SystemExit("Drawer settings listener missing")
k=k.replace(nav,'''        findViewById<View>(R.id.drawerSettingsGear).setOnClickListener {
            drawerLayout.closeDrawer(GravityCompat.START)
            showSettingsHub()
        }
'''+nav,1)

method='''    private fun showSettingsDialog() {'''
if method not in k:raise SystemExit("Settings method missing")
hub='''    private fun showSettingsHub() {
        val wrapper = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(8), dp(18), dp(18))
        }
        lateinit var dialog: androidx.appcompat.app.AlertDialog
        fun addOption(title: String, description: String, action: () -> Unit) {
            val card = com.google.android.material.card.MaterialCardView(this).apply {
                radius = dp(19).toFloat()
                strokeWidth = dp(1)
                strokeColor = color(R.color.divider)
                cardElevation = 0f
                setCardBackgroundColor(color(R.color.surface_alt))
                isClickable = true
                isFocusable = true
            }
            val item = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(17), dp(12), dp(14), dp(12))
            }
            item.addView(TextView(this).apply {
                text = title
                textSize = 16f
                typeface = android.graphics.Typeface.DEFAULT_BOLD
                setTextColor(color(R.color.text_primary))
            })
            item.addView(TextView(this).apply {
                text = description
                textSize = 12f
                setPadding(0, dp(3), 0, 0)
                setTextColor(color(R.color.text_secondary))
            })
            card.addView(item)
            card.setOnClickListener { dialog.dismiss(); action() }
            wrapper.addView(card, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(10) })
        }
        addOption("Model & generation settings", "Threads, context, sampling and reasoning") {
            showSettingsDialog()
        }
        addOption("Aurora background", if (auroraEnabled) "Currently on · tap to disable" else "Currently off · tap to enable") {
            gradientModeButton.performClick()
        }
        addOption("Optimize model", "Thermal-aware CPU benchmark and best settings") {
            openModelOptimizer()
        }
        addOption("Multimodal lab", "Images, microphone and LFM3 Omni native voice") {
            startActivity(android.content.Intent(this, MultimodalActivity::class.java))
        }
        addOption("Export data", "Save chats and settings to a ZIP") {
            exportLauncher.launch("AndroidLLM-export.zip")
        }
        dialog = com.google.android.material.dialog.MaterialAlertDialogBuilder(this)
            .setTitle("Settings")
            .setView(ScrollView(this).apply { addView(wrapper) })
            .setNegativeButton("Close", null)
            .create()
        dialog.show()
        dialog.window?.setBackgroundDrawableResource(R.drawable.androidllm_dialog_background)
    }

'''
k=k.replace(method,hub+method,1)
model_anchor='''        val downloadButton = MaterialButton(this).apply {'''
if model_anchor not in k:raise SystemExit("Model dialog download control missing")
k=k.replace(model_anchor,'''        val browseButton = MaterialButton(this).apply {
            text = "Search Hugging Face · Choose GGUF & quant"
            isAllCaps = false
            cornerRadius = dp(17)
            strokeWidth = dp(1)
            strokeColor = android.content.res.ColorStateList.valueOf(color(R.color.divider))
            setOnClickListener {
                currentModelDialog?.dismiss()
                startActivity(android.content.Intent(this@MainActivity,
                    HuggingFaceBrowserActivity::class.java))
            }
        }
        box.addView(browseButton, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { bottomMargin = dp(10) })

'''+model_anchor,1)
main.write_text(k)

hf=root/"app/src/main/java/com/johndsdev/androidllm/HuggingFaceBrowserActivity.kt"
s=hf.read_text()
needle='''        backgroundTintList=android.content.res.ColorStateList.valueOf(0xff292929.toInt())'''
if needle not in s:raise SystemExit("HF button style anchor missing")
s=s.replace(needle,'''        backgroundTintList=null
        background=android.graphics.drawable.GradientDrawable().apply{
            setColor(0xff292929.toInt())
            cornerRadius=dp(18).toFloat()
            setStroke(dp(1),0xff4B4B4B.toInt())
        }
        setPadding(dp(12),dp(8),dp(12),dp(8))''',1)
hf.write_text(s)

g=gradle.read_text()
g=re.sub(r'versionCode = \d+','versionCode = 108',g,count=1)
g=re.sub(r'versionName = "[^"]+"','versionName = "1.1.0-omni-voice-hf-experimental"',g,count=1)
gradle.write_text(g)
print("v1.1: rounded settings hub and dialogs, HF model search, native Omni speech link")

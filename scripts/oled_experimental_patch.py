#!/usr/bin/env python3
"""Experimental OLED/aurora UI layer. Applied after all inference/UX patches."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
res = root / "app/src/main/res"
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
gradle = root / "app/build.gradle.kts"

# OLED-first palette.  The aurora effect is an opt-in translucent overlay.
colors = {
    "app_background": "#000000",
    "surface": "#171717",
    "surface_alt": "#262626",
    "surface_elevated": "#1D1D1D",
    "text_primary": "#F4F4F4",
    "text_secondary": "#AAAAAA",
    "accent": "#F7F7F7",
    "accent_on": "#111111",
    "accent_soft": "#292929",
    "divider": "#303030",
    "danger": "#FF7777",
    "user_bubble": "#262626",
    "user_text": "#F5F5F5",
    "assistant_bubble": "#000000",
    "assistant_text": "#F3F3F3",
    "chip_background": "#202020",
}
palette = res / "values/colors.xml"
s = palette.read_text()
for key, value in colors.items():
    s, n = re.subn(r'(<color name="' + key + r'">)[^<]*(</color>)',
                   lambda m: m.group(1) + value + m.group(2), s)
    if n != 1:
        raise SystemExit("Missing palette entry " + key)
palette.write_text(s)

layout = res / "layout/activity_main.xml"
xml = layout.read_text()
start = xml.find('    <LinearLayout\n        android:id="@+id/chatDrawer"')
end = xml.rfind('</androidx.drawerlayout.widget.DrawerLayout>')
if start < 0 or end < 0:
    raise SystemExit("Drawer layout boundary not found")

drawer = '''    <LinearLayout
        android:id="@+id/chatDrawer"
        android:layout_width="326dp"
        android:layout_height="match_parent"
        android:layout_gravity="start"
        android:background="@color/surface"
        android:fitsSystemWindows="true"
        android:orientation="vertical"
        android:paddingStart="16dp"
        android:paddingTop="18dp"
        android:paddingEnd="16dp"
        android:paddingBottom="16dp">

        <TextView
            android:layout_width="match_parent"
            android:layout_height="52dp"
            android:gravity="center_vertical"
            android:paddingStart="8dp"
            android:text="Android LLM"
            android:textColor="@color/text_primary"
            android:textSize="24sp"
            android:textStyle="bold" />

        <com.google.android.material.button.MaterialButton
            android:id="@+id/drawerNewChatButton"
            android:layout_width="match_parent"
            android:layout_height="52dp"
            android:layout_marginTop="12dp"
            android:layout_marginBottom="12dp"
            android:text="+   New chat"
            android:textAllCaps="false"
            android:textColor="@color/text_primary"
            android:textSize="15sp"
            app:backgroundTint="@color/surface_alt"
            app:cornerRadius="18dp"
            app:strokeWidth="0dp" />

        <EditText
            android:id="@+id/drawerSearch"
            android:layout_width="match_parent"
            android:layout_height="46dp"
            android:hint="Search chats"
            android:singleLine="true"
            android:imeOptions="actionSearch"
            android:inputType="text"
            android:paddingStart="16dp"
            android:paddingEnd="12dp"
            android:textColor="@color/text_primary"
            android:textColorHint="@color/text_secondary"
            android:textSize="14sp" />

        <TextView
            android:layout_width="match_parent"
            android:layout_height="44dp"
            android:gravity="bottom"
            android:paddingStart="9dp"
            android:paddingBottom="11dp"
            android:text="Recent"
            android:textColor="@color/text_secondary"
            android:textSize="13sp"
            android:textStyle="bold" />

        <ScrollView
            android:layout_width="match_parent"
            android:layout_height="0dp"
            android:layout_weight="1"
            android:clipToPadding="false"
            android:overScrollMode="never">

            <LinearLayout
                android:id="@+id/drawerChatList"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="vertical" />
        </ScrollView>

        <View
            android:layout_width="match_parent"
            android:layout_height="1dp"
            android:layout_marginTop="10dp"
            android:layout_marginBottom="10dp"
            android:background="@color/divider" />

        <TextView
            android:id="@+id/gradientModeButton"
            android:layout_width="match_parent"
            android:layout_height="54dp"
            android:contentDescription="Toggle aurora background"
            android:gravity="center_vertical"
            android:paddingStart="12dp"
            android:paddingEnd="12dp"
            android:text="Aurora background   Off"
            android:textColor="@color/text_primary"
            android:textSize="15sp" />

        <TextView
            android:id="@+id/drawerSettingsButton"
            android:layout_width="match_parent"
            android:layout_height="54dp"
            android:gravity="center_vertical"
            android:paddingStart="12dp"
            android:paddingEnd="12dp"
            android:text="Settings &amp; models"
            android:textColor="@color/text_primary"
            android:textSize="15sp" />

        <TextView
            android:layout_width="match_parent"
            android:layout_height="34dp"
            android:gravity="center_vertical"
            android:paddingStart="12dp"
            android:text="PRIVATE  ·  ON-DEVICE"
            android:textColor="@color/text_secondary"
            android:textSize="10sp"
            android:letterSpacing="0.10" />
    </LinearLayout>
'''
xml = xml[:start] + drawer + xml[end:]
xml = xml.replace('android:layout_height="60dp"', 'android:layout_height="64dp"', 1)
ET.fromstring(xml)
layout.write_text(xml)

src = main.read_text()
def replace_once(old, new):
    global src
    if old not in src:
        raise SystemExit("UI patch anchor missing: " + old[:100])
    src = src.replace(old, new, 1)

replace_once("import android.graphics.Typeface\n",
    """import android.graphics.Typeface
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.RadialGradient
import android.graphics.Shader
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.text.Editable
import android.text.TextWatcher
""")

replace_once("    private lateinit var menuButton: ImageButton\n",
"""    private lateinit var menuButton: ImageButton
    private lateinit var drawerSearch: EditText
    private lateinit var gradientModeButton: TextView
    private var auroraEnabled = false
""")

anchor = "        drawerNewChatButton = findViewById(R.id.drawerNewChatButton)\n"
replace_once(anchor, anchor + """        drawerSearch = findViewById(R.id.drawerSearch)
        gradientModeButton = findViewById(R.id.gradientModeButton)
        auroraEnabled = getSharedPreferences("oled_ui", MODE_PRIVATE).getBoolean("aurora", false)
        drawerSearch.background = GradientDrawable().apply {
            setColor(Color.rgb(39, 39, 39))
            cornerRadius = dp(14).toFloat()
        }
        drawerLayout.setScrimColor(Color.argb(190, 0, 0, 0))
        drawerLayout.setDrawerElevation(0f)
        applyAurora()
        drawerSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                renderChatDrawer()
            }
            override fun afterTextChanged(s: Editable?) {}
        })
        gradientModeButton.setOnClickListener {
            auroraEnabled = !auroraEnabled
            getSharedPreferences("oled_ui", MODE_PRIVATE).edit().putBoolean("aurora", auroraEnabled).apply()
            applyAurora()
        }
        findViewById<View>(R.id.drawerSettingsButton).setOnClickListener {
            drawerLayout.closeDrawer(GravityCompat.START)
            menuButton.performClick()
        }
""")

# Replace the grid of chunky cards and always-visible "Delete" buttons.
start_marker = "    private fun renderChatDrawer() {"
end_marker = "    private fun confirmDeleteChat("
a = src.find(start_marker)
b = src.find(end_marker, a)
if a < 0 or b < 0:
    raise SystemExit("renderChatDrawer boundary not found")
src = src[:a] + '''    private fun renderChatDrawer() {
        drawerChatList.removeAllViews()
        val filter = drawerSearch.text?.toString()?.trim().orEmpty()
        val chats = store.chats.filter { it.title.contains(filter, ignoreCase = true) }
        if (chats.isEmpty()) {
            drawerChatList.addView(TextView(this).apply {
                text = if (filter.isEmpty()) "No chats yet" else "No matching chats"
                textSize = 14f
                setTextColor(color(R.color.text_secondary))
                setPadding(dp(12), dp(18), 0, 0)
            })
        }
        chats.forEach { chat ->
            val selected = chat.id == store.currentChatId
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                minimumHeight = dp(55)
                setPadding(dp(14), dp(4), dp(6), dp(4))
                background = GradientDrawable().apply {
                    setColor(if (selected) Color.rgb(48, 48, 48) else Color.TRANSPARENT)
                    cornerRadius = dp(13).toFloat()
                }
                isClickable = true
                isFocusable = true
                setOnClickListener {
                    if (!busy) {
                        store.selectChat(chat.id)
                        invalidateLoadedConversation()
                        drawerLayout.closeDrawer(GravityCompat.START)
                        renderAll()
                    }
                }
            }
            row.addView(TextView(this).apply {
                text = chat.title
                textSize = 15f
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
                setTextColor(color(R.color.text_primary))
                if (selected) typeface = Typeface.DEFAULT_BOLD
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            row.addView(TextView(this).apply {
                text = "⋯"
                textSize = 24f
                gravity = Gravity.CENTER
                setTextColor(color(R.color.text_secondary))
                contentDescription = "Delete " + chat.title
                setOnClickListener {
                    if (!busy) confirmDeleteChat(chat.id, chat.title)
                }
            }, LinearLayout.LayoutParams(dp(42), dp(42)))
            drawerChatList.addView(row, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(3) })
        }
    }

    private fun applyAurora() {
        val mainRoot = findViewById<View>(R.id.root)
        mainRoot.background = if (auroraEnabled) AuroraDrawable() else ColorDrawable(Color.BLACK)
        window.statusBarColor = Color.BLACK
        window.navigationBarColor = Color.BLACK
        gradientModeButton.text = if (auroraEnabled) "Aurora background      On   ✦" else "Aurora background      Off   ○"
    }

    private class AuroraDrawable : Drawable() {
        private val p = Paint(Paint.ANTI_ALIAS_FLAG)
        override fun draw(canvas: Canvas) {
            val w = bounds.width().toFloat()
            val h = bounds.height().toFloat()
            canvas.drawColor(Color.BLACK)
            fun bloom(x: Float, y: Float, r: Float, center: Int) {
                p.shader = RadialGradient(x, y, r,
                    intArrayOf(center, center and 0x00FFFFFF, Color.TRANSPARENT),
                    floatArrayOf(0f, 0.68f, 1f), Shader.TileMode.CLAMP)
                canvas.drawRect(bounds, p)
                p.shader = null
            }
            bloom(w * 0.20f, h * 0.04f, w * 1.15f, Color.argb(98, 248, 60, 80))
            bloom(w * 0.90f, h * 0.62f, w * 1.28f, Color.argb(82, 62, 128, 255))
            bloom(w * 0.60f, h * 0.29f, w * 0.95f, Color.argb(64, 255, 156, 65))
            bloom(w * 0.55f, h * 0.05f, w * 1.05f, Color.argb(46, 168, 82, 250))
        }
        override fun setAlpha(alpha: Int) {}
        override fun setColorFilter(colorFilter: ColorFilter?) {}
        @Deprecated("Legacy opacity contract")
        override fun getOpacity(): Int = PixelFormat.OPAQUE
    }

''' + src[b:]
# Preserve screen content but update package version for this experimental build.
# Earlier UI scripts already import Color and ColorDrawable. Kotlin treats duplicate
# imports as an error rather than politely ignoring them.
seen_imports = set()
unique_lines = []
for line in src.splitlines(keepends=True):
    if line.startswith("import "):
        if line in seen_imports:
            continue
        seen_imports.add(line)
    unique_lines.append(line)
src = "".join(unique_lines)
main.write_text(src)
build = gradle.read_text()
build = re.sub(r'versionCode = \d+', 'versionCode = 100', build, count=1)
build = re.sub(r'versionName = "[^"]+"', 'versionName = "0.8.0-oled-experimental"', build, count=1)
gradle.write_text(build)

assert 'private class AuroraDrawable' in src
assert 'drawerSearch.addTextChangedListener' in src
assert '#000000' in palette.read_text()
print("OLED experimental UI: black palette, searchable sidebar, rounded chat list, persistent aurora toggle")

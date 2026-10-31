#!/usr/bin/env python3
"""OLED UI v0.8.1: composer model picker, minimal top bar and pitch-black drawer."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
layout = root / "app/src/main/res/layout/activity_main.xml"
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
gradle = root / "app/build.gradle.kts"
xml = layout.read_text()

def cut_block(source, opening, closing):
    a = source.find(opening)
    if a < 0:
        raise SystemExit("UI block start missing: " + opening[:100])
    b = source.find(closing, a)
    if b < 0:
        raise SystemExit("UI block close missing: " + closing)
    b += len(closing)
    return source[:a], source[a:b], source[b:]

# Preserve the existing, functional model selector; just move it from above
# the conversation to the bottom composer, adjacent to message input and send.
prefix, model, suffix = cut_block(
    xml,
    '        <com.google.android.material.card.MaterialCardView\n            android:id="@+id/modelCard"',
    '        </com.google.android.material.card.MaterialCardView>',
)
xml = prefix + suffix
model = model.replace('android:layout_gravity="center_horizontal"', 'android:layout_gravity="start"')
model = model.replace('android:layout_marginStart="16dp"', 'android:layout_marginStart="0dp"', 1)
model = model.replace('android:layout_marginEnd="16dp"', 'android:layout_marginEnd="0dp"', 1)
model = model.replace('android:layout_marginTop="2dp"', 'android:layout_marginTop="0dp"', 1)
model = model.replace('android:layout_marginBottom="4dp"', 'android:layout_marginBottom="0dp"', 1)
model = model.replace('app:cardBackgroundColor="@color/chip_background"', 'app:cardBackgroundColor="@color/surface_alt"')
model = model.replace('android:maxWidth="245dp"', 'android:maxWidth="170dp"')
model = model.replace('android:layout_height="40dp"', 'android:layout_height="38dp"', 1)

before, old_composer, after = cut_block(
    xml,
    '        <com.google.android.material.card.MaterialCardView\n            android:id="@+id/composerCard"',
    '        </com.google.android.material.card.MaterialCardView>',
)
input_match = re.search(r'                <EditText\n\s+android:id="@\+id/inputView"[\s\S]*? />', old_composer)
send_match = re.search(r'                <ImageButton\n\s+android:id="@\+id/sendButton"[\s\S]*? />', old_composer)
if not input_match or not send_match:
    raise SystemExit("Composer message field or send button missing")
message_input = input_match.group()
message_input = message_input.replace('android:layout_width="0dp"', 'android:layout_width="match_parent"')
message_input = message_input.replace('                    android:layout_weight="1"\n', '')
message_input = message_input.replace('android:minHeight="42dp"', 'android:minHeight="43dp"')
send = send_match.group()
model = "\n".join("    " + ln if ln else ln for ln in model.splitlines())

composer = '''        <com.google.android.material.card.MaterialCardView
            android:id="@+id/composerCard"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:layout_marginStart="12dp"
            android:layout_marginEnd="12dp"
            android:layout_marginBottom="10dp"
            app:cardBackgroundColor="@color/surface"
            app:cardCornerRadius="25dp"
            app:cardElevation="0dp"
            app:strokeColor="@color/divider"
            app:strokeWidth="1dp">

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="vertical"
                android:paddingStart="15dp"
                android:paddingTop="7dp"
                android:paddingEnd="8dp"
                android:paddingBottom="8dp">

''' + message_input + '''

                <LinearLayout
                    android:layout_width="match_parent"
                    android:layout_height="46dp"
                    android:gravity="center_vertical"
                    android:orientation="horizontal">

''' + model + '''

                    <Space
                        android:layout_width="0dp"
                        android:layout_height="1dp"
                        android:layout_weight="1" />

''' + send + '''
                </LinearLayout>
            </LinearLayout>
        </com.google.android.material.card.MaterialCardView>'''
xml = before + composer + after

# Retain the IDs for legacy listeners, but remove the unused top settings menu
# and status subtitle from visible navigation.
xml = re.sub(
    r'(android:id="@\+id/headerSubtitle"[\s\S]*?android:textSize="11sp")',
    lambda m: m.group(1) + '\n                    android:visibility="gone"',
    xml, count=1,
)
xml = re.sub(
    r'(android:id="@\+id/menuButton"[\s\S]*?android:src="@drawable/ic_more")',
    lambda m: m.group(1) + '\n                android:visibility="gone"',
    xml, count=1,
)

# Drawer should truly use OLED black rather than the old graphite gray.
drawer_start = xml.index('        android:id="@+id/chatDrawer"')
drawer_block = xml[drawer_start:]
drawer_block = drawer_block.replace('android:background="@color/surface"', 'android:background="@color/app_background"', 1)
drawer_block = drawer_block.replace('android:paddingStart="16dp"', 'android:paddingStart="20dp"', 1)
drawer_block = drawer_block.replace('android:paddingEnd="16dp"', 'android:paddingEnd="20dp"', 1)
drawer_block = drawer_block.replace('android:paddingStart="8dp"', 'android:paddingStart="20dp"', 1)
button_start = drawer_block.index('android:id="@+id/drawerNewChatButton"')
button_end = drawer_block.index('/>', button_start)
button_section = drawer_block[button_start:button_end]
button_section = button_section.replace('android:layout_marginBottom="12dp"',
                                        'android:layout_marginStart="8dp"\n            android:layout_marginEnd="8dp"\n            android:layout_marginBottom="12dp"')
drawer_block = drawer_block[:button_start] + button_section + drawer_block[button_end:]
# Remove the boastful footer; the user knows it's a local app.
drawer_block, count = re.subn(
    r'\n        <TextView\n            android:layout_width="match_parent"\n            android:layout_height="34dp"[\s\S]*?android:letterSpacing="0.10" />',
    '', drawer_block, count=1)
if count != 1:
    raise SystemExit("PRIVATE · ON-DEVICE footer not found")
drawer_block = drawer_block.replace('android:text="Settings &amp; models"', 'android:text="Settings"')
# Keep app-export behavior accessible now that the top-right menu is hidden.
export_button = '''        <TextView
            android:id="@+id/drawerExportButton"
            android:layout_width="match_parent"
            android:layout_height="48dp"
            android:gravity="center_vertical"
            android:paddingStart="12dp"
            android:paddingEnd="12dp"
            android:text="Export data"
            android:textColor="@color/text_secondary"
            android:textSize="14sp" />

'''
close_drawer = '    </LinearLayout>\n</androidx.drawerlayout.widget.DrawerLayout>'
if close_drawer not in drawer_block:
    raise SystemExit("Drawer close not found")
drawer_block = drawer_block.replace(close_drawer, export_button + close_drawer, 1)
xml = xml[:drawer_start] + drawer_block
ET.fromstring(xml)
layout.write_text(xml)

src = main.read_text()
def change_once(old, new):
    global src
    if old not in src:
        raise SystemExit("Kotlin UI anchor missing: " + old[:110])
    src = src.replace(old, new, 1)

# Shifts both empty-state lines upward, while allowing the message list to use
# its entire height when the conversation is non-empty.
change_once('setPadding(dp(18), dp(56), dp(18), dp(56))',
            'setPadding(dp(18), 0, dp(18), dp(156))')
change_once('"Choose a local model above and start chatting."',
            '"Select a model below to start chatting."')
# A direct settings action replaces the former overflow-menu shortcut.
change_once('            menuButton.performClick()\n',
            '            showSettingsDialog()\n')
change_once('        drawerSearch.background = GradientDrawable().apply {\n            setColor(Color.rgb(39, 39, 39))',
            '        drawerSearch.background = GradientDrawable().apply {\n            setColor(Color.rgb(23, 23, 23))')
change_once('setColor(if (selected) Color.rgb(48, 48, 48) else Color.TRANSPARENT)',
            'setColor(if (selected) Color.rgb(30, 30, 30) else Color.TRANSPARENT)')
change_once('        findViewById<View>(R.id.drawerSettingsButton).setOnClickListener {\n            drawerLayout.closeDrawer(GravityCompat.START)\n            showSettingsDialog()\n        }',
            '''        findViewById<View>(R.id.drawerSettingsButton).setOnClickListener {
            drawerLayout.closeDrawer(GravityCompat.START)
            showSettingsDialog()
        }
        findViewById<View>(R.id.drawerExportButton).setOnClickListener {
            drawerLayout.closeDrawer(GravityCompat.START)
            exportLauncher.launch("AndroidLLM-export.zip")
        }''')
main.write_text(src)

build = gradle.read_text()
build = re.sub(r'versionCode = \d+', 'versionCode = 101', build, count=1)
build = re.sub(r'versionName = "[^"]+"', 'versionName = "0.8.1-oled-experimental"', build, count=1)
gradle.write_text(build)

assert xml.count('android:id="@+id/modelCard"') == 1
assert xml.index('android:id="@+id/modelCard"') > xml.index('android:id="@+id/composerCard"')
assert 'android:id="@+id/drawerExportButton"' in xml
assert 'Select a model below' in src
assert 'setPadding(dp(18), 0, dp(18), dp(156))' in src
print("OLED v0.8.1: bottom model picker, centered-up welcome, true-black drawer, direct settings")

#!/usr/bin/env python3
"""OLED v0.8.2 visual cleanup: lightweight model chooser and consistent drawer rows."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
layout = root / "app/src/main/res/layout/activity_main.xml"
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
gradle = root / "app/build.gradle.kts"

xml = layout.read_text()

# Replace the chunky two-chip model selector with a single compact, flat text
# control.  Preserve modelCard/modelNameView/contextView IDs for native listeners.
start = xml.find("<com.google.android.material.card.MaterialCardView\n", xml.index('android:id="@+id/composerCard"'))
if start < 0 or 'android:id="@+id/modelCard"' not in xml[start:start+250]:
    raise SystemExit("Composer model picker was not found")
end_tag = "</com.google.android.material.card.MaterialCardView>"
end = xml.find(end_tag, start)
if end < 0:
    raise SystemExit("Missing composer model picker closing tag")
end += len(end_tag)
replacement = '''<com.google.android.material.card.MaterialCardView
                        android:id="@+id/modelCard"
                        android:layout_width="wrap_content"
                        android:layout_height="wrap_content"
                        android:layout_gravity="center_vertical"
                        android:clickable="true"
                        android:focusable="true"
                        android:contentDescription="Select local model"
                        android:foreground="?attr/selectableItemBackground"
                        app:cardBackgroundColor="@color/surface"
                        app:cardCornerRadius="14dp"
                        app:cardElevation="0dp"
                        app:strokeWidth="0dp">

                        <LinearLayout
                            android:layout_width="wrap_content"
                            android:layout_height="42dp"
                            android:gravity="center_vertical"
                            android:orientation="horizontal"
                            android:paddingStart="3dp"
                            android:paddingEnd="9dp">

                            <TextView
                                android:id="@+id/modelNameView"
                                android:layout_width="wrap_content"
                                android:layout_height="wrap_content"
                                android:ellipsize="end"
                                android:maxLines="1"
                                android:maxWidth="190dp"
                                android:text="Choose model"
                                android:textColor="@color/text_primary"
                                android:textSize="14sp" />

                            <TextView
                                android:layout_width="wrap_content"
                                android:layout_height="wrap_content"
                                android:layout_marginStart="7dp"
                                android:text="⌄"
                                android:textColor="@color/text_secondary"
                                android:textSize="20sp" />

                            <TextView
                                android:id="@+id/contextView"
                                android:layout_width="wrap_content"
                                android:layout_height="wrap_content"
                                android:visibility="gone" />
                        </LinearLayout>
                    </com.google.android.material.card.MaterialCardView>'''
xml = xml[:start] + replacement + xml[end:]

# Same horizontal padding and gray background as the existing New chat pill.
search_start = xml.index('android:id="@+id/drawerSearch"')
search_end = xml.index('/>', search_start)
search = xml[search_start:search_end]
if 'android:layout_width="match_parent"' not in search:
    raise SystemExit("Search input unexpectedly changed")
search = search.replace('android:layout_height="46dp"', '''android:layout_height="52dp"
            android:layout_marginStart="8dp"
            android:layout_marginEnd="8dp"''', 1)
xml = xml[:search_start] + search + xml[search_end:]

ET.fromstring(xml)
layout.write_text(xml)

kt = main.read_text()
old_search = '''        drawerSearch.background = GradientDrawable().apply {
            setColor(Color.rgb(23, 23, 23))
            cornerRadius = dp(14).toFloat()
        }'''
new_search = '''        drawerSearch.background = GradientDrawable().apply {
            setColor(color(R.color.surface_alt))
            cornerRadius = dp(18).toFloat()
        }'''
if old_search not in kt:
    raise SystemExit("Current search style anchor not found")
kt = kt.replace(old_search, new_search, 1)

old_row = 'setColor(if (selected) Color.rgb(30, 30, 30) else Color.TRANSPARENT)'
if old_row not in kt:
    raise SystemExit("Current chat row color anchor not found")
kt = kt.replace(old_row, '''setColor(color(R.color.surface_alt))
                    if (selected) setStroke(dp(1), color(R.color.divider))''', 1)

old_margins = '''            ).apply { bottomMargin = dp(3) })'''
new_margins = '''            ).apply {
                leftMargin = dp(8)
                rightMargin = dp(8)
                bottomMargin = dp(7)
            })'''
if old_margins not in kt:
    raise SystemExit("Chat row margins anchor not found")
kt = kt.replace(old_margins, new_margins, 1)
main.write_text(kt)

build = gradle.read_text()
build = re.sub(r'versionCode = \d+', 'versionCode = 102', build, count=1)
build = re.sub(r'versionName = "[^"]+"', 'versionName = "0.8.2-oled-experimental"', build, count=1)
gradle.write_text(build)

assert xml.count('android:id="@+id/modelCard"') == 1
assert xml.count('android:id="@+id/modelNameView"') == 1
assert xml.count('android:id="@+id/contextView"') == 1
assert xml.index('android:id="@+id/modelCard"') > xml.index('android:id="@+id/composerCard"')
assert 'android:layout_marginStart="8dp"\n            android:layout_marginEnd="8dp"' in search
assert 'setColor(color(R.color.surface_alt))' in kt
assert 'leftMargin = dp(8)' in kt
print("OLED v0.8.2: flat model selector, aligned gray Search/New/Recent controls")

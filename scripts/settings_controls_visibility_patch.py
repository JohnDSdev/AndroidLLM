#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
if not main.exists():
    raise SystemExit("generated MainActivity.kt is missing")

text = main.read_text()
start_marker = "    private fun showSettingsDialog() {"
end_marker = "    private fun showModelsDialog() {"
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("settings function boundaries not found")

block = text[start:end]
for required in ('SheetAction("Reset"', 'SheetAction("Cancel")', 'SheetAction("Save")'):
    if required not in block:
        raise SystemExit(f"missing settings action: {required}")

# The settings content used 70% of the full display height before the title and
# action row were added. On phones, especially with the keyboard or navigation
# insets present, that could push Reset / Cancel / Save below the visible window.
old_height = "(resources.displayMetrics.heightPixels * 0.70f).roundToInt(),"
new_height = "(resources.displayMetrics.heightPixels * 0.52f).roundToInt(),"
if old_height not in block:
    raise SystemExit("settings scroll-height anchor not found")
block = block.replace(old_height, new_height, 1)

# Keep the footer explicit: tapping outside the sheet must not silently discard
# staged edits. Back still behaves like a normal cancel; the visible Cancel
# button is the obvious path out without saving.
old_call = '''        showAppSheet(
            title = "Settings",'''
new_call = '''        val settingsDialog = showAppSheet(
            title = "Settings",'''
if old_call not in block:
    raise SystemExit("settings sheet call anchor not found")
block = block.replace(old_call, new_call, 1)

close_anchor = "        )\n    }\n\n"
close_pos = block.rfind(close_anchor)
if close_pos < 0:
    raise SystemExit("settings sheet closing anchor not found")
block = (
    block[:close_pos]
    + "        )\n        settingsDialog.setCanceledOnTouchOutside(false)\n    }\n\n"
    + block[close_pos + len(close_anchor):]
)

text = text[:start] + block + text[end:]
main.write_text(text)
print("settings footer fix applied: Reset / Cancel / Save remain visible and outside taps do not dismiss staged settings")

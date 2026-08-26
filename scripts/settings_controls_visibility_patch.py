#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
if not main.exists():
    raise SystemExit("generated MainActivity.kt is missing")

text = main.read_text()

# ---------------------------------------------------------------------------
# showAppSheet used to throw away an explicit content height by always adding
# content with WRAP_CONTENT. That made the settings ScrollView expand to its
# full measured height and pushed the action row below the visible screen.
# Preserve an explicitly requested positive content height so only the settings
# body scrolls while Reset / Cancel / Save stay outside it and remain visible.
# ---------------------------------------------------------------------------
old_content_add = '''        if (content != null) {
            root.addView(content, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ))
        }
'''
new_content_add = '''        if (content != null) {
            val requestedContentHeight = content.layoutParams?.height
                ?.takeIf { it > 0 }
                ?: LinearLayout.LayoutParams.WRAP_CONTENT
            root.addView(content, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                requestedContentHeight,
            ))
        }
'''
if old_content_add not in text:
    raise SystemExit("showAppSheet content-layout anchor not found")
text = text.replace(old_content_add, new_content_add, 1)

# ---------------------------------------------------------------------------
# Settings-specific constraints. Keep the scrolling body comfortably below the
# whole display height, leaving room for the title, drag handle, action footer,
# status/navigation insets, and larger accessibility fonts.
# ---------------------------------------------------------------------------
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

old_height = "(resources.displayMetrics.heightPixels * 0.70f).roundToInt(),"
new_height = "(resources.displayMetrics.heightPixels * 0.56f).roundToInt(),"
if old_height not in block:
    # Allow re-running against the previous attempted visibility patch.
    old_height = "(resources.displayMetrics.heightPixels * 0.52f).roundToInt(),"
if old_height not in block:
    raise SystemExit("settings scroll-height anchor not found")
block = block.replace(old_height, new_height, 1)

old_call = '''        showAppSheet(
            title = "Settings",'''
new_call = '''        val settingsDialog = showAppSheet(
            title = "Settings",'''
if old_call in block:
    block = block.replace(old_call, new_call, 1)
elif 'val settingsDialog = showAppSheet(\n            title = "Settings",' not in block:
    raise SystemExit("settings sheet call anchor not found")

# Outside taps should not discard staged changes. Back remains a normal cancel,
# and the visible Cancel button is always available in the pinned footer.
if "settingsDialog.setCanceledOnTouchOutside(false)" not in block:
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

# Guards against shipping another invisible-footer build.
assert "requestedContentHeight" in text
assert "requestedContentHeight," in text
assert "0.56f" in text[start:end + 400]
assert 'SheetAction("Reset"' in text[start:end + 400]
assert 'SheetAction("Cancel")' in text[start:end + 400]
assert 'SheetAction("Save")' in text[start:end + 400]
assert "settingsDialog.setCanceledOnTouchOutside(false)" in text[start:end + 400]

main.write_text(text)
print("settings pinned-footer fix applied: bounded scroll body + visible Reset / Cancel / Save footer")

package com.johndsdev.androidllm

import android.content.Intent
import android.graphics.Bitmap
import android.text.Spanned
import android.view.accessibility.AccessibilityNodeInfo
import io.noties.markwon.core.spans.StrongEmphasisSpan
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.view.GravityCompat
import androidx.drawerlayout.widget.DrawerLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class BlueChatUiTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private fun launch(): MainActivity {
        dismissSystemUiAnr()
        val context = instrumentation.targetContext
        return instrumentation.startActivitySync(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
    }
    private fun snapshot(name: String) {
        dismissSystemUiAnr()
        instrumentation.waitForIdleSync()
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        File(instrumentation.targetContext.filesDir, name).outputStream().use {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        bitmap.recycle()
    }
    private fun dismissSystemUiAnr() {
        val root = instrumentation.uiAutomation.rootInActiveWindow ?: return
        if (root.findAccessibilityNodeInfosByText("System UI isn't responding").none {
                it.text?.toString() == "System UI isn't responding"
            }) return
        root.findAccessibilityNodeInfosByText("Wait").firstOrNull {
            it.text?.toString() == "Wait"
        }?.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        instrumentation.waitForIdleSync()
    }
    @Test fun composerModelPickerAndSidebarSettings() {
        val activity = launch()
        try {
            instrumentation.runOnMainSync {
                val picker = activity.findViewById<View>(R.id.modelCard)
                val composer = activity.findViewById<View>(R.id.composerCard)
                var parent = picker.parent
                while (parent is View && parent !== composer) parent = parent.parent
                assertSame("model picker must be inside the bottom composer", composer, parent)
                assertTrue(picker.height >= (48 * activity.resources.displayMetrics.density).toInt())
                val settings = activity.findViewById<View>(R.id.menuButton)
                val drawer = activity.findViewById<ViewGroup>(R.id.chatDrawer)
                assertSame(drawer, settings.parent.parent)
                assertEquals("Settings", settings.contentDescription)
                assertEquals(0, activity.resources.getIdentifier("newButton", "id", activity.packageName))
                assertTrue(activity.findViewById<View>(R.id.inputView).bottom <= composer.height)
                assertTrue(composer.bottom <= activity.findViewById<View>(R.id.root).height)
                picker.performClick()
            }
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                val dialogField = MainActivity::class.java.getDeclaredField("currentModelDialog").apply { isAccessible = true }
                assertNotNull("model selector must open Models", dialogField.get(activity))
                (dialogField.get(activity) as android.app.Dialog).dismiss()
            }
            snapshot("ui-home.png")
            val density = activity.resources.displayMetrics.density
            val start = android.os.SystemClock.uptimeMillis()
            val y = activity.resources.displayMetrics.heightPixels / 2f
            instrumentation.sendPointerSync(MotionEvent.obtain(start,start,MotionEvent.ACTION_DOWN,2f,y,0))
            for (step in 1..12) {
                instrumentation.sendPointerSync(MotionEvent.obtain(start,start+step*20L,MotionEvent.ACTION_MOVE,2f+step*20f*density,y,0))
            }
            instrumentation.sendPointerSync(MotionEvent.obtain(start,start+260,MotionEvent.ACTION_UP,242f*density,y,0))
            // Wait for DrawerLayout's settle animation, not a fixed screenshot delay.
            repeat(40) {
                var open = false
                instrumentation.runOnMainSync { open = activity.findViewById<DrawerLayout>(R.id.drawerLayout).isDrawerOpen(GravityCompat.START) }
                if (open) return@repeat
                Thread.sleep(25)
            }
            instrumentation.runOnMainSync {
                assertTrue("left edge swipe opens chats", activity.findViewById<DrawerLayout>(R.id.drawerLayout).isDrawerOpen(GravityCompat.START))
            }
            snapshot("ui-chats.png")
            instrumentation.runOnMainSync { activity.findViewById<View>(R.id.menuButton).performClick() }
            instrumentation.waitForIdleSync()
            snapshot("ui-settings.png")
        } finally { instrumentation.runOnMainSync { activity.finish() } }
    }
    @Test fun savedAssistantTextRendersBoldAndCodeAfterReveal() {
        val context = instrumentation.targetContext
        val store = AppStore(context)
        store.newChat()
        store.currentChat().messages.add(ChatMessage("user", "Show formatted text"))
        store.currentChat().messages.add(ChatMessage("assistant", "## Ready to create\n\nA **bold idea**, a little math, and a clear answer.\n\n- Blue gradients\n- Local inference\n\n```python\nprint(\"hello\")\n```"))
        store.save()
        val activity = launch()
        try {
            instrumentation.runOnMainSync {
                val texts = mutableListOf<TextView>()
                fun visit(v: View) {
                    if (v is TextView) texts.add(v)
                    if (v is ViewGroup) for(i in 0 until v.childCount) visit(v.getChildAt(i))
                }
                visit(activity.findViewById(R.id.messageContainer))
                assertTrue("saved markdown has actual bold spans", texts.any { view ->
                    val text = view.text
                    text is Spanned && text.getSpans(0,text.length,StrongEmphasisSpan::class.java).isNotEmpty()
                })
                assertTrue("code remains readable", texts.any { it.text.contains("print(\"hello\")") })
            }
            snapshot("ui-conversation.png")
        } finally { instrumentation.runOnMainSync { activity.finish() } }
    }
}

package com.johndsdev.androidllm

import android.graphics.Rect
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SearchAndScrollTest {
    @Test fun searchProtocolAndBoundedUntrustedResults() {
        assertEquals("moon ice", WebSearchTool.requestedQuery("<think>need facts</think>\n<search>moon ice</search>"))
        assertNull(WebSearchTool.requestedQuery("here is an example: <search>moon</search>"))
        assertNull(WebSearchTool.requestedQuery("<search> </search>"))
        assertNull(WebSearchTool.requestedQuery("<search>" + "a".repeat(241) + "</search>"))
        val xml = "<rss><channel>" + (1..12).joinToString("") { "<item><title>Source $it</title><link>https://example.com/$it</link><description>Evidence &amp; facts</description></item>" } + "</channel></rss>"
        val results = WebSearchTool.parseResults(xml)
        assertEquals(5, results.size)
        assertEquals("Evidence & facts", results.first().snippet)
        assertTrue(WebSearchTool.resultPrompt("moon", results).contains("UNTRUSTED SOURCE DATA"))
        assertTrue(WebSearchTool.resultPrompt("moon", emptyList(), "offline").contains("Search failed: offline"))
        assertEquals(0, WebSearchTool.parseResults("<rss><item><title>Bad</title><link>javascript:alert(1)</link></item></rss>").size)
        val tool = WebSearchTool(); tool.cancel()
        try { tool.search("should never contact network"); fail("Cancelled search ran") } catch (_: IllegalStateException) { }
    }

    @Test fun settingsDefaultSaveCancelResetAndReload() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val store = AppStore(context)
        store.resetGlobalSettings()
        assertFalse(store.currentChat().webSearchEnabled)
        assertTrue(store.currentChat().fastExperts)
        store.currentChat().webSearchEnabled = true
        store.currentChat().fastExperts = false
        store.save()
        val reloaded = AppStore(context)
        assertTrue(reloaded.currentChat().webSearchEnabled)
        assertFalse(reloaded.newChat().fastExperts)
        reloaded.resetGlobalSettings()
        assertFalse(AppStore(context).currentChat().webSearchEnabled)
    }

    @Test fun tallStreamingMessagePinsBeforeDrawingAndIgnoresFocusRequests() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.runOnMainSync {
            val scroll = TranscriptScrollView(instrumentation.targetContext)
            val column = LinearLayout(instrumentation.targetContext).apply { orientation = LinearLayout.VERTICAL }
            val body = TextView(instrumentation.targetContext).apply { textSize = 16f; setTextIsSelectable(false) }
            column.addView(body)
            scroll.addView(column)
            repeat(80) { step ->
                body.append("line $step: **text** with a long answer\n")
                scroll.measure(View.MeasureSpec.makeMeasureSpec(360, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(500, View.MeasureSpec.EXACTLY))
                scroll.layout(0, 0, 360, 500)
                assertEquals((column.height - 500).coerceAtLeast(0), scroll.scrollY)
                val before = scroll.scrollY
                assertFalse(scroll.requestChildRectangleOnScreen(body, Rect(0, 0, 30, 30), true))
                assertEquals(before, scroll.scrollY)
            }
            assertTrue(scroll.scrollY > 500)
        }
    }
}

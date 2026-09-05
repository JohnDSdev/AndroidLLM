package com.johndsdev.androidllm

import android.app.Activity
import android.graphics.Rect
import android.view.MotionEvent
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TranscriptScrollViewTest {
    @Test fun streamingFollowsGrowthButDoesNotOverrideTheReader() {
        val activity = Robolectric.buildActivity(Activity::class.java).setup().get()
        val scroll = TranscriptScrollView(activity).apply { streaming = true }
        val container = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        val body = TextView(activity).apply { text = "A long answer\n".repeat(150) }
        container.addView(body)
        scroll.addView(container)
        activity.setContentView(scroll)
        fun layout() {
            scroll.measure(
                View.MeasureSpec.makeMeasureSpec(400, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(600, View.MeasureSpec.EXACTLY),
            )
            scroll.layout(0, 0, 400, 600)
        }
        layout()
        assertTrue(scroll.scrollY > 0)
        assertFalse(scroll.canScrollVertically(1))
        val firstBottom = scroll.scrollY
        repeat(10) {
            body.append("More tokens\n".repeat(10))
            layout()
            assertFalse(scroll.canScrollVertically(1))
        }
        assertTrue(scroll.scrollY > firstBottom)
        // TextView's focus/selection rectangle must never pull a stream to its top.
        assertFalse(scroll.requestChildRectangleOnScreen(body, Rect(0, 0, 20, 20), true))
        scroll.dispatchTouchEvent(MotionEvent.obtain(0, 0, MotionEvent.ACTION_DOWN, 50f, 50f, 0))
        scroll.scrollTo(0, 120)
        assertFalse(scroll.followTail)
        repeat(10) {
            body.append("Another token\n")
            layout()
            assertEquals(120, scroll.scrollY)
        }
        scroll.jumpToLatest()
        layout()
        assertTrue(scroll.followTail)
        assertFalse(scroll.canScrollVertically(1))
        activity.finish()
    }
}

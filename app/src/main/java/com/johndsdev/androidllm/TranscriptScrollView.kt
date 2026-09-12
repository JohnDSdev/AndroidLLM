package com.johndsdev.androidllm

import android.content.Context
import android.graphics.Rect
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.widget.ScrollView

/** Anchor before drawing, never in a later posted frame or via focus navigation. */
class TranscriptScrollView @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : ScrollView(context, attrs) {
    var following = true
        private set
    private var touching = false
    private var previousY = 0f
    private val bottom: Int get() = ((getChildAt(0)?.height ?: 0) - height + paddingTop + paddingBottom).coerceAtLeast(0)

    fun followBottom() { following = true; requestLayout() }

    override fun onInterceptTouchEvent(event: MotionEvent): Boolean {
        trackTouch(event)
        return super.onInterceptTouchEvent(event)
    }
    override fun onTouchEvent(event: MotionEvent): Boolean {
        trackTouch(event)
        return super.onTouchEvent(event)
    }
    private fun trackTouch(event: MotionEvent) {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> { touching = true; previousY = event.y }
            MotionEvent.ACTION_MOVE -> {
                if (event.y > previousY + 2f) following = false
                previousY = event.y
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> touching = false
        }
    }
    override fun onScrollChanged(l: Int, t: Int, oldl: Int, oldt: Int) {
        super.onScrollChanged(l, t, oldl, oldt)
        if (touching && t < oldt) following = false
        if (t > oldt && bottom - t <= 4) following = true
    }
    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val oldY = scrollY
        val pin = following
        super.onLayout(changed, l, t, r, b)
        scrollTo(0, if (pin) bottom else oldY.coerceAtMost(bottom))
    }
    override fun requestChildRectangleOnScreen(child: View, rectangle: Rect, immediate: Boolean): Boolean = false
}

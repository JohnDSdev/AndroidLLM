package com.johndsdev.androidllm

import android.content.Context
import android.graphics.Rect
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.widget.ScrollView

/** One owner of scroll position: layout follows the tail until the reader scrolls away. */
class TranscriptScrollView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null,
) : ScrollView(context, attrs) {
    var followTail = true
        private set
    var streaming = false
    var onFollowChanged: ((Boolean) -> Unit)? = null

    private fun setFollowing(value: Boolean) {
        if (followTail == value) return
        followTail = value
        onFollowChanged?.invoke(value)
    }

    fun jumpToLatest() {
        setFollowing(true)
        requestLayout()
    }

    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        // Stop pinning before ScrollView handles the gesture, including a fling.
        if (event.actionMasked == MotionEvent.ACTION_DOWN) setFollowing(false)
        val handled = super.dispatchTouchEvent(event)
        if (event.actionMasked == MotionEvent.ACTION_UP || event.actionMasked == MotionEvent.ACTION_CANCEL) {
            setFollowing(!canScrollVertically(1))
        }
        return handled
    }

    override fun onScrollChanged(l: Int, t: Int, oldl: Int, oldt: Int) {
        super.onScrollChanged(l, t, oldl, oldt)
        // This also handles keyboard/accessibility scrolling back to the bottom.
        if (t < oldt) setFollowing(false)
        else if (t > oldt && !canScrollVertically(1)) setFollowing(true)
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val previousY = scrollY
        val wasFollowing = followTail
        super.onLayout(changed, l, t, r, b)
        val childHeight = getChildAt(0)?.height ?: 0
        val bottom = (childHeight - height + paddingTop + paddingBottom).coerceAtLeast(0)
        // Apply once after measurement, before drawing. No posted callbacks race
        // TextView selection/focus requests or a second scroll animation.
        scrollTo(0, if (wasFollowing) bottom else previousY.coerceAtMost(bottom))
        setFollowing(wasFollowing)
    }

    override fun requestChildRectangleOnScreen(child: View, rectangle: Rect, immediate: Boolean): Boolean {
        return if (streaming) false else super.requestChildRectangleOnScreen(child, rectangle, immediate)
    }

    override fun computeScrollDeltaToGetChildRectOnScreen(rect: Rect): Int {
        return if (streaming) 0 else super.computeScrollDeltaToGetChildRectOnScreen(rect)
    }
}

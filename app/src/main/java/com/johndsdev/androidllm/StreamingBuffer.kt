package com.johndsdev.androidllm

/** Append on the inference thread; drain deltas on the UI thread without copying the whole answer. */
class StreamingBuffer {
    private val text = StringBuilder()
    private var consumed = 0

    @Synchronized fun append(piece: String) { text.append(piece) }

    @Synchronized fun drain(smooth: Boolean): String {
        val remaining = text.length - consumed
        if (remaining == 0) return ""
        // Keep animation within ~12 frames of inference; never split a surrogate pair.
        var end = if (smooth) consumed + maxOf(1, (remaining + 11) / 12) else text.length
        if (end < text.length && Character.isHighSurrogate(text[end - 1]) &&
            Character.isLowSurrogate(text[end])) end++
        val delta = text.substring(consumed, end)
        consumed = end
        return delta
    }

    @Synchronized fun snapshot(): String = text.toString()
}

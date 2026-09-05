package com.johndsdev.androidllm

import org.junit.Assert.*
import org.junit.Test

class StreamingBufferTest {
    @Test fun drainsOnlyNewTextAndKeepsCompleteResponse() {
        val stream = StreamingBuffer()
        stream.append("Hello")
        assertEquals("Hello", stream.drain(false))
        assertEquals("", stream.drain(false))
        stream.append(" world")
        assertEquals(" world", stream.drain(false))
        assertEquals("Hello world", stream.snapshot())
    }

    @Test fun smoothModePreservesEmojiAndDrainsLongBacklogs() {
        val text = "🌍Hello 👩🏽‍💻! 漢字\n".repeat(500)
        val stream = StreamingBuffer()
        stream.append(text)
        val output = StringBuilder()
        var frames = 0
        while (true) {
            val delta = stream.drain(true)
            if (delta.isEmpty()) break
            assertFalse(Character.isHighSurrogate(delta.last()))
            assertFalse(Character.isLowSurrogate(delta.first()))
            output.append(delta)
            assertTrue(++frames < 150)
        }
        assertEquals(text, output.toString())
    }

    @Test fun producerAndUiNeverDropOrDuplicateOutput() {
        val stream = StreamingBuffer()
        val producer = Thread { repeat(5000) { stream.append("$it,") } }
        val output = StringBuilder()
        producer.start()
        while (producer.isAlive) output.append(stream.drain(false))
        producer.join()
        output.append(stream.drain(false))
        assertEquals((0 until 5000).joinToString(separator = ",", postfix = ","), output.toString())
    }
}

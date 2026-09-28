package com.johndsdev.androidllm

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.arm.aichat.AiChat
import com.arm.aichat.InferenceEngine
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class InferenceSmokeTest {
    @Test
    fun cpuLoadPrefillGenerateResetAndReload() = runBlocking {
        withTimeout(180_000L) {
            val instrumentation = InstrumentationRegistry.getInstrumentation()
            val context = instrumentation.targetContext
            val model = File(context.cacheDir, "stories260K.gguf")
            instrumentation.context.assets.open("stories260K.gguf").use { input ->
                model.outputStream().use { input.copyTo(it) }
            }
            val engine = AiChat.getInferenceEngine(context)
            engine.state.first { it is InferenceEngine.State.Initialized || it is InferenceEngine.State.Error }
            assertTrue(engine.state.value is InferenceEngine.State.Initialized)
            try {
                repeat(2) { cycle ->
                    val loadStart = System.nanoTime()
                    engine.loadModel(model.absolutePath, 512, 2, 3, 256, 0f, 1, 1f, 0f, false)
                    engine.setSystemPrompt("Tell a story.")
                    Log.i("AndroidLLMTest", "cycle=$cycle ready_ms=${(System.nanoTime()-loadStart)/1e6}")
                    assertFalse(engine.isGpuPromptProcessingActive())
                    // >64 tokens exercises internal microbatch splitting and then
                    // single-token decode with different active pool sizes.
                    for (prompt in listOf("Once upon a time there was a cat. ".repeat(12), "What happened next?")) {
                        var pieces = 0
                        val output = StringBuilder()
                        val start = System.nanoTime()
                        engine.sendUserPrompt(prompt, false).collect { piece ->
                            if (pieces == 0) Log.i("AndroidLLMTest", "first_piece_ms=${(System.nanoTime()-start)/1e6}")
                            output.append(piece)
                            if (++pieces >= 16) engine.stopGeneration()
                        }
                        assertTrue("CPU produced no text", output.isNotBlank())
                        assertTrue(engine.state.value is InferenceEngine.State.ModelReady)
                    }
                    engine.setSystemPrompt("Tell a different story.")
                    assertTrue(engine.state.value is InferenceEngine.State.ModelReady)
                    engine.cleanUp()
                    assertTrue(engine.state.value is InferenceEngine.State.Initialized)
                }
            } finally {
                if (engine.state.value is InferenceEngine.State.ModelReady) engine.cleanUp()
                model.delete()
            }
        }
    }
}

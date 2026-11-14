package com.johndsdev.androidllm

/** The Edge0 engine is separate from llama.cpp; it consumes an asset directory, not GGUF. */
internal fun interface Edge0Output {
    /** kind=0 is visible answer text; kind=1 is internal reasoning. */
    fun onEvent(kind: Int, bytes: ByteArray)
}

internal class Edge0Runtime {
    companion object {
        init { System.loadLibrary("edge0_androidllm") }
    }

    private val handle: Long = nativeCreate()
    @Volatile var loaded: Boolean = false
        private set
    @Volatile var contextLength: Long = 0L
        private set

    @Synchronized
    fun load(directory: String) {
        contextLength = nativeLoad(handle, directory)
        loaded = true
    }

    @Synchronized
    fun reset() {
        if (loaded) nativeReset(handle)
    }

    fun prepare() {
        check(loaded) { "Load an Edge0 asset directory first" }
        nativePrepare(handle)
    }

    /** The caller owns the generation thread. Stop is allowed from a different thread. */
    fun generate(
        messages: List<Pair<String, String>>,
        thinking: Boolean,
        temperature: Double,
        output: Edge0Output,
    ): Double = nativeGenerate(
        handle,
        messages.map { it.first }.toTypedArray(),
        messages.map { it.second }.toTypedArray(),
        thinking, temperature, output
    )

    fun cancel() {
        if (loaded) nativeCancel(handle)
    }

    @Synchronized
    fun unload() {
        if (loaded) {
            nativeUnload(handle)
            loaded = false
            contextLength = 0L
        }
    }

    private external fun nativeCreate(): Long
    private external fun nativeLoad(handle: Long, directory: String): Long
    private external fun nativeReset(handle: Long)
    private external fun nativePrepare(handle: Long)
    private external fun nativeCancel(handle: Long)
    private external fun nativeGenerate(
        handle: Long,
        roles: Array<String>,
        contents: Array<String>,
        thinking: Boolean,
        temperature: Double,
        output: Edge0Output,
    ): Double
    private external fun nativeUnload(handle: Long)
}

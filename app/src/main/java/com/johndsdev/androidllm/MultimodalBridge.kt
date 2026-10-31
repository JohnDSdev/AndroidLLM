package com.johndsdev.androidllm

/** CPU-only llama.cpp libmtmd JNI bridge, explicitly separate from ordinary chat. */
object MultimodalBridge {
    init { System.loadLibrary("ai-chat") }

    @JvmStatic external fun infer(
        modelPath: String,
        mmprojPath: String,
        mediaPath: String,
        question: String,
        maxTokens: Int
    ): String
}

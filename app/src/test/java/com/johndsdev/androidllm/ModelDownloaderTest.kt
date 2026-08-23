package com.johndsdev.androidllm

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.net.ServerSocket
import java.nio.file.Files
import kotlin.concurrent.thread

class ModelDownloaderTest {
    @Test
    fun downloadsGgufIntoDirectoryThatDoesNotExistYet() {
        val root = Files.createTempDirectory("androidllm-downloader-test").toFile()
        val modelsDir = File(root, "nested/models")
        val body = byteArrayOf(0x47, 0x47, 0x55, 0x46, 0x03, 0x00, 0x00, 0x00, 1, 2, 3, 4)
        val server = ServerSocket(0)

        val serverThread = thread(start = true) {
            serveOnce(server, body, body.size)
        }

        try {
            val file = ModelDownloader.download(
                "http://127.0.0.1:${server.localPort}/tiny-test.gguf",
                modelsDir,
            ) { }

            assertTrue(modelsDir.isDirectory)
            assertTrue(file.exists())
            assertTrue(file.name == "tiny-test.gguf")
            assertArrayEquals(body, file.readBytes())
        } finally {
            runCatching { server.close() }
            serverThread.join(2_000)
            root.deleteRecursively()
        }
    }

    @Test
    fun rejectsTruncatedDownload() {
        val root = Files.createTempDirectory("androidllm-truncated-test").toFile()
        val modelsDir = File(root, "models")
        val body = byteArrayOf(0x47, 0x47, 0x55, 0x46, 0x03, 0x00, 0x00, 0x00, 1, 2, 3, 4)
        val server = ServerSocket(0)
        val serverThread = thread(start = true) {
            serveOnce(server, body, body.size + 128)
        }

        try {
            try {
                ModelDownloader.download(
                    "http://127.0.0.1:${server.localPort}/truncated.gguf",
                    modelsDir,
                ) { }
                fail("Expected a truncated download to fail")
            } catch (expected: Exception) {
                val messages = mutableListOf<String>()
                var current: Throwable? = expected
                while (current != null) {
                    current.message?.let { messages += it }
                    current = current.cause
                }
                val text = messages.joinToString(" ").lowercase()
                assertTrue(text.contains("stream") || text.contains("early") || text.contains("unexpected"))
            }
            assertFalse(modelsDir.listFiles()?.any { it.extension.equals("gguf", true) } == true)
        } finally {
            runCatching { server.close() }
            serverThread.join(2_000)
            root.deleteRecursively()
        }
    }

    private fun serveOnce(server: ServerSocket, body: ByteArray, declaredLength: Int) {
        server.accept().use { socket ->
            val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isEmpty()) break
            }
            val header = buildString {
                append("HTTP/1.1 200 OK\r\n")
                append("Content-Type: application/octet-stream\r\n")
                append("Content-Disposition: attachment; filename=\"tiny-test.gguf\"\r\n")
                append("Content-Length: $declaredLength\r\n")
                append("Connection: close\r\n\r\n")
            }.toByteArray()
            socket.getOutputStream().use { output ->
                output.write(header)
                output.write(body)
                output.flush()
            }
        }
        server.close()
    }
}

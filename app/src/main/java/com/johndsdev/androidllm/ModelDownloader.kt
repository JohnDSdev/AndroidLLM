package com.johndsdev.androidllm

import java.io.File
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

object ModelDownloader {
    data class Progress(val downloaded: Long, val total: Long)

    fun download(
        directUrl: String,
        modelsDir: File,
        onProgress: (Progress) -> Unit,
    ): File {
        require(directUrl.startsWith("https://") || directUrl.startsWith("http://")) {
            "Please paste a direct http(s) GGUF download URL."
        }

        modelsDir.mkdirs()
        var currentUrl = directUrl
        var connection = open(currentUrl)
        var redirects = 0
        while (connection.responseCode in 300..399 && redirects < 8) {
            val location = connection.getHeaderField("Location")
                ?: error("Redirect did not include a Location header")
            currentUrl = URL(URL(currentUrl), location).toString()
            connection.disconnect()
            connection = open(currentUrl)
            redirects++
        }

        val code = connection.responseCode
        if (code !in 200..299) {
            val message = connection.errorStream?.bufferedReader()?.use { it.readText().take(300) }
            connection.disconnect()
            error("Download failed with HTTP $code${if (message.isNullOrBlank()) "" else ": $message"}")
        }

        val fileName = chooseFileName(connection, currentUrl)
        require(fileName.lowercase().endsWith(".gguf")) {
            "The direct URL did not resolve to a .gguf file."
        }

        val destination = uniqueDestination(modelsDir, fileName)
        val partial = File(modelsDir, "${destination.name}.part")
        val total = connection.contentLengthLong

        try {
            connection.inputStream.use { input ->
                partial.outputStream().buffered(1024 * 1024).use { output ->
                    val buffer = ByteArray(1024 * 1024)
                    var downloaded = 0L
                    var lastUpdate = 0L
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        output.write(buffer, 0, read)
                        downloaded += read
                        val now = System.currentTimeMillis()
                        if (now - lastUpdate >= 300) {
                            onProgress(Progress(downloaded, total))
                            lastUpdate = now
                        }
                    }
                    output.flush()
                    onProgress(Progress(downloaded, total))
                }
            }

            val magic = ByteArray(4)
            val magicRead = partial.inputStream().use { it.read(magic) }
            require(magicRead == 4 && magic.contentEquals(byteArrayOf(0x47, 0x47, 0x55, 0x46))) {
                "Downloaded file is not a valid GGUF file. Check that the URL points directly to the model file."
            }

            if (!partial.renameTo(destination)) {
                partial.copyTo(destination, overwrite = true)
                partial.delete()
            }
            return destination
        } catch (t: Throwable) {
            partial.delete()
            throw t
        } finally {
            connection.disconnect()
        }
    }

    private fun open(url: String): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 20_000
            readTimeout = 60_000
            instanceFollowRedirects = false
            requestMethod = "GET"
            setRequestProperty("User-Agent", "AndroidLLM/0.1")
        }

    private fun chooseFileName(connection: HttpURLConnection, resolvedUrl: String): String {
        val disposition = connection.getHeaderField("Content-Disposition").orEmpty()
        val fromHeader = Regex("filename\\*?=(?:UTF-8''|\")?([^\";]+)", RegexOption.IGNORE_CASE)
            .find(disposition)
            ?.groupValues
            ?.getOrNull(1)
            ?.let { URLDecoder.decode(it.trim(), StandardCharsets.UTF_8.name()) }
            ?.substringAfterLast('/')
            ?.takeIf { it.isNotBlank() }

        val fromUrl = runCatching {
            URLDecoder.decode(URI(resolvedUrl).path.substringAfterLast('/'), StandardCharsets.UTF_8.name())
        }.getOrNull()?.takeIf { it.isNotBlank() }

        return sanitize(fromHeader ?: fromUrl ?: "model.gguf")
    }

    private fun sanitize(name: String): String {
        val clean = name.replace(Regex("[^A-Za-z0-9._()\\- ]"), "_").trim().take(180)
        return if (clean.isBlank()) "model.gguf" else clean
    }

    private fun uniqueDestination(dir: File, name: String): File {
        var candidate = File(dir, name)
        if (!candidate.exists()) return candidate
        val stem = name.removeSuffix(".gguf")
        var index = 2
        while (candidate.exists()) {
            candidate = File(dir, "$stem ($index).gguf")
            index++
        }
        return candidate
    }
}

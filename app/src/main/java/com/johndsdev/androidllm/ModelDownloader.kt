package com.johndsdev.androidllm

import java.io.File
import java.io.FileInputStream
import java.io.IOException
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
            "Paste a direct http(s) GGUF download URL."
        }

        ensureWritableDirectory(modelsDir)
        val partial = try {
            File.createTempFile("androidllm-model-", ".part", modelsDir)
        } catch (t: Throwable) {
            throw IOException("Could not create a temporary model file in ${modelsDir.absolutePath}", t)
        }

        var connection: HttpURLConnection? = null
        try {
            var currentUrl = directUrl
            var redirects = 0

            while (true) {
                connection?.disconnect()
                connection = open(currentUrl)
                val code = connection.responseCode

                if (code !in 300..399) break
                if (redirects >= 8) throw IOException("Too many redirects while downloading the model")

                val location = connection.getHeaderField("Location")
                    ?: throw IOException("The download redirect did not include a Location header")
                currentUrl = URL(URL(currentUrl), location).toString()
                redirects++
            }

            val code = connection.responseCode
            if (code !in 200..299) {
                val message = connection.errorStream
                    ?.bufferedReader()
                    ?.use { it.readText().replace('\n', ' ').take(240) }
                    ?.takeIf { it.isNotBlank() }
                throw IOException("Download failed with HTTP $code${message?.let { ": $it" } ?: ""}")
            }

            val fileName = chooseFileName(connection, currentUrl)
            if (!fileName.endsWith(".gguf", ignoreCase = true)) {
                throw IOException("The URL did not resolve to a .gguf model file")
            }
            val destination = uniqueDestination(modelsDir, fileName)
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
                            if (read == 0) continue
                            output.write(buffer, 0, read)
                            downloaded += read

                            val now = System.currentTimeMillis()
                            if (now - lastUpdate >= 250L) {
                                onProgress(Progress(downloaded, total))
                                lastUpdate = now
                            }
                        }
                        output.flush()
                        onProgress(Progress(downloaded, total))
                    }
                }
            } catch (t: Throwable) {
                throw IOException("The model download stream failed", t)
            }

            validateGguf(partial)

            if (!partial.renameTo(destination)) {
                try {
                    partial.inputStream().buffered(1024 * 1024).use { input ->
                        destination.outputStream().buffered(1024 * 1024).use { output ->
                            input.copyTo(output, 1024 * 1024)
                        }
                    }
                    if (!partial.delete()) partial.deleteOnExit()
                } catch (t: Throwable) {
                    destination.delete()
                    throw IOException("Downloaded the model but could not move it into model storage", t)
                }
            }

            return destination
        } finally {
            connection?.disconnect()
            if (partial.exists()) partial.delete()
        }
    }

    private fun ensureWritableDirectory(dir: File) {
        if (dir.exists() && !dir.isDirectory) {
            throw IOException("Model storage path is not a directory: ${dir.absolutePath}")
        }
        if (!dir.exists() && !dir.mkdirs()) {
            throw IOException("Could not create model storage: ${dir.absolutePath}")
        }
        if (!dir.canWrite()) {
            throw IOException("Model storage is not writable: ${dir.absolutePath}")
        }
    }

    private fun validateGguf(file: File) {
        if (!file.exists() || file.length() < 8L) {
            throw IOException("The downloaded file is empty or incomplete")
        }
        val magic = ByteArray(4)
        val count = try {
            FileInputStream(file).use { it.read(magic) }
        } catch (t: Throwable) {
            throw IOException("Downloaded the model but could not reopen the temporary file", t)
        }
        val expected = byteArrayOf(0x47, 0x47, 0x55, 0x46)
        if (count != 4 || !magic.contentEquals(expected)) {
            throw IOException("The downloaded file is not GGUF. Make sure the link points directly to the model file")
        }
    }

    private fun open(url: String): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 30_000
            readTimeout = 120_000
            instanceFollowRedirects = false
            requestMethod = "GET"
            useCaches = false
            setRequestProperty("User-Agent", "AndroidLLM/0.2")
            setRequestProperty("Accept", "application/octet-stream,*/*")
            setRequestProperty("Accept-Encoding", "identity")
        }

    private fun chooseFileName(connection: HttpURLConnection, resolvedUrl: String): String {
        val disposition = connection.getHeaderField("Content-Disposition").orEmpty()

        val encodedHeader = Regex("filename\\*\\s*=\\s*UTF-8''([^;]+)", RegexOption.IGNORE_CASE)
            .find(disposition)?.groupValues?.getOrNull(1)
        val quotedHeader = Regex("filename\\s*=\\s*\"([^\"]+)\"", RegexOption.IGNORE_CASE)
            .find(disposition)?.groupValues?.getOrNull(1)
        val plainHeader = Regex("filename\\s*=\\s*([^;]+)", RegexOption.IGNORE_CASE)
            .find(disposition)?.groupValues?.getOrNull(1)

        val headerCandidate = (encodedHeader ?: quotedHeader ?: plainHeader)
            ?.trim()
            ?.trim('"', '\'')
            ?.let { runCatching { URLDecoder.decode(it, StandardCharsets.UTF_8.name()) }.getOrDefault(it) }
            ?.replace('\\', '/')
            ?.substringAfterLast('/')
            ?.takeIf { it.isNotBlank() }

        val urlCandidate = runCatching {
            URLDecoder.decode(URI(resolvedUrl).path.substringAfterLast('/'), StandardCharsets.UTF_8.name())
        }.getOrNull()?.takeIf { it.isNotBlank() }

        val preferred = listOfNotNull(headerCandidate, urlCandidate)
            .firstOrNull { it.endsWith(".gguf", ignoreCase = true) }
            ?: headerCandidate
            ?: urlCandidate
            ?: "model.gguf"

        return sanitize(preferred)
    }

    private fun sanitize(name: String): String {
        var clean = name.replace(Regex("[^A-Za-z0-9._()\\- +]"), "_").trim()
        if (clean.length > 180) {
            val extension = if (clean.endsWith(".gguf", ignoreCase = true)) ".gguf" else ""
            clean = clean.removeSuffix(extension).take(180 - extension.length) + extension
        }
        return clean.ifBlank { "model.gguf" }
    }

    private fun uniqueDestination(dir: File, name: String): File {
        var candidate = File(dir, name)
        if (!candidate.exists()) return candidate

        val stem = if (name.endsWith(".gguf", ignoreCase = true)) name.dropLast(5) else name
        var index = 2
        while (candidate.exists()) {
            candidate = File(dir, "$stem ($index).gguf")
            index++
        }
        return candidate
    }
}

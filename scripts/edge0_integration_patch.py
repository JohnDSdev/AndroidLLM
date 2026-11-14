#!/usr/bin/env python3
"""Apply Edge0 integration AFTER all other MainActivity build-time patches."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
main = root / "app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
text = main.read_text()

def once(a, b):
    global text
    if text.count(a) != 1:
        raise SystemExit("Edge0 patch anchor mismatch: " + repr(a[:110]) + " x " + str(text.count(a)))
    text = text.replace(a, b, 1)

def before(a, b):
    once(a, b + a)

once("import androidx.core.content.ContextCompat\n",
     "import androidx.core.content.ContextCompat\nimport androidx.documentfile.provider.DocumentFile\n")
once("import kotlinx.coroutines.flow.collect\n",
     "import kotlinx.coroutines.flow.collect\n"
     "import kotlinx.coroutines.flow.Flow\n"
     "import kotlinx.coroutines.flow.callbackFlow\n"
     "import kotlinx.coroutines.channels.awaitClose\n"
     "import kotlinx.coroutines.channels.trySendBlocking\n")

once("    private lateinit var engine: InferenceEngine\n",
     "    private lateinit var engine: InferenceEngine\n"
     "    private val edge0Engine by lazy { Edge0Runtime() }\n"
     "    private lateinit var edge0ImportLauncher: ActivityResultLauncher<Uri?>\n")
once("        engine = AiChat.getInferenceEngine(applicationContext)\n",
     "        engine = AiChat.getInferenceEngine(applicationContext)\n"
     "        edge0ImportLauncher = registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->\n"
     "            if (uri != null) importEdge0Assets(uri)\n"
     "        }\n")

before("        val downloadButton = MaterialButton(this).apply {",
'''        val edge0Button = MaterialButton(this).apply {
            text = "Import Edge0-35B assets folder"
            isAllCaps = false
            cornerRadius = dp(16)
            setOnClickListener {
                currentModelDialog?.dismiss()
                edge0ImportLauncher.launch(null)
            }
        }
        box.addView(edge0Button, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ))

''')

before("    private fun showDownloadDialog() {", r'''    private fun importEdge0Assets(uri: Uri) {
        if (busy) return
        val source = DocumentFile.fromTreeUri(this, uri)
        if (source == null || !source.isDirectory || source.findFile("model.json")?.isFile != true) {
            showError("Invalid Edge0 assets", IllegalArgumentException(
                "Choose a converted Edge0-35B asset folder containing model.json. " +
                    "Raw Hugging Face weights are not loadable directly."
            ))
            return
        }
        setBusy(true, "Importing Edge0 assets…")
        Thread {
            val temporary = File(store.modelsDir, ".edge0-import-" + System.currentTimeMillis())
            try {
                check(temporary.mkdirs()) { "Could not create temporary model directory" }
                var copied = 0
                fun copyFolder(sourceFolder: DocumentFile, targetFolder: File) {
                    sourceFolder.listFiles().forEach { entry ->
                        val name = entry.name ?: error("An asset has no filename")
                        require(name.isNotBlank() && name != "." && name != ".." &&
                                '/' !in name && '\\' !in name) { "Invalid asset filename" }
                        val destination = File(targetFolder, name)
                        if (entry.isDirectory) {
                            check(destination.mkdir()) { "Could not make asset directory: $name" }
                            copyFolder(entry, destination)
                        } else if (entry.isFile) {
                            contentResolver.openInputStream(entry.uri).use { input ->
                                checkNotNull(input) { "Cannot read Edge0 asset: $name" }
                                destination.outputStream().buffered(1024 * 1024).use { output ->
                                    input.copyTo(output, 1024 * 1024)
                                }
                            }
                            copied++
                            if (copied % 5 == 0) runOnUiThread {
                                showStatus("Imported $copied asset files…", indeterminate = true)
                            }
                        }
                    }
                }
                copyFolder(source, temporary)
                check(File(temporary, "model.json").isFile) { "Missing Edge0 model.json" }
                check(copied > 1) { "Asset folder contains no weights" }
                var name = "Edge0-35B"
                var suffix = 2
                while (File(store.modelsDir, name).exists()) {
                    name = "Edge0-35B-" + suffix++
                }
                val installed = File(store.modelsDir, name)
                check(temporary.renameTo(installed)) { "Cannot finish model import" }
                runOnUiThread {
                    setBusy(false)
                    selectAndLoadModel(installed)
                }
            } catch (error: Throwable) {
                temporary.deleteRecursively()
                runOnUiThread {
                    setBusy(false)
                    showError("Edge0 import failed", error)
                }
            }
        }.start()
    }

''')

# Keep the GGUF engine untouched, and load Edge0 only for a converted asset directory.
once("    private fun ensureModelLoaded(chat: ChatSession) {\n",
'''    private fun ensureModelLoaded(chat: ChatSession) {
        val selected = chat.modelFile ?: loadedModelName ?: error("No model selected")
        val folder = File(store.modelsDir, selected)
        if (isEdge0Asset(folder)) {
            if (chat.modelFile == null) {
                chat.modelFile = selected
                store.save()
            }
            if (edge0Active && loadedModelName == selected) {
                if (loadedChatId != chat.id) {
                    edge0Engine.reset()
                    loadedChatId = chat.id
                }
                return
            }
            unloadModelBlocking()
            runOnUiThread { showStatus("Loading Edge0-35B native engine…", indeterminate = true) }
            edge0Engine.load(folder.absolutePath)
            edge0Active = true
            loadedModelName = selected
            loadedChatId = chat.id
            loadedContextLength = chat.contextLength
            loadedRuntimeKey = "edge0-35b"
            gpuPpActive = false
            runOnUiThread { renderHeader() }
            return
        }
        if (edge0Active) {
            edge0Engine.unload()
            edge0Active = false
        }
''')
once("    private fun unloadModelBlocking() {\n",
'''    private fun unloadModelBlocking() {
        if (edge0Active) {
            edge0Engine.unload()
            edge0Active = false
        }
''')
once("        engine.stopGeneration()\n",
'''        if (edge0Active) edge0Engine.cancel() else engine.stopGeneration()
''')
once("engine.sendUserPrompt(text, enableThinking = chat.thinkingEnabled).collect { token ->",
     "selectedResponseFlow(chat, text).collect { token ->")
before("    private fun sendMessage() {",
'''    private fun selectedResponseFlow(chat: ChatSession, text: String): Flow<String> {
        val selected = chat.modelFile?.let { File(store.modelsDir, it) }
        if (selected == null || !isEdge0Asset(selected)) {
            return engine.sendUserPrompt(text, enableThinking = chat.thinkingEnabled)
        }
        // The model receives the full conversation, and its own runtime handles
        // prompt-prefix caching and MoE expert streaming from flash.
        val transcript = listOf("system" to chat.systemPrompt.ifBlank { AppStore.DEFAULT_SYSTEM_PROMPT }) +
            chat.messages.dropLast(1)
                .filter { it.content.isNotBlank() }
                .map { it.role to it.content }
        return callbackFlow {
            val worker = Thread {
                try {
                    edge0Engine.prepare()
                    val speed = edge0Engine.generate(
                        transcript,
                        chat.thinkingEnabled,
                        chat.temperature.toDouble(),
                        Edge0Output { kind, data ->
                            // Do not put raw reasoning tokens in the visible answer.
                            if (kind == 0) trySendBlocking(data.toString(Charsets.UTF_8))
                        }
                    )
                    if (speed.isFinite() && speed > 0.0) lastTps = speed
                    close()
                } catch (error: Throwable) {
                    close(error)
                }
            }
            worker.name = "AndroidLLM-Edge0"
            worker.start()
            awaitClose { edge0Engine.cancel() }
        }
    }

''')

# A converted Edge0 model is a directory with a model manifest.
once(
'''    private fun modelFiles(): List<File> =
        store.modelsDir.listFiles()
            ?.filter { it.isFile && it.extension.equals("gguf", ignoreCase = true) }
            ?.sortedBy { it.name.lowercase() }
            ?: emptyList()
''',
'''    private fun isEdge0Asset(file: File): Boolean =
        file.isDirectory && File(file, "model.json").isFile

    private fun modelFiles(): List<File> =
        store.modelsDir.listFiles()
            ?.filter { (it.isFile && it.extension.equals("gguf", ignoreCase = true)) || isEdge0Asset(it) }
            ?.sortedBy { it.name.lowercase() }
            ?: emptyList()
''')
once("                append(formatBytes(file.length()))",
     '                append(if (file.isDirectory) "Edge0 native assets" else formatBytes(file.length()))')
once("                    if (file.delete()) {",
     "                    if (if (file.isDirectory) file.deleteRecursively() else file.delete()) {")

d = chr(36) + "{"
old_message = '            message = "' + d + 'file.name}\\n' + d + 'formatBytes(file.length())}",'
new_message = '            message = "' + d + 'file.name}\\n' + d + 'if (file.isDirectory) "Edge0 native assets" else formatBytes(file.length())}",'
once(old_message, new_message)

# The CPU benchmark exists for GGUF and must not receive an asset directory.
start = text.find("    private fun openModelOptimizer() {")
end = text.find("    private fun runModelOptimization(", start)
if start < 0 or end < 0:
    raise SystemExit("Edge0 optimizer boundary not found")
optimizer = text[start:end]
if optimizer.count("val files = modelFiles()") != 1:
    raise SystemExit("Edge0 optimizer file list changed")
text = text[:start] + optimizer.replace(
    "val files = modelFiles()", "val files = modelFiles().filter { it.isFile }", 1
) + text[end:]

# Existing export button must continue to work when an Edge0 folder is installed.
old_zip = (
    '                        zip.putNextEntry(ZipEntry("models/' + d + 'model.name}"))\n'
    '                        model.inputStream().buffered(1024 * 1024).use { it.copyTo(zip, 1024 * 1024) }\n'
    '                        zip.closeEntry()\n'
)
new_zip = (
    '                        val contents = if (model.isDirectory) model.walkTopDown().filter { it.isFile }.toList()\n'
    '                                       else listOf(model)\n'
    '                        contents.forEach { entry ->\n'
    '                            val suffix = if (model.isDirectory) "/" + entry.relativeTo(model).invariantSeparatorsPath else ""\n'
    '                            zip.putNextEntry(ZipEntry("models/' + d + 'model.name}' + d + 'suffix}"))\n'
    '                            entry.inputStream().buffered(1024 * 1024).use { it.copyTo(zip, 1024 * 1024) }\n'
    '                            zip.closeEntry()\n'
    '                        }\n'
)
once(old_zip, new_zip)

once("    private val edge0Engine by lazy { Edge0Runtime() }\n",
     "    private val edge0Engine by lazy { Edge0Runtime() }\n"
     "    @Volatile private var edge0Active = false\n")

assert "Edge0 native assets" in text
assert "selectedResponseFlow(chat, text)" in text
assert "edge0ImportLauncher.launch(null)" in text
assert "private fun isEdge0Asset(file: File)" in text
main.write_text(text)
print("Edge0 35B Android integration applied")

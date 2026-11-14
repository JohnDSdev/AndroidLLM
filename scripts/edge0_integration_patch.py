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

once('        contextView.text = "' + '$' + '{formatContext(chat.contextLength)} ctx"\n',
     '        contextView.text = if (loadedModelName != null && loadedModelName == chat.modelFile && edge0Engine.loaded) {\n'
     '            "' + '$' + '{formatContext(edge0Engine.contextLength.coerceAtMost(Int.MAX_VALUE.toLong()).toInt())} ctx"\n'
     '        } else "' + '$' + '{formatContext(chat.contextLength)} ctx"\n')

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

package com.johndsdev.androidllm

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.net.Uri
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.view.Gravity
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Experimental on-device libmtmd image/audio interpreter.
 *
 * LFM3 Omni: speech INPUT is processed by the actual model + its mmproj.
 * Spoken OUTPUT is Android TTS, NOT Omni's native speech codec.
 * Deliberately avoids fake support for model-native audio generation.
 */
class MultimodalActivity : AppCompatActivity() {
    private lateinit var store: AppStore
    private lateinit var prompt: EditText
    private lateinit var output: TextView
    private lateinit var status: TextView
    private lateinit var modelButton: Button
    private lateinit var mmprojButton: Button
    private lateinit var mediaButton: Button
    private lateinit var recordButton: Button
    private lateinit var askButton: Button
    private lateinit var speakSwitch: CheckBox
    private lateinit var progress: ProgressBar

    private var model: File? = null
    private var mmproj: File? = null
    private var attachment: File? = null
    private var recording = AtomicBoolean(false)
    private var recorder: AudioRecord? = null
    private var recordThread: Thread? = null
    private var running = false
    private var talker: TextToSpeech? = null
    private var ttsReady = false
    private var voicePlayer: android.media.MediaPlayer? = null

    private val imagePicker = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) setMedia(uri, "png")
    }
    private val audioPicker = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) setMedia(uri, "wav")
    }
    private val recordPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { allowed ->
        if (allowed) startRecording() else status.text = "Microphone permission denied."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = AppStore(applicationContext)
        window.statusBarColor = Color.BLACK
        window.navigationBarColor = Color.BLACK
        talker = TextToSpeech(applicationContext) { code ->
            ttsReady = code == TextToSpeech.SUCCESS
            if (ttsReady) runOnUiThread { talker?.language = Locale.US }
        }

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            setPadding(dp(18), dp(18), dp(18), dp(18))
        }
        val scroll = ScrollView(this)
        val body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        fun headline(t: String) = TextView(this).apply {
            text = t
            textSize = 23f
            setTextColor(Color.WHITE)
            setPadding(0, dp(4), 0, dp(12))
        }
        fun label(t: String) = TextView(this).apply {
            text = t
            textSize = 13f
            setTextColor(0xffb9b9b9.toInt())
            setPadding(0, dp(3), 0, dp(11))
        }
        fun btn(title: String) = Button(this).apply {
            text = title
            isAllCaps = false
            setTextColor(Color.WHITE)
            backgroundTintList = null
            background = android.graphics.drawable.GradientDrawable().apply {
                setColor(0xff292929.toInt())
                cornerRadius = dp(18).toFloat()
                setStroke(dp(1), 0xff525252.toInt())
            }
            minHeight = dp(48)
        }
        body.addView(headline("Multimodal lab"))
        body.addView(label("Runs image/audio through llama.cpp libmtmd on CPU. Models need a matching mmproj GGUF. Compatible Omni models generate speech using their native audio decoder."))

        modelButton = btn("1 · Choose model")
        mmprojButton = btn("2 · Choose mmproj")
        mediaButton = btn("3 · Attach image or audio")
        recordButton = btn("Record microphone")
        askButton = btn("Run multimodal inference")
        body.addView(modelButton)
        body.addView(mmprojButton)
        body.addView(mediaButton)
        val mediaRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val img = btn("Photo").apply { setOnClickListener { imagePicker.launch("image/*") } }
        val aud = btn("Audio").apply { setOnClickListener { audioPicker.launch("audio/*") } }
        mediaRow.addView(img, LinearLayout.LayoutParams(0, dp(52), 1f))
        mediaRow.addView(aud, LinearLayout.LayoutParams(0, dp(52), 1f))
        body.addView(mediaRow)
        body.addView(recordButton)
        body.addView(label("Tap Record microphone to start recording; tap Stop to attach a 16 kHz WAV. Audio questions are interpreted by supported multimodal GGUF models."))

        prompt = EditText(this).apply {
            hint = "Ask a question about the picture or audio…"
            setHintTextColor(0xffaaaaaa.toInt())
            setTextColor(Color.WHITE)
            setSingleLine(false)
            minLines = 2
            setPadding(dp(16),dp(12),dp(16),dp(12))
            background = android.graphics.drawable.GradientDrawable().apply {
                setColor(0xff202020.toInt())
                cornerRadius = dp(18).toFloat()
                setStroke(dp(1),0xff525252.toInt())
            }
        }
        body.addView(prompt)
        speakSwitch = CheckBox(this).apply {
            text = "Generate speech using LFM3 Omni native audio decoder"
            setTextColor(Color.WHITE)
            isChecked = true
        }
        body.addView(speakSwitch)
        body.addView(askButton)
        progress = ProgressBar(this).apply { visibility = android.view.View.GONE }
        body.addView(progress)
        status = label("Ready. Choose model, mmproj and a media file.")
        body.addView(status)
        output = TextView(this).apply {
            textSize = 16f
            setTextColor(Color.WHITE)
            setPadding(dp(8), dp(16), dp(8), dp(36))
            setTextIsSelectable(true)
            text = ""
        }
        body.addView(output)
        scroll.addView(body)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)

        modelButton.setOnClickListener { selectGguf(false) }
        mmprojButton.setOnClickListener { selectGguf(true) }
        mediaButton.setOnClickListener {
            MaterialAlertDialogBuilder(this)
                .setTitle("Attach media")
                .setItems(arrayOf("Image", "Audio (WAV / MP3 / FLAC)")) { _, which ->
                    if (which == 0) imagePicker.launch("image/*") else audioPicker.launch("audio/*")
                }.show()
        }
        recordButton.setOnClickListener { toggleRecording() }
        askButton.setOnClickListener { runInference() }
    }

    private fun selectGguf(projector: Boolean) {
        val list = store.modelsDir.listFiles()?.filter {
            it.isFile && it.extension.equals("gguf", true) &&
                (it.name.startsWith("mmproj", true) == projector)
        }?.sortedBy { it.name } ?: emptyList()
        if (list.isEmpty()) {
            MaterialAlertDialogBuilder(this)
                .setMessage(if (projector) "Download the matching mmproj GGUF using AndroidLLM's model manager first."
                            else "Download a multimodal model GGUF using AndroidLLM's model manager first.")
                .setPositiveButton("OK", null).show()
            return
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(if (projector) "Choose projector" else "Choose model")
            .setItems(list.map { it.name }.toTypedArray()) { _, i ->
                if (projector) {
                    mmproj = list[i]
                    mmprojButton.text = "mmproj: " + list[i].name.take(35)
                } else {
                    model = list[i]
                    modelButton.text = "Model: " + list[i].name.take(35)
                }
            }.show()
    }

    private fun setMedia(uri: Uri, fallback: String) {
        try {
            val mime = contentResolver.getType(uri) ?: ""
            val ext = when {
                mime.contains("jpeg") -> "jpg"
                mime.contains("png") -> "png"
                mime.contains("webp") -> "webp"
                mime.contains("wav") || mime.contains("wave") -> "wav"
                mime.contains("mpeg") || mime.contains("mp3") -> "mp3"
                mime.contains("flac") -> "flac"
                else -> fallback
            }
            val f = File(cacheDir, "multimodal-attachment." + ext)
            contentResolver.openInputStream(uri)?.use { input ->
                f.outputStream().use { out -> input.copyTo(out) }
            } ?: error("File could not be read")
            require(f.length() in 1..(40L * 1024 * 1024)) { "Media must be between 1 byte and 40 MB." }
            attachment = f
            status.text = "Attached " + ext.uppercase() + ": " + (f.length()/1024) + " KB"
        } catch(e: Exception) {
            status.text = "Attachment error: " + e.message
        }
    }

    private fun toggleRecording() {
        if (recording.get()) {
            recording.set(false)
            recordButton.isEnabled = false
            Thread {
                recordThread?.join(2500)
                runOnUiThread {
                    recordButton.isEnabled = true
                    recordButton.text = "Record microphone"
                }
            }.start()
            return
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            recordPermission.launch(Manifest.permission.RECORD_AUDIO)
        } else startRecording()
    }

    private fun startRecording() {
        if (running || recording.get()) return
        val rate = 16000
        val minimum = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val size = maxOf(minimum,8192)
        if (size < 0) { status.text = "Cannot initialize microphone."; return }
        try {
            val r = AudioRecord(MediaRecorder.AudioSource.MIC,rate,AudioFormat.CHANNEL_IN_MONO,
                                AudioFormat.ENCODING_PCM_16BIT,size)
            require(r.state == AudioRecord.STATE_INITIALIZED) { "Microphone unavailable" }
            recorder = r
            r.startRecording()
            recording.set(true)
            recordButton.text = "Stop recording"
            status.text = "Recording 16 kHz mono audio…"
            recordThread = Thread {
                val bytes = ByteArrayOutputStream()
                val buffer = ByteArray(size)
                val start = System.currentTimeMillis()
                try {
                    while(recording.get() && System.currentTimeMillis()-start < 30000L) {
                        val got = r.read(buffer,0,buffer.size)
                        if(got>0)bytes.write(buffer,0,got)
                    }
                } finally {
                    recording.set(false)
                    runCatching {r.stop()};r.release();recorder=null
                    val pcm=bytes.toByteArray()
                    if(pcm.isNotEmpty()) {
                        val wav=File(cacheDir,"mic-voice.wav")
                        wav.outputStream().use { stream ->
                            val head=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
                            head.put("RIFF".toByteArray())
                            head.putInt(pcm.size+36)
                            head.put("WAVEfmt ".toByteArray())
                            head.putInt(16);head.putShort(1.toShort());head.putShort(1.toShort())
                            head.putInt(rate);head.putInt(rate*2)
                            head.putShort(2.toShort());head.putShort(16.toShort())
                            head.put("data".toByteArray());head.putInt(pcm.size)
                            stream.write(head.array());stream.write(pcm)
                        }
                        attachment = wav
                    }
                    runOnUiThread {
                        recordButton.text = "Record microphone"
                        status.text = if(pcm.isNotEmpty()) "Microphone recording attached ("+(pcm.size/32000)+" sec)"
                                      else "No microphone audio captured"
                    }
                }
            }.apply {start()}
        } catch (e:Exception) {recording.set(false);status.text="Microphone error: "+e.message}
    }

    private fun runInference() {
        if (running || recording.get()) {status.text="Stop recording before running.";return}
        val m=model;val mm=mmproj;val media=attachment
        if (m==null || mm==null || media==null) {
            status.text="Choose a model, its matching mmproj, and image/audio input first."
            return
        }
        running=true
        askButton.isEnabled=false
        progress.visibility=android.view.View.VISIBLE
        output.text=""
        status.text="Running CPU-only multimodal inference. Large models may take time."
        val question=prompt.text.toString()
        Thread {
            val result = try {
                MultimodalBridge.infer(m.absolutePath,mm.absolutePath,media.absolutePath,question,192)
            } catch(e:Throwable) {
                "Multimodal error: " + (e.message?:e.javaClass.simpleName)
            }
            val shouldSpeak = speakSwitch.isChecked && !result.startsWith("Multimodal inference error") &&
                !result.startsWith("Multimodal error:")
            runOnUiThread {
                output.text = result
                if(shouldSpeak) status.text = "Generating Omni-native speech…"
            }
            val voice = if(shouldSpeak) {
                try {
                    val wav=File(cacheDir,"omni-generated-voice.wav")
                    MultimodalBridge.synthesizeNativeSpeech(m.absolutePath,mm.absolutePath,result,wav.absolutePath)
                } catch(e:Throwable) {"ERROR: "+(e.message?:"Native speech generation failed")}
            } else null
            runOnUiThread {
                running=false
                askButton.isEnabled=true
                progress.visibility=android.view.View.GONE
                if(voice!=null && !voice.startsWith("ERROR:")) {
                    status.text="Playing LFM3 Omni generated voice"
                    try {
                        voicePlayer?.release()
                        voicePlayer=android.media.MediaPlayer().apply {
                            setDataSource(voice)
                            setOnCompletionListener { it.release();voicePlayer=null }
                            prepare()
                            start()
                        }
                    } catch(e:Exception) { status.text="Could not play Omni WAV: "+e.message }
                } else if(voice!=null) {
                    status.text=voice
                } else status.text="Finished."
            }
        }.start()
    }

    private fun dp(n: Int)=(n*resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        recording.set(false)
        talker?.stop()
        talker?.shutdown()
        voicePlayer?.release()
        voicePlayer=null
        super.onDestroy()
    }
}

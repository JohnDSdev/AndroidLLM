#!/usr/bin/env python3
"""Experimental-only, CPU-only native model autotuner."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
layout=root/"app/src/main/res/layout/activity_main.xml"
main=root/"app/src/main/java/com/johndsdev/androidllm/MainActivity.kt"
gradle=root/"app/build.gradle.kts"
xml=layout.read_text()
anchor='''        <TextView
            android:id="@+id/drawerSettingsButton"'''
if xml.count(anchor)!=1: raise SystemExit("Drawer settings node not found")
item='''        <TextView
            android:id="@+id/drawerOptimizeButton"
            android:layout_width="match_parent"
            android:layout_height="54dp"
            android:gravity="center_vertical"
            android:paddingStart="12dp"
            android:paddingEnd="12dp"
            android:text="Optimize model"
            android:textColor="@color/text_primary"
            android:textSize="15sp" />

'''
xml=xml.replace(anchor,item+anchor,1)
ET.fromstring(xml)
layout.write_text(xml)
src=main.read_text()
nav='''        findViewById<View>(R.id.drawerSettingsButton).setOnClickListener {'''
if src.count(nav)!=1: raise SystemExit("Settings click listener not found")
src=src.replace(nav,'''        findViewById<View>(R.id.drawerOptimizeButton).setOnClickListener {
            drawerLayout.closeDrawer(GravityCompat.START)
            openModelOptimizer()
        }
'''+nav,1)
insert='''    private fun applyAurora() {'''
if src.count(insert)!=1: raise SystemExit("Kotlin method insertion point not found")
new_methods=r'''
    @Volatile private var optimizerStopRequested = false

    private data class TuneConfig(val gen: Int, val prompt: Int, val batch: Int) {
        override fun toString(): String =
            gen.toString() + " generation / " + prompt + " prompt threads, batch " + batch
    }

    private data class TuneScore(val config: TuneConfig, val speeds: List<Double>) {
        val sustained: Double get() = speeds.minOrNull() ?: 0.0
    }

    private fun batteryTempC(): Float? {
        val intent = registerReceiver(null, android.content.IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED))
        val value = intent?.getIntExtra(android.os.BatteryManager.EXTRA_TEMPERATURE, -1) ?: -1
        return if (value in 1..800) value / 10f else null
    }

    private fun cpuThermalStatus(): Int =
        (getSystemService(android.content.Context.POWER_SERVICE) as android.os.PowerManager).currentThermalStatus

    private fun openModelOptimizer() {
        if (busy) return
        val files = modelFiles()
        if (files.isEmpty()) {
            MaterialAlertDialogBuilder(this).setTitle("Optimize model")
                .setMessage("Download a GGUF model to use the CPU tuner.")
                .setPositiveButton("OK", null).show()
            return
        }
        MaterialAlertDialogBuilder(this)
            .setTitle("Choose a model to optimize")
            .setItems(files.map { it.name }.toTypedArray()) { _, index ->
                confirmModelOptimization(files[index])
            }
            .setNegativeButton("Cancel", null).show()
    }

    private fun confirmModelOptimization(file: File) {
        if (busy) return
        val previous = getSharedPreferences("model_tune", MODE_PRIVATE)
            .getString("best:" + file.name + ":" + file.length() + ":" + file.lastModified(), null)
        val message = "Tests 8 CPU thread/batch combinations twice in reverse order after warming up. " +
            "Uses actual llama.cpp tokens/sec, and ranks by the slower pass for sustained performance.\n\n" +
            "Battery temperature and Android thermal status are monitored; the test stops if severely hot. " +
            "No GPU or NPU. You can stop between trials. Settings do not change until you tap Apply." +
            (if (previous != null) "\n\nPreviously saved: " + previous else "")
        MaterialAlertDialogBuilder(this)
            .setTitle("Optimize " + file.name)
            .setMessage(message)
            .setPositiveButton("Start") { _, _ -> runModelOptimization(file) }
            .setNegativeButton("Cancel", null).show()
    }

    private fun runModelOptimization(file: File) {
        if (busy) return
        optimizerStopRequested = false
        setBusy(true, "Preparing native benchmark…")
        val progress = TextView(this).apply {
            text = "Warming up the CPU…"
            textSize = 14f
            setTextColor(color(R.color.text_primary))
            setPadding(dp(22), dp(18), dp(22), dp(18))
        }
        val dialog = MaterialAlertDialogBuilder(this).setTitle("Thermal-aware CPU tuning")
            .setView(progress).setNegativeButton("Stop", null)
            .setCancelable(false).create()
        dialog.setOnShowListener {
            dialog.getButton(androidx.appcompat.app.AlertDialog.BUTTON_NEGATIVE).setOnClickListener {
                optimizerStopRequested = true
                progress.text = "Stopping after current test…"
            }
        }
        dialog.show()

        val chat = store.currentChat()
        val configs = listOf(
            TuneConfig(2, 4, 256),
            TuneConfig(3, 4, 512),
            TuneConfig(4, 6, 512),
            TuneConfig(4, 6, 256),
            TuneConfig(3, 6, 512),
            TuneConfig(4, 4, 1024),
            TuneConfig(6, 6, 512),
            TuneConfig(2, 6, 512),
        ).distinct()
        val scores = mutableMapOf<TuneConfig, MutableList<Double>>()
        val initialTemp = batteryTempC()

        Thread {
            var errorText: String? = null
            var heatStop = false
            try {
                unloadModelBlocking()
                waitForNativeInitialization()
                fun measure(config: TuneConfig): Double {
                    if (optimizerStopRequested) error("Stopped")
                    unloadModelBlocking()
                    runBlocking {
                        engine.loadModel(
                            file.absolutePath, chat.contextLength,
                            config.gen, config.prompt, config.batch,
                            chat.temperature, chat.topK, chat.topP, chat.minP, false
                        )
                    }
                    val result = runBlocking { engine.bench(128, 48, 1, 1) }
                    val value = Regex("""\|\s*tg\s+\d+\s*\|\s*([0-9]+(?:\.[0-9]+)?)""")
                        .find(result)?.groupValues?.get(1)?.toDoubleOrNull()
                    require(value != null && value > 0 && value.isFinite()) {
                        "Native TG benchmark result invalid: " + result.take(300)
                    }
                    return value
                }
                // Cold-start warmup is intentionally *not* ranked.
                measure(TuneConfig(4, 6, 512))
                for (pass in 0..1) {
                    val sequence = if (pass == 0) configs else configs.reversed()
                    for ((index, config) in sequence.withIndex()) {
                        if (optimizerStopRequested) break
                        val thermal = cpuThermalStatus()
                        val temp = batteryTempC()
                        if (thermal >= android.os.PowerManager.THERMAL_STATUS_SEVERE ||
                            (temp != null && temp >= 46f)) {
                            heatStop = true
                            optimizerStopRequested = true
                            break
                        }
                        runOnUiThread {
                            progress.text = "Pass " + (pass + 1) + "/2 · " +
                                (index + 1) + "/" + sequence.size + "\n\n" + config +
                                "\n\nBattery: " + (temp?.let { "%.1f°C".format(it) } ?: "unknown") +
                                "\nThermal status: " + thermal +
                                "\n\nComparing sustained rather than cold-start speed…"
                        }
                        scores.getOrPut(config) { mutableListOf() }.add(measure(config))
                    }
                    if (optimizerStopRequested) break
                }
            } catch (e: Throwable) {
                if (!optimizerStopRequested) errorText = e.message ?: e.javaClass.simpleName
            } finally {
                runCatching { unloadModelBlocking() }
                val completed = configs.mapNotNull { config ->
                    scores[config]?.takeIf { it.size == 2 }?.let { TuneScore(config, it.toList()) }
                }
                val winner = completed.maxByOrNull { it.sustained }
                val stopped = optimizerStopRequested
                val failure = errorText
                val overheated = heatStop
                runOnUiThread {
                    dialog.dismiss()
                    setBusy(false)
                    renderAll()
                    showTuneResults(file, chat, completed, winner, initialTemp,
                        stopped, overheated, failure)
                }
            }
        }.start()
    }

    private fun showTuneResults(
        file: File, chat: ChatSession, results: List<TuneScore>,
        best: TuneScore?, initialTemp: Float?, stopped: Boolean,
        overheated: Boolean, failure: String?
    ) {
        val report = buildString {
            if (overheated) append("Stopped to protect the phone from excessive heat.\n\n")
            else if (stopped) append("Stopped by user.\n\n")
            if (failure != null) append("Error: " + failure + "\n\n")
            append("Battery " + (initialTemp?.let { "%.1f°C".format(it) } ?: "unknown") +
                " → " + (batteryTempC()?.let { "%.1f°C".format(it) } ?: "unknown") + "\n")
            append("Ranking uses slower of two passes; incomplete tests are excluded.\n\n")
            if (results.isEmpty()) append("No complete results. No settings changed.")
            for ((i, item) in results.sortedByDescending { it.sustained }.withIndex()) {
                append((i + 1).toString() + ". " + item.config + "\n")
                append("%.1f sustained tok/s".format(item.sustained) +
                    " (%.1f / %.1f)\n".format(item.speeds[0], item.speeds[1]))
            }
        }
        val builder = MaterialAlertDialogBuilder(this)
            .setTitle(if (best == null) "Optimization incomplete" else "Optimization results")
            .setMessage(report)
            .setNegativeButton("Close", null)
        if (best != null && !stopped && !overheated && failure == null) {
            builder.setPositiveButton("Apply best") { _, _ ->
                val c = best.config
                store.currentChat().modelFile = file.name
                store.applyGlobalSettings(
                    systemPrompt = chat.systemPrompt,
                    contextLength = chat.contextLength,
                    thinkingEnabled = chat.thinkingEnabled,
                    generationThreads = c.gen,
                    promptThreads = c.prompt,
                    batchSize = c.batch,
                    temperature = chat.temperature,
                    topK = chat.topK,
                    topP = chat.topP,
                    minP = chat.minP,
                    prettyMode = chat.prettyMode,
                )
                val key = "best:" + file.name + ":" + file.length() + ":" + file.lastModified()
                val saved = c.gen.toString() + "/" + c.prompt + " threads, batch " +
                    c.batch + ", " + "%.1f".format(best.sustained) + " sustained tok/s"
                getSharedPreferences("model_tune", MODE_PRIVATE).edit()
                    .putString(key, saved).apply()
                store.save()
                renderAll()
                Toast.makeText(this, "Optimized settings applied", Toast.LENGTH_LONG).show()
            }
        }
        builder.show()
    }

'''
src=src.replace(insert,new_methods+insert,1)
main.write_text(src)
g=gradle.read_text()
g=re.sub(r'versionCode = \d+','versionCode = 105',g,count=1)
g=re.sub(r'versionName = "[^"]+"','versionName = "0.9.0-oled-tuner"',g,count=1)
gradle.write_text(g)
assert 'engine.bench(128, 48, 1, 1)' in src
assert 'configs.reversed()' in src
assert 'THERMAL_STATUS_SEVERE' in src
assert 'android:id="@+id/drawerOptimizeButton"' in xml
print("CPU autotuner: 8 configs, two reverse-order passes, thermal safety, manual apply")

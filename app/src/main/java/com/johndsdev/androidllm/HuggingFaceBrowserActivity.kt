package com.johndsdev.androidllm

import android.os.Bundle
import android.graphics.Color
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** Search the public Hugging Face API, choose quantized GGUF, download into private model storage. */
class HuggingFaceBrowserActivity : AppCompatActivity() {
    private val store by lazy { AppStore(applicationContext) }
    private lateinit var query: EditText
    private lateinit var status: TextView
    private lateinit var list: LinearLayout
    private val fg = Color.WHITE
    private val muted = 0xffbbbbbb.toInt()
    @Volatile private var busy = false
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.BLACK
        window.navigationBarColor = Color.BLACK
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            setPadding(dp(18), dp(14), dp(18), dp(14))
        }
        root.addView(label("Find GGUF models",24f,fg))
        root.addView(label("Search Hugging Face, select a quantization, download to the app. For vision/audio models, select the matching mmproj too.",13f,muted))
        query=EditText(this).apply{
            setTextColor(fg);setHintTextColor(muted);hint="Model name (e.g. LFM3 Omni)"
            setSingleLine(true);setText("LFM3 Omni")
        }
        root.addView(query)
        root.addView(button("Search models").apply{setOnClickListener{search(query.text.toString().trim())}})
        status=label("Supports public repositories with GGUF files.",13f,muted)
        root.addView(status)
        val scroll=ScrollView(this)
        list=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL}
        scroll.addView(list)
        root.addView(scroll,LinearLayout.LayoutParams(-1,0,1f))
        setContentView(root)
    }
    private fun dp(x:Int)=(x*resources.displayMetrics.density).toInt()
    private fun label(s:String,z:Float,c:Int)=TextView(this).apply{
        text=s;textSize=z;setTextColor(c);setPadding(dp(6),dp(9),dp(6),dp(9))
    }
    private fun button(s:String)=Button(this).apply{
        text=s;isAllCaps=false;setTextColor(fg)
        backgroundTintList=android.content.res.ColorStateList.valueOf(0xff292929.toInt())
    }
    private fun enc(s:String)=URLEncoder.encode(s,"UTF-8").replace("+","%20")
    private fun get(uri:String):String{
        val c=URL(uri).openConnection() as HttpURLConnection
        c.connectTimeout=12000;c.readTimeout=20000
        c.setRequestProperty("Accept","application/json")
        c.setRequestProperty("User-Agent","AndroidLLM/1.1")
        return try{
            if(c.responseCode !in 200..299) error("Hugging Face HTTP "+c.responseCode)
            c.inputStream.bufferedReader().use{it.readText()}
        }finally{c.disconnect()}
    }
    private fun work(message:String,action:()->Unit){
        if(busy)return
        busy=true;status.text=message
        Thread{
            try{action()}catch(e:Exception){
                runOnUiThread{status.text="Error: "+(e.message?:"Network unavailable")}
            }finally{runOnUiThread{busy=false}}
        }.start()
    }
    private fun search(term:String){
        if(term.isBlank())return
        work("Searching Hugging Face…"){
            val json=JSONArray(get("https://huggingface.co/api/models?search="+enc(term)+"&filter=gguf&sort=downloads&direction=-1&limit=35"))
            val repos=(0 until json.length()).mapNotNull{
                json.optJSONObject(it)?.optString("id")?.takeIf{v->v.contains("/")}
            }
            runOnUiThread{
                list.removeAllViews()
                status.text=repos.size.toString()+" repositories"
                if(repos.isEmpty())list.addView(label("No matching public GGUF repositories.",15f,muted))
                repos.forEach{repo->list.addView(button(repo).apply{setOnClickListener{browse(repo)}})}
            }
        }
    }
    private data class FileChoice(val path:String,val bytes:Long){
        val name get()=path.substringAfterLast('/')
        val projector get()=name.startsWith("mmproj",true)
        val quant get()=Regex("(IQ[1-4]_[A-Z0-9_]+|Q[2-8]_[A-Z0-9_]+|BF16|F16|F32)",RegexOption.IGNORE_CASE)
            .find(name)?.value?:"GGUF"
        fun display()=quant+" · "+"%.2f".format(bytes/1073741824.0)+" GiB\n"+name
    }
    private fun browse(repo:String){
        work("Reading repository files…"){
            val parts=repo.split("/")
            require(parts.size==2){"Invalid repository ID"}
            val uri="https://huggingface.co/api/models/"+enc(parts[0])+"/"+enc(parts[1])+"/tree/main?recursive=true"
            val json=JSONArray(get(uri))
            val files=(0 until json.length()).mapNotNull{
                val o=json.optJSONObject(it)?:return@mapNotNull null
                val name=o.optString("path")
                if(o.optString("type")!="file"||!name.endsWith(".gguf",true))return@mapNotNull null
                val bytes=o.optLong("size",o.optJSONObject("lfs")?.optLong("size")?:0)
                FileChoice(name,bytes)
            }
            runOnUiThread{
                list.removeAllViews()
                status.text=repo+" · "+files.size+" GGUF files"
                list.addView(button("Back to search").apply{setOnClickListener{search(query.text.toString().trim())}})
                if(files.isEmpty())list.addView(label("No GGUFs in this repository.",15f,muted))
                files.sortedWith(compareBy<FileChoice>{it.projector}.thenBy{it.bytes}).take(100).forEach{f->
                    list.addView(button(f.display()).apply{
                        setOnClickListener{choose(repo,f,files.filter{it.projector})}
                    })
                }
            }
        }
    }
    private fun choose(repo:String,choice:FileChoice,projectors:List<FileChoice>){
        val labels=if(!choice.projector&&projectors.isNotEmpty())
            arrayOf("Download this GGUF","Download GGUF and matching projector")
        else arrayOf("Download this GGUF")
        MaterialAlertDialogBuilder(this)
            .setTitle(choice.name)
            .setMessage("Quantization: "+choice.quant+"\nSize: "+"%.2f".format(choice.bytes/1073741824.0)+" GiB")
            .setItems(labels){_,which->
                val files=mutableListOf(choice)
                if(which==1){
                    val matching=projectors.find{it.name.contains(choice.quant,true)}?:projectors.firstOrNull()
                    if(matching!=null)files.add(matching)
                }
                download(repo,files)
            }.setNegativeButton("Cancel",null).show()
    }
    private fun download(repo:String,files:List<FileChoice>){
        work("Downloading GGUF…"){
            for((i,f) in files.withIndex()){
                val uri="https://huggingface.co/"+repo+"/resolve/main/"+
                    f.path.split("/").joinToString("/"){enc(it)}+"?download=true"
                val saved=ModelDownloader.download(uri,store.modelsDir){p->
                    runOnUiThread{
                        val amount=if(p.total>0) (p.downloaded*100/p.total).toString()+"%"
                            else (p.downloaded/1048576).toString()+" MiB"
                        status.text="Downloading "+(i+1)+"/"+files.size+": "+f.name+" · "+amount
                    }
                }
                runOnUiThread{status.text="Saved "+saved.name}
            }
            runOnUiThread{
                MaterialAlertDialogBuilder(this).setTitle("Downloaded")
                    .setMessage("Your GGUF files are now available in AndroidLLM's model selectors.")
                    .setPositiveButton("OK",null).show()
            }
        }
    }
}

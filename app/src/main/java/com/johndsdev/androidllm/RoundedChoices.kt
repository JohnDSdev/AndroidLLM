package com.johndsdev.androidllm

import android.graphics.Typeface
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AlertDialog
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.card.MaterialCardView

/** A consistent, accessible bordered OLED menu rather than a platform list popup. */
object RoundedChoices {
    fun show(activity: AppCompatActivity, title: String, choices: List<String>, onSelect: (Int) -> Unit) {
        fun dp(x:Int)=(x*activity.resources.displayMetrics.density).toInt()
        val box=LinearLayout(activity).apply {
            orientation=LinearLayout.VERTICAL
            setPadding(dp(18),dp(10),dp(18),dp(18))
        }
        lateinit var dialog:AlertDialog
        fun entry(value:String, index:Int) {
            val card=MaterialCardView(activity).apply {
                radius=dp(19).toFloat()
                cardElevation=0f
                strokeWidth=dp(1)
                strokeColor=0xff505050.toInt()
                setCardBackgroundColor(0xff292929.toInt())
                isClickable=true
                isFocusable=true
            }
            val label=TextView(activity).apply {
                text=value
                textSize=15f
                typeface=Typeface.DEFAULT
                setTextColor(0xfff4f4f4.toInt())
                setPadding(dp(16),dp(13),dp(16),dp(13))
            }
            card.addView(label)
            box.addView(card,LinearLayout.LayoutParams(-1,-2).apply{bottomMargin=dp(9)})
            card.setOnClickListener {
                dialog.dismiss()
                if(index>=0)onSelect(index)
            }
        }
        choices.forEachIndexed{index,value->entry(value,index)}
        entry("Cancel",-1)
        val scroll=ScrollView(activity).apply{
            addView(box)
            isFillViewport=false
        }
        dialog=MaterialAlertDialogBuilder(activity)
            .setTitle(title)
            .setView(scroll)
            .create()
        dialog.show()
        dialog.window?.setBackgroundDrawableResource(R.drawable.androidllm_dialog_background)
    }
}

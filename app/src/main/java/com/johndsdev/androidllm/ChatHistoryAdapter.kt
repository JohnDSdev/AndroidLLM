package com.johndsdev.androidllm

import android.graphics.Typeface
import android.text.TextUtils
import android.view.Gravity
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.card.MaterialCardView
import java.time.LocalDate
import java.time.ZoneId

/** Recycled history cards; even a large archive only creates the visible rows. */
class ChatHistoryAdapter(
    private val select: (ChatSession) -> Unit,
    private val options: (ChatSession) -> Unit,
) : RecyclerView.Adapter<ChatHistoryAdapter.Holder>() {
    private data class Entry(val heading: String? = null, val chat: ChatSession? = null)
    private var entries = emptyList<Entry>()
    private var selectedId: String? = null

    fun submit(chats: List<ChatSession>, selected: String?, query: String) {
        selectedId = selected
        val today = LocalDate.now()
        val zone = ZoneId.systemDefault()
        entries = buildList {
            var previous: String? = null
            ChatHistory.matching(chats, query).forEach { chat ->
                val group = ChatHistory.group(chat, today, zone)
                if (group != previous) add(Entry(heading = group))
                add(Entry(chat = chat))
                previous = group
            }
            if (isEmpty()) add(Entry(heading = "No matching chats"))
        }
        notifyDataSetChanged()
    }

    override fun getItemCount() = entries.size
    override fun getItemViewType(position: Int) = if (entries[position].chat == null) 0 else 1

    class Holder(val root: LinearLayout) : RecyclerView.ViewHolder(root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Holder {
        val root = LinearLayout(parent.context).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = RecyclerView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        return Holder(root)
    }

    override fun onBindViewHolder(holder: Holder, position: Int) {
        val root = holder.root
        val context = root.context
        fun dp(n: Int) = (n * context.resources.displayMetrics.density).toInt()
        fun color(id: Int) = ContextCompat.getColor(context, id)
        root.removeAllViews()
        val entry = entries[position]
        val chat = entry.chat
        if (chat == null) {
            root.addView(TextView(context).apply {
                text = entry.heading
                textSize = 12f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(color(R.color.text_secondary))
                setPadding(dp(12), dp(20), dp(12), dp(8))
                isAccessibilityHeading = true
            })
            return
        }
        val selected = chat.id == selectedId
        val card = MaterialCardView(context).apply {
            radius = dp(16).toFloat()
            cardElevation = 0f
            strokeWidth = if (selected) dp(1) else 0
            strokeColor = color(R.color.accent)
            setCardBackgroundColor(color(if (selected) R.color.accent_soft else R.color.surface))
            isClickable = true
            isFocusable = true
            isSelected = selected
            setOnClickListener { select(chat) }
            setOnLongClickListener { options(chat); true }
        }
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(12), dp(4), dp(12))
        }
        val copy = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        copy.addView(TextView(context).apply {
            text = chat.title
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
            setTextColor(color(R.color.text_primary))
        })
        copy.addView(TextView(context).apply {
            text = ChatHistory.preview(chat)
            textSize = 13f
            maxLines = 2
            ellipsize = TextUtils.TruncateAt.END
            setTextColor(color(R.color.text_secondary))
            setPadding(0, dp(5), 0, dp(5))
        })
        copy.addView(TextView(context).apply {
            val count = chat.messages.size
            text = "$count ${if (count == 1) "message" else "messages"}" + if (selected) " · Current chat" else ""
            textSize = 11f
            setTextColor(color(R.color.text_secondary))
        })
        row.addView(copy, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(TextView(context).apply {
            text = "⋮"
            textSize = 24f
            gravity = Gravity.CENTER
            setTextColor(color(R.color.text_secondary))
            contentDescription = "Options for ${chat.title}"
            isFocusable = true
            setOnClickListener { options(chat) }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
        card.addView(row)
        root.addView(card, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            bottomMargin = dp(6)
        })
    }
}

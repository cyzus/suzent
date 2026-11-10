package com.suzent.mobile

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import android.view.ViewGroup
import androidx.compose.ui.graphics.toArgb
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.noties.markwon.AbstractMarkwonPlugin
import io.noties.markwon.Markwon
import io.noties.markwon.core.MarkwonTheme
import io.noties.markwon.ext.tables.TablePlugin
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class InlineCodePreviewTest {
    private val source = """
        主人，`22:45` 定时巡检结果如下：

        - **Job ID**：`40634051`（`optiscene-qwen3-8b`，2 节点 × 4 卡 A100）
        - **当前状态**：`PD`（`PENDING` / 排队中）
        - **排队原因**（`REASON`）：`(Resources)`（已无更高优先级作业挡在前面，目前排在**第 1 顺位**等待 2 台节点释放）
        - **预计最晚启动时间**（`START_TIME`）：`2026-11-10T23:21:23`（约 35 分钟内）

        我会在下次巡检（`23:15`）继续为您跟进！
    """.trimIndent()

    @Test fun renderPreviews() = InstrumentationRegistry.getInstrumentation().runOnMainSync {
        val out = File(context().getExternalFilesDir(null), "preview").apply { mkdirs() }
        for (dark in listOf(false, true)) {
            val mode = if (dark) "dark" else "light"
            save(render(source, dark), File(out, "$mode-final.png"))
            val cut = source.indexOf("`23:15`") + 4
            save(render(source.take(cut), dark), File(out, "$mode-streaming.png"))
        }
    }

    private fun render(markdown: String, dark: Boolean): Bitmap {
        val ctx = context()
        val density = ctx.resources.displayMetrics.density
        val background = if (dark) PresentationTokens.background_dark.toInt() else android.graphics.Color.WHITE
        val foreground = if (dark) PresentationTokens.text_dark.toInt() else android.graphics.Color.BLACK
        val tablePlugin = TablePlugin.create(ctx)
        val renderer = Markwon.builder(ctx).usePlugin(object : AbstractMarkwonPlugin() {
            override fun configureTheme(builder: MarkwonTheme.Builder) {
                builder.codeBackgroundColor(0x00FFFFFF).codeTextColor(android.graphics.Color.BLACK)
            }
        }).usePlugin(tablePlugin).build()
        val view = StableTableTextView(ctx).apply {
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            textSize = PresentationTokens.typeChat.toFloat()
            setLineSpacing(0f, 1.2f)
            setTextColor(foreground)
            setBackgroundColor(background)
            val pad = (16 * density).toInt()
            setPadding(pad, pad, pad, pad)
            this.tablePlugin = tablePlugin
        }
        val content = renderer.render(renderer.parse(markdown))
        renderer.setParsedMarkdown(view, view.prepareMarkdown(android.text.SpannableString(content)))
        val width = 1080
        fun draw(): Bitmap {
            view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
            view.layout(0, 0, width, view.measuredHeight)
            return Bitmap.createBitmap(width, view.measuredHeight, Bitmap.Config.ARGB_8888).also { view.draw(Canvas(it)) }
        }
        draw()
        view.text = inlineCodeBordered(view.text, suzentYellow(dark).toArgb(), 2f * density, view)
        return draw()
    }

    private fun save(bitmap: Bitmap, file: File) = file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    private fun context() = InstrumentationRegistry.getInstrumentation().targetContext
}

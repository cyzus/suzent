package com.suzent.mobile

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.content.Intent
import android.media.MediaPlayer
import android.webkit.MimeTypeMap
import android.widget.MediaController
import android.widget.VideoView
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.FileProvider
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Fetches a tool's media for the conversation on screen; absent where nothing can be fetched. */
val LocalMediaLoader = staticCompositionLocalOf<(suspend (MediaItem) -> File?)?> { null }

private sealed interface MediaState {
    data object Loading : MediaState
    data object Failed : MediaState
    data class Ready(val file: File, val image: Bitmap? = null) : MediaState
}

/** The images, videos, audio and files a turn's tools made or sent, shown inline like the desktop's result gallery. */
@Composable
fun MediaGallery(items: List<MediaItem>) {
    val loader = LocalMediaLoader.current ?: return
    if (items.isEmpty()) return
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        items.distinctBy { it.id }.forEach { item ->
            key(item.id) { if (item.kind == "file") FileRow(item, loader) else MediaTile(item, loader) }
        }
    }
}

/** A sent document or archive: fetched only when the user asks to share or open it. */
@Composable
private fun FileRow(item: MediaItem, loader: suspend (MediaItem) -> File?) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember(item.id) { mutableStateOf(false) }
    var failed by remember(item.id) { mutableStateOf(false) }
    val frame = Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outline)
    Column(frame) {
        Row(Modifier.padding(start = 12.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(painterResource(R.drawable.ic_attach_file), contentDescription = null, modifier = Modifier.size(18.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(item.name, Modifier.weight(1f).padding(horizontal = 10.dp), fontSize = PresentationTokens.typeMeta.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            SuzentIconButton(onClick = {
                busy = true
                failed = false
                scope.launch {
                    val file = loader(item)
                    busy = false
                    if (file == null) failed = true else shareFile(context, file)
                }
            }, label = stringResource(R.string.media_share, item.name), enabled = !busy) {
                Icon(painterResource(R.drawable.ic_share), contentDescription = null, modifier = Modifier.size(18.dp))
            }
        }
        if (busy) MediaNote(stringResource(R.string.media_loading, item.name), Modifier)
        if (failed) MediaNote(stringResource(R.string.media_unavailable, item.name), Modifier)
    }
}

private fun shareFile(context: android.content.Context, file: File) {
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.attachments", file)
    val type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension.lowercase()) ?: "application/octet-stream"
    val send = Intent(Intent.ACTION_SEND).setType(type).putExtra(Intent.EXTRA_STREAM, uri)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    try { context.startActivity(Intent.createChooser(send, file.name)) } catch (_: android.content.ActivityNotFoundException) {}
}

@Composable
private fun MediaTile(item: MediaItem, loader: suspend (MediaItem) -> File?) {
    val state by produceState<MediaState>(MediaState.Loading, item.id) {
        val file = loader(item)
        value = when {
            file == null -> MediaState.Failed
            item.kind == "image" -> withContext(Dispatchers.IO) { decodeImage(file) }?.let { MediaState.Ready(file, it) } ?: MediaState.Failed
            else -> MediaState.Ready(file)
        }
    }
    val outline = MaterialTheme.colorScheme.outline
    val frame = Modifier.fillMaxWidth().border(1.dp, outline)
    when (val current = state) {
        MediaState.Loading -> MediaNote(stringResource(R.string.media_loading, item.name), frame)
        MediaState.Failed -> MediaNote(stringResource(R.string.media_unavailable, item.name), frame)
        is MediaState.Ready -> when (item.kind) {
            "image" -> Image(current.image!!.asImageBitmap(), contentDescription = item.name, contentScale = ContentScale.Fit,
                modifier = frame.heightIn(max = 360.dp))
            "video" -> VideoPlayer(current.file, item.name, frame)
            else -> AudioPlayer(current.file, item.name, frame)
        }
    }
}

@Composable
private fun MediaNote(text: String, modifier: Modifier) {
    Text(text, modifier.padding(12.dp), fontSize = PresentationTokens.typeMeta.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
}

@Composable
private fun VideoPlayer(file: File, name: String, modifier: Modifier) {
    var view by remember(file) { mutableStateOf<VideoView?>(null) }
    DisposableEffect(file) { onDispose { view?.stopPlayback() } }
    Box(modifier.background(Color.Black).heightIn(min = 120.dp, max = 360.dp).semantics { contentDescription = name },
        contentAlignment = Alignment.Center) {
        AndroidView(factory = { context ->
            VideoView(context).apply {
                val controls = MediaController(context)
                controls.setAnchorView(this)
                setMediaController(controls)
                // Show the first frame instead of a black box until the user presses play.
                setOnPreparedListener { seekTo(1) }
                setVideoPath(file.path)
                view = this
            }
        })
    }
}

@Composable
private fun AudioPlayer(file: File, name: String, modifier: Modifier) {
    var playing by remember(file) { mutableStateOf(false) }
    val player = remember(file) {
        runCatching { MediaPlayer().apply { setDataSource(file.path); prepare() } }.getOrNull()
    }
    DisposableEffect(player) {
        player?.setOnCompletionListener { playing = false }
        onDispose { player?.release() }
    }
    if (player == null) {
        MediaNote(stringResource(R.string.media_unavailable, name), modifier)
        return
    }
    Row(modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        SuzentIconButton(onClick = {
            if (playing) player.pause() else player.start()
            playing = !playing
        }, label = stringResource(if (playing) R.string.media_pause else R.string.media_play, name)) {
            Icon(painterResource(if (playing) R.drawable.ic_media_pause else R.drawable.ic_media_play), contentDescription = null,
                modifier = Modifier.size(20.dp))
        }
        Text(name, Modifier.weight(1f), fontSize = PresentationTokens.typeMeta.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** Decodes at most about 1600 px on the long side, so a large render can't exhaust memory. */
private fun decodeImage(file: File): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(file.path, bounds)
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= 1600) sample *= 2
    return BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply { inSampleSize = sample })
}

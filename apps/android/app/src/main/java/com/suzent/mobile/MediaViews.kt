package com.suzent.mobile

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.MediaPlayer
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.widget.Toast
import android.webkit.MimeTypeMap
import android.widget.MediaController
import android.widget.VideoView
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
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
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
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

private fun shareFile(context: Context, file: File) {
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
            "image" -> ImageTile(current.file, current.image!!, item.name, frame)
            "video" -> VideoPlayer(current.file, item.name, frame)
            else -> AudioPlayer(current.file, item.name, frame)
        }
    }
}

/** An inline image: tap opens it full screen, long press offers saving and sharing. */
@Composable
private fun ImageTile(file: File, image: Bitmap, name: String, modifier: Modifier) {
    var viewing by remember(file) { mutableStateOf(false) }
    var actions by remember(file) { mutableStateOf(false) }
    var menuAnchor by remember(file) { mutableStateOf<Offset?>(null) }
    var pressAt by remember(file) { mutableLongStateOf(0L) }
    Box {
        Image(image.asImageBitmap(), contentDescription = name, contentScale = ContentScale.Fit,
            modifier = modifier.heightIn(max = 360.dp).recordPressInWindow {
                menuAnchor = it
                pressAt = android.os.SystemClock.uptimeMillis()
            }.combinedClickable(
                onClickLabel = stringResource(R.string.media_open, name),
                onLongClickLabel = stringResource(R.string.media_actions),
                onClick = { viewing = true }, onLongClick = {
                    // Accessibility actions have no current touch to anchor to.
                    if (android.os.SystemClock.uptimeMillis() - pressAt > 1_500L) menuAnchor = null
                    actions = true
                }))
        ImageActions(file, actions, menuAnchor) { actions = false }
    }
    if (viewing) ImageViewer(file, name) { viewing = false }
}

@Composable
private fun ImageActions(file: File, expanded: Boolean, anchorInWindow: Offset?, dismiss: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    SuzentMenu(expanded = expanded, onDismissRequest = dismiss, anchorInWindow = anchorInWindow) {
        if (canSaveToPhotos()) DropdownMenuItem(text = { Text(stringResource(R.string.media_save)) }, onClick = {
            dismiss()
            scope.launch { announceSave(context, saveToPhotos(context, file)) }
        })
        DropdownMenuItem(text = { Text(stringResource(R.string.media_share, file.name)) }, onClick = {
            dismiss()
            shareFile(context, file)
        })
    }
}

/** Full screen, pinch or double tap to zoom, drag to pan when zoomed. */
@Composable
private fun ImageViewer(file: File, name: String, close: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val image by produceState<Bitmap?>(null, file) { value = withContext(Dispatchers.IO) { decodeImage(file, 2560) } }
    var scale by remember(file) { mutableFloatStateOf(1f) }
    var offset by remember(file) { mutableStateOf(Offset.Zero) }
    var actions by remember(file) { mutableStateOf(false) }
    var menuAnchor by remember(file) { mutableStateOf<Offset?>(null) }
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(Modifier.fillMaxSize().background(Color.Black)) {
            image?.let { bitmap ->
                Image(bitmap.asImageBitmap(), contentDescription = name, contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxSize()
                        .recordPressInWindow { menuAnchor = it }
                        .pointerInput(file) {
                            detectTransformGestures { _, pan, zoom, _ ->
                                scale = (scale * zoom).coerceIn(1f, 6f)
                                offset = if (scale == 1f) Offset.Zero else offset + pan
                            }
                        }
                        .pointerInput(file) {
                            detectTapGestures(
                                onDoubleTap = {
                                    if (scale > 1f) { scale = 1f; offset = Offset.Zero } else scale = 2.5f
                                },
                                onLongPress = { actions = true })
                        }
                        .graphicsLayer { scaleX = scale; scaleY = scale; translationX = offset.x; translationY = offset.y })
            }
            Row(Modifier.fillMaxWidth().statusBarsPadding().padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                SuzentIconButton(onClick = close, label = stringResource(R.string.media_close)) {
                    Icon(painterResource(R.drawable.ic_close), contentDescription = null, tint = Color.White,
                        modifier = Modifier.size(20.dp))
                }
                Text(name, Modifier.weight(1f).padding(horizontal = 8.dp), color = Color.White,
                    fontSize = PresentationTokens.typeMeta.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (canSaveToPhotos()) SuzentIconButton(onClick = {
                    scope.launch { announceSave(context, saveToPhotos(context, file)) }
                }, label = stringResource(R.string.media_save)) {
                    Icon(painterResource(R.drawable.ic_tool_arrow_down_on_square), contentDescription = null,
                        tint = Color.White, modifier = Modifier.size(20.dp))
                }
                SuzentIconButton(onClick = { shareFile(context, file) }, label = stringResource(R.string.media_share, name)) {
                    Icon(painterResource(R.drawable.ic_share), contentDescription = null, tint = Color.White,
                        modifier = Modifier.size(20.dp))
                }
            }
            ImageActions(file, actions, menuAnchor) { actions = false }
        }
    }
}

/** Android 10 and later can add to the gallery without a storage permission; older versions keep Share. */
private fun canSaveToPhotos(): Boolean = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q

private suspend fun saveToPhotos(context: Context, file: File): Boolean = withContext(Dispatchers.IO) {
    if (!canSaveToPhotos()) return@withContext false
    val resolver = context.contentResolver
    val type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension.lowercase()) ?: "image/png"
    val values = ContentValues().apply {
        put(MediaStore.MediaColumns.DISPLAY_NAME, file.name)
        put(MediaStore.MediaColumns.MIME_TYPE, type)
        put(MediaStore.MediaColumns.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/Suzent")
        put(MediaStore.MediaColumns.IS_PENDING, 1)
    }
    val uri = runCatching { resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) }.getOrNull()
        ?: return@withContext false
    runCatching {
        val out = resolver.openOutputStream(uri) ?: error("no output stream")
        out.use { stream -> file.inputStream().use { it.copyTo(stream) } }
        resolver.update(uri, ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
    }.onFailure { resolver.delete(uri, null, null) }.isSuccess
}

private fun announceSave(context: Context, saved: Boolean) {
    Toast.makeText(context, if (saved) R.string.media_saved else R.string.media_save_failed, Toast.LENGTH_SHORT).show()
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

/** Decodes at most about [maxSide] px on the long side, so a large render can't exhaust memory. */
private fun decodeImage(file: File, maxSide: Int = 1600): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(file.path, bounds)
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= maxSide) sample *= 2
    return BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply { inSampleSize = sample })
}

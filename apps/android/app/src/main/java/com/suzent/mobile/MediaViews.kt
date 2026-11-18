package com.suzent.mobile

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.MediaMetadataRetriever
import android.media.MediaPlayer
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.widget.Toast
import android.webkit.MimeTypeMap
import android.widget.MediaController
import android.widget.VideoView
import androidx.compose.foundation.Image
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.semantics.heading
import androidx.compose.foundation.clickable
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.FileProvider
import java.io.File
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
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
    val unique = items.distinctBy { it.id }
    val visual = unique.filter { it.kind == "image" || it.kind == "video" }
    var viewing by remember { mutableStateOf<Int?>(null) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        visual.forEachIndexed { index, item ->
            key(item.id) {
                VisualMediaCard(item, loader, Modifier.fillMaxWidth().height(200.dp)) { viewing = index }
            }
        }
        unique.filter { it.kind != "image" && it.kind != "video" }.forEach { item ->
            key(item.id) { if (item.kind == "file") FileRow(item, loader) else PlayableMediaTile(item, loader) }
        }
    }
    viewing?.let { index -> MediaGalleryViewer(visual, index, loader) { viewing = null } }
}

@Composable
private fun VisualMediaCard(item: MediaItem, loader: suspend (MediaItem) -> File?, modifier: Modifier, viewer: Boolean = false, open: () -> Unit) {
    val preview by produceState<Bitmap?>(null, item.id) {
        value = if (item.kind == "video") videoPreview(item, loader)
            else loader(item)?.let { file -> withContext(Dispatchers.IO) { decodeImage(file, 480) } }
    }
    val openLabel = stringResource(R.string.media_open, item.name)
    Box(modifier.background(if (viewer) Color.Black else MaterialTheme.colorScheme.surface)
        .then(if (viewer) Modifier else Modifier.border(1.dp, suzentLine).clickable(onClickLabel = openLabel, onClick = open))
        .semantics { contentDescription = item.name }, contentAlignment = Alignment.Center) {
        preview?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = if (viewer) ContentScale.Fit else ContentScale.Crop) }
        if (item.kind == "video" && !viewer) Box(Modifier.size(40.dp).background(Color.Black.copy(alpha = .65f), androidx.compose.foundation.shape.CircleShape),
            contentAlignment = Alignment.Center) {
            Icon(painterResource(R.drawable.ic_media_play), null, Modifier.size(20.dp), tint = Color.White)
        } else if (preview == null) Icon(painterResource(R.drawable.ic_tool_folder_open), null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun MediaGalleryViewer(items: List<MediaItem>, initial: Int, loader: suspend (MediaItem) -> File?, close: () -> Unit) {
    if (items.isEmpty()) return
    val pager = rememberPagerState(initialPage = initial.coerceIn(items.indices), pageCount = { items.size })
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        val window = (androidx.compose.ui.platform.LocalView.current.parent as? androidx.compose.ui.window.DialogWindowProvider)?.window
        androidx.compose.runtime.SideEffect { window?.setBackgroundDrawable(android.graphics.drawable.ColorDrawable(android.graphics.Color.BLACK)) }
        HorizontalPager(pager, Modifier.fillMaxSize().background(Color.Black), beyondViewportPageCount = 1, overscrollEffect = null) { page ->
            val item = items[page]
            key(item.id) {
                val state by produceState<MediaState>(MediaState.Loading, item.id) {
                    value = loader(item)?.let { MediaState.Ready(it) } ?: MediaState.Failed
                }
                Column(Modifier.fillMaxSize().background(Color.Black).safeDrawingPadding()) {
                    val ready = (state as? MediaState.Ready)?.file
                    if (item.kind == "image" && ready != null) {
                        ImageViewerContent(ready, item.name, "${page + 1} / ${items.size}", close)
                    } else {
                        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text("${page + 1} / ${items.size}", Modifier.weight(1f).padding(start = 12.dp), color = Color.White)
                            SuzentIconButton(close, stringResource(R.string.media_close)) {
                                Icon(painterResource(R.drawable.ic_close), null, Modifier.size(20.dp), tint = Color.White)
                            }
                        }
                        Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                            if (ready != null && page == pager.settledPage) VideoPlayer(ready, item.name, Modifier.fillMaxSize())
                            else if (ready != null) VisualMediaCard(item, loader, Modifier.fillMaxSize(), viewer = true) {}
                            else MediaNote(stringResource(if (state == MediaState.Failed) R.string.media_unavailable else R.string.media_loading, item.name), Modifier)
                        }
                    }
                }
            }
        }
    }
}

/** What the agent handed over with send_file, gathered under the reply as the turn's deliverable. */
@Composable
fun SentFilesSection(items: List<MediaItem>) {
    if (LocalMediaLoader.current == null) return
    val count = items.distinctBy { it.id }.size
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Icon(painterResource(R.drawable.ic_tool_arrow_down_on_square), null, Modifier.size(14.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(stringResource(R.string.sent_files_heading, count).uppercase(), Modifier.semantics { heading() },
            fontSize = PresentationTokens.typeMeta.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        MediaGallery(items)
    }
}

/** A sent document or archive: fetched only when the user asks to share or open it. */
@Composable
private fun FileRow(item: MediaItem, loader: suspend (MediaItem) -> File?) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember(item.id) { mutableStateOf(false) }
    var failed by remember(item.id) { mutableStateOf(false) }
    val extension = item.name.substringAfterLast('.', "").lowercase().filter { it.isLetterOrDigit() }.take(4)
    val share = {
        busy = true
        failed = false
        scope.launch {
            val file = loader(item)
            busy = false
            if (file == null) failed = true else shareFile(context, file)
        }
        Unit
    }
    val shape = androidx.compose.foundation.shape.RoundedCornerShape(PresentationTokens.radiusControl.dp)
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, shape)
        .border(1.5.dp, MaterialTheme.colorScheme.outline, shape)) {
        Row(Modifier.clickable(enabled = !busy, onClickLabel = stringResource(R.string.media_share, item.name), onClick = share)
            .padding(start = 10.dp, top = 10.dp, bottom = 10.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(40.dp).background(fileCover(extension), androidx.compose.foundation.shape.RoundedCornerShape(PresentationTokens.radiusBadge.dp))
                .border(1.dp, MaterialTheme.colorScheme.outline, androidx.compose.foundation.shape.RoundedCornerShape(PresentationTokens.radiusBadge.dp)),
                contentAlignment = Alignment.Center) {
                Text(if (extension.isEmpty()) "FILE" else ".${extension.uppercase()}", color = MaterialTheme.colorScheme.onSurface, fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold, maxLines = 1)
            }
            Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
                Text(item.name, fontSize = PresentationTokens.typeChat.sp, fontWeight = FontWeight.SemiBold,
                    maxLines = 1, overflow = TextOverflow.MiddleEllipsis)
                Text(stringResource(if (busy) R.string.media_loading_short else R.string.sent_file_tap_to_share),
                    fontSize = PresentationTokens.typeMeta.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
            }
            SuzentIconButton(onClick = share, label = stringResource(R.string.media_share, item.name), enabled = !busy) {
                Icon(painterResource(R.drawable.ic_share), contentDescription = null, modifier = Modifier.size(18.dp))
            }
        }
        if (failed) MediaNote(stringResource(R.string.media_unavailable, item.name), Modifier)
    }
}

/** The desktop artifact covers' colours, from the shared presentation tokens. */
@Composable
private fun fileCover(extension: String): Color {
    val (light, dark) = PresentationTokens.fileCovers[extension] ?: PresentationTokens.fileCovers.getValue("default")
    return Color(if (isSystemInDarkTheme()) dark else light)
}

private fun shareFile(context: Context, file: File) {
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.attachments", file)
    val type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension.lowercase()) ?: "application/octet-stream"
    val send = Intent(Intent.ACTION_SEND).setType(type).putExtra(Intent.EXTRA_STREAM, uri)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    try { context.startActivity(Intent.createChooser(send, file.name)) } catch (_: android.content.ActivityNotFoundException) {}
}

private val videoPreviewSlots = Semaphore(2)

private suspend fun videoPreview(item: MediaItem, loader: suspend (MediaItem) -> File?): Bitmap? =
    videoPreviewSlots.withPermit {
        val file = loader(item) ?: return@withPermit null
        withContext(Dispatchers.IO) {
            val cached = File(file.parentFile, ".video-preview.jpg")
            if (cached.isFile) decodeImage(cached, 320)?.let { return@withContext it }
            val retriever = MediaMetadataRetriever()
            try {
                retriever.setDataSource(file.path)
                val frame = if (Build.VERSION.SDK_INT >= 27) {
                    retriever.getScaledFrameAtTime(0, MediaMetadataRetriever.OPTION_CLOSEST_SYNC, 320, 320)
                } else retriever.getFrameAtTime(0, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
                frame?.let { original ->
                    val factor = 320f / maxOf(original.width, original.height).coerceAtLeast(320)
                    val preview = if (factor < 1f) Bitmap.createScaledBitmap(original,
                        (original.width * factor).toInt().coerceAtLeast(1), (original.height * factor).toInt().coerceAtLeast(1), true)
                        .also { original.recycle() } else original
                    runCatching { cached.outputStream().use { preview.compress(Bitmap.CompressFormat.JPEG, 80, it) } }
                    preview
                }
            } catch (_: Exception) { null }
            finally { runCatching { retriever.release() } }
        }
    }

@Composable
private fun PlayableMediaTile(item: MediaItem, loader: suspend (MediaItem) -> File?) {
    var viewing by remember(item.id) { mutableStateOf(false) }
    val preview by produceState<Bitmap?>(null, item.id) {
        if (item.kind == "video") value = videoPreview(item, loader)
    }
    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
        .border(1.dp, suzentLine).clickable(onClickLabel = stringResource(R.string.media_open, item.name)) { viewing = true }
        .padding(10.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.width(96.dp).height(72.dp).background(if (item.kind == "video") Color.Black else MaterialTheme.colorScheme.background),
            contentAlignment = Alignment.Center) {
            preview?.let { image ->
                Image(image.asImageBitmap(), null, Modifier.matchParentSize(), contentScale = ContentScale.Crop)
            }
            Box(Modifier.size(32.dp).background(Color.Black.copy(alpha = .65f), androidx.compose.foundation.shape.CircleShape),
                contentAlignment = Alignment.Center) {
                Icon(painterResource(R.drawable.ic_media_play), null, Modifier.size(16.dp), tint = Color.White)
            }
        }
        Text(item.name, Modifier.weight(1f), fontWeight = FontWeight.Medium, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Icon(painterResource(R.drawable.ic_chevron_right), null, Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (viewing) Dialog(onDismissRequest = { viewing = false }, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        val state by produceState<MediaState>(MediaState.Loading, item.id) {
            value = loader(item)?.let { MediaState.Ready(it) } ?: MediaState.Failed
        }
        val video = item.kind == "video"
        val foreground = if (video) Color.White else MaterialTheme.colorScheme.onSurface
        Column(Modifier.fillMaxSize().background(if (video) Color.Black else MaterialTheme.colorScheme.background).safeDrawingPadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(item.name, Modifier.weight(1f).padding(start = 12.dp), color = foreground, maxLines = 1, overflow = TextOverflow.Ellipsis)
                SuzentIconButton(onClick = { viewing = false }, label = stringResource(R.string.media_close)) {
                    Icon(painterResource(R.drawable.ic_close), null, Modifier.size(20.dp), tint = foreground)
                }
            }
            Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                when (val current = state) {
                    is MediaState.Ready -> if (item.kind == "video") VideoPlayer(current.file, item.name, Modifier.fillMaxSize())
                        else AudioPlayer(current.file, item.name, Modifier.fillMaxWidth().padding(20.dp))
                    MediaState.Loading -> MediaNote(stringResource(R.string.media_loading, item.name), Modifier)
                    MediaState.Failed -> MediaNote(stringResource(R.string.media_unavailable, item.name), Modifier)
                }
            }
        }
    }
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

@Composable
private fun ImageViewerContent(file: File, name: String, title: String, close: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val image by produceState<Bitmap?>(null, file) { value = withContext(Dispatchers.IO) { decodeImage(file, 2560) } }
    var scale by remember(file) { mutableFloatStateOf(1f) }
    var offset by remember(file) { mutableStateOf(Offset.Zero) }
    var actions by remember(file) { mutableStateOf(false) }
    var menuAnchor by remember(file) { mutableStateOf<Offset?>(null) }
        Box(Modifier.fillMaxSize().background(Color.Black)) {
            image?.let { bitmap ->
                Image(bitmap.asImageBitmap(), contentDescription = name, contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxSize()
                        .recordPressInWindow { menuAnchor = it }
                        .pointerInput(file) {
                            // A one-finger drag only pans once the image is zoomed. Until then it is
                            // left unconsumed so a vertical move is not claimed as a horizontal swipe.
                            awaitEachGesture {
                                val down = awaitFirstDown(requireUnconsumed = false)
                                val lock = SwipeAxisLock()
                                // A drag that starts zoomed pans both ways. The axis lock only applies at 1x.
                                var pinching = scale > 1f
                                do {
                                    val event = awaitPointerEvent()
                                    val pressed = event.changes.filter { it.pressed }
                                    if (pressed.isEmpty()) break
                                    val zoomChange = event.calculateZoom()
                                    val panChange = event.calculatePan()
                                    if (pressed.size > 1 || zoomChange != 1f) pinching = true
                                    val total = pressed.first().position - down.position
                                    val axis = if (pinching) SwipeAxisLock.Axis.HORIZONTAL
                                    else lock.update(total.x.toDouble(), total.y.toDouble())
                                    if (SwipeAxisLock.imageDragYieldsToScroll(scale, pinching, axis)) break
                                    if (pinching || scale > 1f) {
                                        scale = (scale * zoomChange).coerceIn(1f, 6f)
                                        offset = if (scale == 1f) Offset.Zero else offset + panChange
                                        event.changes.forEach { if (it.pressed) it.consume() }
                                    }
                                } while (true)
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
            Row(Modifier.fillMaxWidth().padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                SuzentIconButton(onClick = close, label = stringResource(R.string.media_close)) {
                    Icon(painterResource(R.drawable.ic_close), contentDescription = null, tint = Color.White,
                        modifier = Modifier.size(20.dp))
                }
                Text(title, Modifier.weight(1f).padding(horizontal = 8.dp), color = Color.White,
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
    var controls by remember(file) { mutableStateOf<MediaController?>(null) }
    var prepared by remember(file) { mutableStateOf(false) }
    var playing by remember(file) { mutableStateOf(false) }
    var failed by remember(file) { mutableStateOf(false) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(file, lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_PAUSE) view?.pause() }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); controls?.hide(); view?.stopPlayback() }
    }
    Box(modifier.background(Color.Black).semantics { contentDescription = name }, contentAlignment = Alignment.Center) {
        AndroidView(modifier = Modifier.fillMaxSize(), factory = { context ->
            object : VideoView(context) {
                override fun start() { super.start(); playing = true }
                override fun pause() { super.pause(); playing = false }
            }.apply {
                val controller = MediaController(context)
                controller.setAnchorView(this)
                setMediaController(controller)
                controls = controller
                setOnPreparedListener { prepared = true; seekTo(1) }
                setOnCompletionListener { playing = false }
                setOnErrorListener { _, _, _ -> failed = true; playing = false; true }
                setVideoPath(file.path)
                view = this
            }
        })
        if (failed) MediaNote(stringResource(R.string.media_unavailable, name), Modifier)
        else if (!prepared) androidx.compose.material3.CircularProgressIndicator(color = Color.White, modifier = Modifier.size(32.dp))
        else if (!playing) androidx.compose.material3.IconButton(onClick = { view?.start(); controls?.show() },
            modifier = Modifier.size(64.dp).background(Color.Black.copy(alpha = .65f), androidx.compose.foundation.shape.CircleShape)) {
            Icon(painterResource(R.drawable.ic_media_play), stringResource(R.string.media_play, name), Modifier.size(32.dp), tint = Color.White)
        }
    }
}

@Composable
private fun AudioPlayer(file: File, name: String, modifier: Modifier) {
    var playing by remember(file) { mutableStateOf(false) }
    var prepared by remember(file) { mutableStateOf(false) }
    var failed by remember(file) { mutableStateOf(false) }
    val player = remember(file) { MediaPlayer() }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(player, lifecycle) {
        player.setOnPreparedListener { prepared = true }
        player.setOnCompletionListener { playing = false }
        player.setOnErrorListener { _, _, _ -> failed = true; playing = false; true }
        runCatching { player.setDataSource(file.path); player.prepareAsync() }.onFailure { failed = true }
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_PAUSE && playing) { player.pause(); playing = false }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); player.release() }
    }
    if (failed) {
        MediaNote(stringResource(R.string.media_unavailable, name), modifier)
        return
    }
    Row(modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        SuzentIconButton(onClick = {
            runCatching {
                if (playing) player.pause() else player.start()
                playing = !playing
            }.onFailure { failed = true }
        }, enabled = prepared, label = stringResource(if (playing) R.string.media_pause else R.string.media_play, name)) {
            Icon(painterResource(if (playing) R.drawable.ic_media_pause else R.drawable.ic_media_play), contentDescription = null,
                modifier = Modifier.size(20.dp))
        }
        Text(if (prepared) name else stringResource(R.string.media_loading, name), Modifier.weight(1f),
            fontSize = PresentationTokens.typeMeta.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
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

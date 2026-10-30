package com.suzent.mobile

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AttachmentPanel(model: MobileModel, close: () -> Unit) {
    val context = LocalContext.current
    // Survives the activity being recreated while the camera app is in front.
    var capturePath by rememberSaveable { mutableStateOf<String?>(null) }
    var pendingCamera by rememberSaveable { mutableStateOf<String?>(null) }

    fun finishCapture() {
        val path = capturePath ?: return
        capturePath = null
        val file = File(path)
        if (file.length() > 0) model.attachCaptured(AttachmentFiles.captured(file, file.extension)) else file.delete()
    }
    val media = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(MAX_ATTACHMENTS)) { model.attach(it) }
    val documents = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { model.attach(it) }
    val photo = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { finishCapture() }

    fun startCamera(extension: String) {
        val (file, uri) = AttachmentFiles.capture(context, extension)
        capturePath = file.path
        try { photo.launch(uri) }
        catch (_: ActivityNotFoundException) { capturePath = null; file.delete(); model.error = context.getString(R.string.camera_permission_attach) }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val extension = pendingCamera
        pendingCamera = null
        if (granted && extension != null) startCamera(extension)
        else if (!granted) model.error = context.getString(R.string.camera_permission_attach)
    }
    fun camera(extension: String) {
        if (context.checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) startCamera(extension)
        else { pendingCamera = extension; permission.launch(Manifest.permission.CAMERA) }
    }

    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface)) {
        HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
        Row(Modifier.fillMaxWidth().weight(1f).padding(horizontal = 20.dp, vertical = 24.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            AttachmentOption(R.drawable.ic_attach_media, stringResource(R.string.attach_media), Modifier.weight(1f)) {
                close(); media.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
            }
            AttachmentOption(R.drawable.ic_attach_camera, stringResource(R.string.attach_camera), Modifier.weight(1f)) {
                close(); camera("jpg")
            }
            AttachmentOption(R.drawable.ic_attach_file, stringResource(R.string.attach_file), Modifier.weight(1f)) {
                close(); documents.launch(arrayOf("*/*"))
            }
        }
    }
}

@Composable
private fun AttachmentOption(icon: Int, label: String, modifier: Modifier, onClick: () -> Unit) {
    Column(modifier.clickable(role = Role.Button, onClick = onClick)
        .padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(60.dp).background(MaterialTheme.colorScheme.surface)
            .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline), contentAlignment = Alignment.Center) {
            Icon(painterResource(icon), contentDescription = null, modifier = Modifier.size(28.dp))
        }
        Text(label, color = MaterialTheme.colorScheme.onSurface, fontSize = PresentationTokens.typeCaption.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
    }
}

@Composable
fun PendingAttachmentStrip(model: MobileModel) {
    if (model.attachments.isEmpty()) return
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        model.attachments.forEach { attachment ->
            val remove = stringResource(R.string.attachment_remove, attachment.name)
            AttachmentChip(attachment.name, attachment.mimeType, onRemove = { model.removeAttachment(attachment) }, removeLabel = remove,
                enabled = !model.busy, thumbnail = attachment.file.takeIf { attachment.mimeType.startsWith("image/") })
        }
    }
}

@Composable
fun AttachmentChip(name: String, mimeType: String, onRemove: (() -> Unit)? = null, removeLabel: String = "", enabled: Boolean = true,
                   color: Color = MaterialTheme.colorScheme.onSurface, thumbnail: File? = null) {
    Row(Modifier.border(PresentationTokens.borderWidth.dp, color).padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (thumbnail != null) AttachmentThumbnail(thumbnail)
        else Icon(painterResource(attachmentIcon(mimeType)), contentDescription = null, tint = color, modifier = Modifier.size(16.dp))
        Text(name, color = color, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 180.dp))
        if (onRemove != null) Box(Modifier.clickable(enabled = enabled, onClickLabel = removeLabel, role = Role.Button, onClick = onRemove)
            .semantics { contentDescription = removeLabel }.padding(4.dp)) {
            Icon(painterResource(R.drawable.ic_close), contentDescription = null, tint = color, modifier = Modifier.size(14.dp))
        }
    }
}

@Composable
private fun AttachmentThumbnail(file: File) {
    val image by produceState<ImageBitmap?>(null, file) { value = withContext(Dispatchers.IO) { decodeThumbnail(file, 84) } }
    Box(Modifier.size(28.dp).background(MaterialTheme.colorScheme.surfaceVariant)) {
        image?.let { Image(it, contentDescription = null, modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
    }
}

private fun decodeThumbnail(file: File, target: Int): ImageBitmap? = runCatching {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(file.path, bounds)
    val options = BitmapFactory.Options().apply { inSampleSize = (minOf(bounds.outWidth, bounds.outHeight) / target).coerceAtLeast(1) }
    BitmapFactory.decodeFile(file.path, options)?.asImageBitmap()
}.getOrNull()

private fun attachmentIcon(mimeType: String): Int = when {
    mimeType.startsWith("image/") -> R.drawable.ic_attach_media
    mimeType.startsWith("video/") -> R.drawable.ic_video
    else -> R.drawable.ic_attach_file
}

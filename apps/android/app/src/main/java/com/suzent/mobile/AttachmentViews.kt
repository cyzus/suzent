package com.suzent.mobile

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.io.File

@Composable
fun AttachButton(model: MobileModel, enabled: Boolean) {
    val context = LocalContext.current
    var menu by remember { mutableStateOf(false) }
    // Survives the activity being recreated while the camera app is in front.
    var capturePath by rememberSaveable { mutableStateOf<String?>(null) }
    var pendingCamera by rememberSaveable { mutableStateOf<String?>(null) }

    fun finishCapture() {
        val path = capturePath ?: return
        capturePath = null
        val file = File(path)
        // Some camera apps report failure after saving a video, so trust the file.
        if (file.length() > 0) model.attachCaptured(AttachmentFiles.captured(file, file.extension)) else file.delete()
    }
    val media = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(MAX_ATTACHMENTS)) { model.attach(it) }
    val documents = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { model.attach(it) }
    val photo = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { finishCapture() }
    val video = rememberLauncherForActivityResult(ActivityResultContracts.CaptureVideo()) { finishCapture() }

    fun startCamera(extension: String) {
        val (file, uri) = AttachmentFiles.capture(context, extension)
        capturePath = file.path
        try { if (extension == "jpg") photo.launch(uri) else video.launch(uri) }
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

    Box {
        IconButton(onClick = { menu = true }, enabled = enabled, modifier = Modifier.size(PresentationTokens.controlHeight.dp)) {
            Icon(painterResource(R.drawable.ic_attach), contentDescription = stringResource(R.string.attach), tint = MaterialTheme.colorScheme.onSurface)
        }
        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
            DropdownMenuItem(text = { Text(stringResource(R.string.attach_photo)) }, onClick = { menu = false; camera("jpg") })
            DropdownMenuItem(text = { Text(stringResource(R.string.attach_video)) }, onClick = { menu = false; camera("mp4") })
            DropdownMenuItem(text = { Text(stringResource(R.string.attach_media)) }, onClick = {
                menu = false
                media.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
            })
            DropdownMenuItem(text = { Text(stringResource(R.string.attach_file)) }, onClick = { menu = false; documents.launch(arrayOf("*/*")) })
        }
    }
}

@Composable
fun PendingAttachmentStrip(model: MobileModel) {
    if (model.attachments.isEmpty()) return
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        model.attachments.forEach { attachment ->
            val remove = stringResource(R.string.attachment_remove, attachment.name)
            AttachmentChip(attachment.name, attachment.mimeType, onRemove = { model.removeAttachment(attachment) }, removeLabel = remove,
                enabled = !model.busy)
        }
    }
}

@Composable
fun AttachmentChip(name: String, mimeType: String, onRemove: (() -> Unit)? = null, removeLabel: String = "", enabled: Boolean = true,
                   color: Color = MaterialTheme.colorScheme.onSurface) {
    Row(Modifier.border(PresentationTokens.borderWidth.dp, color).padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(attachmentGlyph(mimeType), color = color, fontSize = 13.sp)
        Text(name, color = color, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 180.dp))
        if (onRemove != null) Text("✕", color = color, fontSize = 13.sp,
            modifier = Modifier.clickable(enabled = enabled, onClickLabel = removeLabel, onClick = onRemove))
    }
}

private fun attachmentGlyph(mimeType: String): String = when {
    mimeType.startsWith("image/") -> "▣"
    mimeType.startsWith("video/") -> "▶"
    else -> "▤"
}

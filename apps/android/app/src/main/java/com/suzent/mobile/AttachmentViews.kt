package com.suzent.mobile

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AttachButton(model: MobileModel, enabled: Boolean) {
    val context = LocalContext.current
    var menu by rememberSaveable { mutableStateOf(false) }
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

    SuzentTextButton(onClick = { menu = true }, enabled = enabled,
        modifier = Modifier.size(PresentationTokens.controlHeight.dp)) {
        Icon(painterResource(R.drawable.ic_attach), contentDescription = stringResource(R.string.attach), tint = MaterialTheme.colorScheme.onSurface)
    }
    if (menu) {
        ModalBottomSheet(onDismissRequest = { menu = false },
            containerColor = Color.Transparent, shape = RectangleShape, dragHandle = null,
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
            Column(Modifier.fillMaxWidth().padding(PresentationTokens.spacePage.dp)
                .background(MaterialTheme.colorScheme.surface)
                .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)
                .padding(PresentationTokens.spacePage.dp),
                verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceMedium.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.attach),
                        modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                    SuzentTextButton(onClick = { menu = false }) {
                        Text(stringResource(R.string.dismiss))
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(PresentationTokens.spaceMedium.dp)) {
                    AttachmentOption(R.drawable.ic_attach_camera, stringResource(R.string.attach_camera), Modifier.weight(1f)) {
                        menu = false; camera("jpg")
                    }
                    AttachmentOption(R.drawable.ic_attach_media, stringResource(R.string.attach_media), Modifier.weight(1f)) {
                        menu = false
                        media.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
                    }
                    AttachmentOption(R.drawable.ic_attach_file, stringResource(R.string.attach_file), Modifier.weight(1f)) {
                        menu = false; documents.launch(arrayOf("*/*"))
                    }
                }
            }
        }
    }
}

@Composable
private fun AttachmentOption(icon: Int, label: String, modifier: Modifier, onClick: () -> Unit) {
    val outline = MaterialTheme.colorScheme.outline
    val shadow = PresentationTokens.shadowOffset.dp
    Column(modifier.padding(end = shadow, bottom = shadow)
        .drawBehind { drawRect(outline, topLeft = Offset(shadow.toPx(), shadow.toPx()), size = size) }
        .background(MaterialTheme.colorScheme.surface)
        .border(PresentationTokens.borderWidth.dp, outline)
        .clickable(role = Role.Button, onClick = onClick)
        .heightIn(min = 96.dp).padding(horizontal = 8.dp, vertical = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterVertically)) {
        Icon(painterResource(icon), contentDescription = null, modifier = Modifier.size(28.dp))
        Text(label, fontSize = PresentationTokens.typeCaption.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
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

package com.suzent.mobile

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import android.webkit.MimeTypeMap
import androidx.core.content.FileProvider
import java.io.File
import java.util.UUID

const val MAX_ATTACHMENTS = 10

data class PendingAttachment(val file: File, val name: String, val mimeType: String)

object AttachmentFiles {
    private fun directory(context: Context): File = File(context.cacheDir, "attachments").apply { mkdirs() }

    // Picked content is copied first: a content URI's size is often unknown and its
    // grant can lapse, while the upload must declare its length and may be retried.
    fun copy(context: Context, uri: Uri): PendingAttachment {
        val resolver = context.contentResolver
        val mimeType = resolver.getType(uri) ?: "application/octet-stream"
        val displayName = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        }
        val extension = MimeTypeMap.getSingleton().getExtensionFromMimeType(mimeType)
        val name = displayName?.takeIf { it.isNotBlank() } ?: ("attachment" + (extension?.let { ".$it" } ?: ""))
        val target = File(directory(context), UUID.randomUUID().toString())
        requireNotNull(resolver.openInputStream(uri)).use { input -> target.outputStream().use { input.copyTo(it) } }
        return PendingAttachment(target, name, mimeType)
    }

    fun capture(context: Context, extension: String): Pair<File, Uri> {
        val file = File(directory(context), "${UUID.randomUUID()}.$extension")
        return file to FileProvider.getUriForFile(context, "${context.packageName}.attachments", file)
    }

    fun captured(file: File, extension: String): PendingAttachment {
        val mimeType = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension) ?: "application/octet-stream"
        val stamp = java.text.SimpleDateFormat("yyyyMMdd-HHmmss", java.util.Locale.US).format(java.util.Date())
        return PendingAttachment(file, "camera-$stamp.$extension", mimeType)
    }

    fun clear(context: Context) { directory(context).listFiles()?.forEach { it.delete() } }
}

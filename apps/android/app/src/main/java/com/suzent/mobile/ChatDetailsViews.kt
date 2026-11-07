package com.suzent.mobile

import android.content.Intent
import android.webkit.MimeTypeMap
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

private fun permissionModeLabel(mode: String): Int = when (mode) {
    "auto" -> R.string.permission_mode_auto
    "full_access" -> R.string.full_access
    else -> R.string.permission_mode_ask
}

private fun permissionModeDescription(mode: String): Int = when (mode) {
    "auto" -> R.string.permission_mode_auto_detail
    "full_access" -> R.string.permission_mode_full_detail
    else -> R.string.permission_mode_ask_detail
}

private fun statusLabel(status: String): Int? = when (status) {
    "active" -> R.string.status_active
    "paused" -> R.string.status_paused
    "completed" -> R.string.status_completed
    "running" -> R.string.status_running
    "queued" -> R.string.status_queued
    "failed" -> R.string.status_failed
    "cancelled" -> R.string.status_cancelled
    "in_progress" -> R.string.status_in_progress
    "blocked" -> R.string.status_blocked
    "pending" -> R.string.status_pending
    else -> null
}

private fun statusColor(status: String): Color = when (status) {
    "completed" -> Color(0xFF16A34A)
    "in_progress", "running", "queued", "active" -> Color(0xFF2563EB)
    "blocked", "waiting", "paused" -> Color(0xFFD97706)
    "failed", "cancelled" -> Color(0xFFDC2626)
    else -> Color(0xFF9CA3AF)
}

@Composable
private fun statusText(status: String): String =
    statusLabel(status)?.let { stringResource(it) } ?: status.replace('_', ' ').replaceFirstChar { it.uppercase() }

/** The phone's version of the desktop chat side panel, opened from the conversation header. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatDetailsSheet(model: MobileModel, chat: Chat, dismiss: () -> Unit) {
    // The open folder path; null shows the details overview.
    var folder by remember { mutableStateOf<String?>(null) }
    BackHandler(enabled = folder != null) { folder = folder?.takeIf { it.isNotEmpty() }?.let(::workspaceParentPath) }
    ModalBottomSheet(onDismissRequest = dismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        shape = RectangleShape, containerColor = MaterialTheme.colorScheme.surface) {
        Column(Modifier.fillMaxWidth().padding(bottom = PresentationTokens.spacePage.dp)) {
            val current = folder
            if (current == null) DetailsOverview(model, chat, openFiles = { folder = "" }, close = dismiss)
            else WorkspaceFolder(model, chat.id, current, open = { folder = it },
                up = { folder = if (current.isEmpty()) null else workspaceParentPath(current) }, close = dismiss)
        }
    }
}

@Composable
private fun SheetHeading(text: String) {
    Text(text.uppercase(java.util.Locale.getDefault()), Modifier.padding(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 6.dp),
        fontWeight = FontWeight.ExtraBold, fontSize = PresentationTokens.typeSidebarSection.sp, letterSpacing = 1.6.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun StatusRow(text: String, status: String, detail: String? = null, strike: Boolean = false, onClick: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp)
        .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
        .padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).background(statusColor(status), CircleShape))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(text, maxLines = 2, overflow = TextOverflow.Ellipsis,
                textDecoration = if (strike) TextDecoration.LineThrough else null,
                color = if (strike) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface)
            if (detail != null) Text(detail, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (onClick != null) Icon(painterResource(R.drawable.ic_chevron_right), contentDescription = null,
            modifier = Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun DetailsOverview(model: MobileModel, chat: Chat, openFiles: () -> Unit, close: () -> Unit) {
    var details by remember(chat.id) { mutableStateOf<ChatDetails?>(null) }
    var failed by remember(chat.id) { mutableStateOf(false) }
    var attempt by remember { mutableIntStateOf(0) }
    var savingMode by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val modeError = stringResource(R.string.request_error)
    LaunchedEffect(chat.id, attempt) {
        failed = false
        try { details = model.chatDetails(chat.id) }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { failed = true }
    }
    Text(stringResource(R.string.chat_details), Modifier.padding(horizontal = 16.dp),
        style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
    val loaded = details
    if (loaded == null) {
        Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
            if (failed) SuzentTextButton(onClick = { attempt++ }) { Text(stringResource(R.string.chat_details_retry)) }
            else CircularProgressIndicator()
        }
        return
    }
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
        SheetHeading(stringResource(R.string.approval_mode))
        val mode = loaded.permissionMode
        mode.available.forEach { option ->
            Row(Modifier.fillMaxWidth().heightIn(min = 44.dp)
                .clickable(enabled = mode.canChange && !savingMode && option != mode.mode, role = Role.RadioButton) {
                    savingMode = true
                    scope.launch {
                        try {
                            val saved = model.setPermissionMode(chat.id, option)
                            details = loaded.copy(permissionMode = mode.copy(mode = saved))
                        } catch (cancelled: CancellationException) { throw cancelled }
                        catch (_: Exception) { model.error = modeError }
                        finally { savingMode = false }
                    }
                }.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected = option == mode.mode, onClick = null, enabled = mode.canChange || option == mode.mode,
                    modifier = Modifier.padding(horizontal = 8.dp))
                Text(stringResource(permissionModeLabel(option)), fontWeight = FontWeight.SemiBold)
            }
        }
        Text(stringResource(permissionModeDescription(mode.mode)) +
            if (mode.canChange) "" else " " + stringResource(R.string.approval_mode_locked),
            Modifier.padding(horizontal = 16.dp, vertical = 4.dp), style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)

        loaded.context?.let { context ->
            HorizontalDivider(Modifier.padding(top = 12.dp), color = MaterialTheme.colorScheme.outlineVariant)
            SheetHeading(stringResource(R.string.context_usage))
            Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                LinearProgressIndicator(progress = { context.percent / 100f }, modifier = Modifier.fillMaxWidth(),
                    color = MaterialTheme.colorScheme.onSurface, trackColor = MaterialTheme.colorScheme.outlineVariant)
                Text(stringResource(R.string.context_usage_detail, context.percent, "%,d".format(context.limit)),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        if (loaded.goal != null || loaded.tasks.isNotEmpty()) {
            HorizontalDivider(Modifier.padding(top = 12.dp), color = MaterialTheme.colorScheme.outlineVariant)
            SheetHeading(stringResource(R.string.tasks))
            loaded.goal?.let { StatusRow(it.objective, it.status, detail = statusText(it.status)) }
            loaded.tasks.forEach { task ->
                StatusRow(if (task.status == "in_progress") task.activeForm ?: task.title else task.title, task.status,
                    strike = task.status == "completed")
            }
        }

        if (loaded.agents.isNotEmpty()) {
            HorizontalDivider(Modifier.padding(top = 12.dp), color = MaterialTheme.colorScheme.outlineVariant)
            SheetHeading(stringResource(R.string.background_tasks))
            loaded.agents.forEach { agent ->
                val child = agent.chatId
                StatusRow(agent.description, agent.status, detail = statusText(agent.status),
                    onClick = child?.let { id -> { close(); model.open(model.chats.firstOrNull { it.id == id } ?: Chat(id, agent.description, false, emptyList())) } })
            }
        }

        loaded.memory?.takeIf { it.recalled.isNotEmpty() || it.saved.isNotEmpty() }?.let { memory ->
            HorizontalDivider(Modifier.padding(top = 12.dp), color = MaterialTheme.colorScheme.outlineVariant)
            SheetHeading(stringResource(R.string.memory))
            (memory.recalled + memory.saved).forEach { item ->
                Text(item.content, Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
                    style = MaterialTheme.typography.bodyMedium)
            }
        }

        if (loaded.files) {
            HorizontalDivider(Modifier.padding(top = 12.dp), color = MaterialTheme.colorScheme.outlineVariant)
            Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clickable(role = Role.Button, onClick = openFiles)
                .padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(painterResource(R.drawable.ic_tool_folder), contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.workspace_files), fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.workspace_files_detail), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Icon(painterResource(R.drawable.ic_chevron_right), contentDescription = null, modifier = Modifier.size(16.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun WorkspaceFolder(model: MobileModel, chatId: String, path: String, open: (String) -> Unit, up: () -> Unit, close: () -> Unit) {
    var listing by remember(path) { mutableStateOf<WorkspaceListing?>(null) }
    var failed by remember(path) { mutableStateOf(false) }
    var attempt by remember { mutableIntStateOf(0) }
    var opening by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val openError = stringResource(R.string.workspace_open_failed)
    LaunchedEffect(path, attempt) {
        failed = false
        try { listing = model.workspaceFiles(chatId, path) }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { failed = true }
    }
    Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        SuzentIconButton(onClick = up, label = stringResource(R.string.back)) {
            Icon(painterResource(R.drawable.ic_chat_back), contentDescription = null, modifier = Modifier.size(20.dp))
        }
        Text(if (path.isEmpty()) stringResource(R.string.workspace_files) else workspaceDisplayName(path), Modifier.weight(1f),
            style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        SuzentIconButton(onClick = close, label = stringResource(R.string.dismiss)) {
            Icon(painterResource(R.drawable.ic_close), contentDescription = null, modifier = Modifier.size(20.dp))
        }
    }
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
    val loaded = listing
    when {
        loaded == null -> Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
            if (failed) SuzentTextButton(onClick = { attempt++ }) { Text(stringResource(R.string.chat_details_retry)) }
            else CircularProgressIndicator()
        }
        loaded.entries.isEmpty() -> Text(stringResource(R.string.workspace_empty), Modifier.fillMaxWidth().padding(32.dp),
            color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        else -> Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
            loaded.entries.forEach { entry ->
                val child = workspaceChildPath(path, entry.name)
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(enabled = opening == null, role = Role.Button) {
                    if (entry.isDir) open(child)
                    else {
                        opening = child
                        scope.launch {
                            try {
                                val file = model.downloadWorkspaceFile(chatId, child)
                                val uri = FileProvider.getUriForFile(context, "${context.packageName}.attachments", file)
                                val type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension.lowercase()) ?: "*/*"
                                val view = Intent(Intent.ACTION_VIEW).setDataAndType(uri, type).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                context.startActivity(Intent.createChooser(view, file.name))
                            } catch (cancelled: CancellationException) { throw cancelled }
                            catch (_: Exception) { model.error = openError }
                            finally { opening = null }
                        }
                    }
                }.padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(painterResource(if (entry.isDir) R.drawable.ic_tool_folder else R.drawable.ic_tool_document_text),
                        contentDescription = null, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(12.dp))
                    Text(entry.name, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    when {
                        opening == child -> CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                        entry.isDir -> Icon(painterResource(R.drawable.ic_chevron_right), contentDescription = null,
                            modifier = Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        else -> Text(android.text.format.Formatter.formatShortFileSize(context, entry.size),
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f))
            }
            if (loaded.truncated) Text(stringResource(R.string.workspace_truncated), Modifier.padding(16.dp),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

package com.suzent.mobile

import android.content.Intent
import android.webkit.MimeTypeMap
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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

@Composable
private fun statusText(status: String): String =
    statusLabel(status)?.let { stringResource(it) } ?: status.replace('_', ' ').replaceFirstChar { it.uppercase() }

/** The desktop side panel's square status marker: blue while working, red on failure, yellow when held up. */
@Composable
private fun StatusMarker(status: String) {
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val base = Modifier.size(8.dp)
    when (status) {
        "in_progress", "running", "queued", "active" -> Box(base.background(suzentLink))
        "failed", "cancelled" -> Box(base.background(MaterialTheme.colorScheme.error))
        "blocked", "waiting", "paused" -> Box(base.background(Color(PresentationTokens.yellow)).border(1.dp, MaterialTheme.colorScheme.outline))
        "completed" -> Box(base.background(muted.copy(alpha = 0.5f)))
        else -> Box(base.border(1.dp, muted))
    }
}

@Composable
private fun DetailsHeading(text: String) {
    Text(text.uppercase(java.util.Locale.getDefault()), Modifier.padding(start = 16.dp, end = 16.dp, top = 20.dp, bottom = 6.dp),
        fontWeight = FontWeight.ExtraBold, fontSize = PresentationTokens.typeSidebarSection.sp, letterSpacing = 1.6.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun RowDivider() = HorizontalDivider(color = suzentRowDivider)

@Composable
private fun DetailsMessage(text: String, retry: (() -> Unit)? = null) {
    Column(Modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(text, fontSize = PresentationTokens.typeCaption.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        if (retry != null) Box(Modifier.border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)
            .clickable(role = Role.Button, onClick = retry).heightIn(min = 40.dp).padding(horizontal = 16.dp), contentAlignment = Alignment.Center) {
            Text(stringResource(R.string.details_retry), fontWeight = FontWeight.SemiBold)
        }
    }
}

/** The phone's version of the desktop chat side panel, styled like the model and project pickers. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatDetailsSheet(model: MobileModel, chat: Chat, dismiss: () -> Unit) {
    // The open folder path; null shows the details overview.
    var folder by remember { mutableStateOf<String?>(null) }
    val up = { folder = folder?.takeIf { it.isNotEmpty() }?.let(::workspaceParentPath) }
    BackHandler(enabled = folder != null, onBack = up)
    val outline = MaterialTheme.colorScheme.outline
    val shadowColor = suzentShadow
    ModalBottomSheet(onDismissRequest = dismiss, containerColor = Color.Transparent,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), dragHandle = null, shape = RectangleShape) {
        Column(Modifier.fillMaxWidth().padding(16.dp).drawBehind {
            val offset = PresentationTokens.shadowOffsetHeavy.dp.toPx()
            drawRect(shadowColor, topLeft = Offset(offset, offset), size = size)
        }.background(MaterialTheme.colorScheme.surface).border(2.dp, outline)) {
            val current = folder
            Row(Modifier.fillMaxWidth().background(Color.Black).padding(start = if (current == null) 16.dp else 0.dp),
                verticalAlignment = Alignment.CenterVertically) {
                if (current != null) SuzentIconButton(onClick = up, label = stringResource(R.string.back)) {
                    Icon(painterResource(R.drawable.ic_chat_back), contentDescription = null, tint = Color.White, modifier = Modifier.size(20.dp))
                }
                Text(when {
                    current == null -> stringResource(R.string.chat_details)
                    current.isEmpty() -> stringResource(R.string.workspace_files)
                    else -> workspaceDisplayName(current)
                }, Modifier.weight(1f), fontFamily = FontFamily.Monospace, fontSize = 15.sp, fontWeight = FontWeight.Bold,
                    color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
                SuzentIconButton(onClick = dismiss, label = stringResource(R.string.dismiss)) {
                    Icon(painterResource(R.drawable.ic_close), contentDescription = null, tint = Color.White, modifier = Modifier.size(20.dp))
                }
            }
            Column(Modifier.fillMaxWidth().heightIn(max = 560.dp)) {
                if (current == null) DetailsOverview(model, chat, openFiles = { folder = "" }, close = dismiss)
                else WorkspaceFolder(model, chat.id, current, open = { folder = it })
            }
        }
    }
}

@Composable
private fun StatusRow(text: String, status: String, detail: String? = null, done: Boolean = false, onClick: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp)
        .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
        .padding(horizontal = 16.dp, vertical = PresentationTokens.spaceRow.dp), verticalAlignment = Alignment.CenterVertically) {
        StatusMarker(status)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(text, fontSize = PresentationTokens.typeChat.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                textDecoration = if (done) TextDecoration.LineThrough else null,
                color = if (done) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface)
            if (detail != null) Text(detail, fontSize = PresentationTokens.typeMeta.sp, fontWeight = FontWeight.Medium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
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
    val loaded = details
    if (loaded == null) {
        if (failed) DetailsMessage(stringResource(R.string.chat_details_failed)) { attempt++ }
        else Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        return
    }
    val outline = MaterialTheme.colorScheme.outline
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(bottom = PresentationTokens.spaceLarge.dp)) {
        DetailsHeading(stringResource(R.string.approval_mode))
        val mode = loaded.permissionMode
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp).border(PresentationTokens.borderWidth.dp, outline)
            .alpha(if (mode.canChange) 1f else DisabledAlpha)) {
            mode.available.forEachIndexed { index, option ->
                val chosen = option == mode.mode
                if (index > 0) Box(Modifier.width(PresentationTokens.borderWidth.dp).height(40.dp).background(outline))
                Box(Modifier.weight(1f).heightIn(min = 40.dp)
                    .background(if (chosen) Color(PresentationTokens.yellow) else MaterialTheme.colorScheme.surface)
                    .selectable(selected = chosen, enabled = mode.canChange && !savingMode, role = Role.RadioButton) {
                        if (chosen) return@selectable
                        savingMode = true
                        scope.launch {
                            try {
                                val saved = model.setPermissionMode(chat.id, option)
                                details = loaded.copy(permissionMode = mode.copy(mode = saved))
                            } catch (cancelled: CancellationException) { throw cancelled }
                            catch (_: Exception) { model.error = modeError }
                            finally { savingMode = false }
                        }
                    }, contentAlignment = Alignment.Center) {
                    Text(stringResource(permissionModeLabel(option)), fontSize = PresentationTokens.typeCaption.sp, maxLines = 1,
                        fontWeight = if (chosen) FontWeight.Bold else FontWeight.Medium,
                        color = if (chosen) Color.Black else MaterialTheme.colorScheme.onSurface)
                }
            }
        }
        Text(stringResource(permissionModeDescription(mode.mode)) +
            if (mode.canChange) "" else " " + stringResource(R.string.approval_mode_locked),
            Modifier.padding(start = 16.dp, end = 16.dp, top = 8.dp), fontSize = PresentationTokens.typeLabel.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant)

        loaded.context?.let { context ->
            DetailsHeading(stringResource(R.string.context_usage))
            Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.fillMaxWidth().height(10.dp).border(PresentationTokens.borderWidth.dp, outline)) {
                    Box(Modifier.fillMaxWidth(context.percent / 100f).fillMaxHeight().background(MaterialTheme.colorScheme.onSurface))
                }
                Text(stringResource(R.string.context_usage_detail, context.percent, "%,d".format(context.limit)),
                    fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        if (loaded.goal != null || loaded.tasks.isNotEmpty()) {
            DetailsHeading(stringResource(R.string.tasks))
            loaded.goal?.let { goal ->
                Text(goal.objective, Modifier.padding(horizontal = 16.dp), fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.Bold)
                Text(statusText(goal.status), Modifier.padding(horizontal = 16.dp), fontSize = PresentationTokens.typeMeta.sp,
                    fontWeight = FontWeight.Medium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            loaded.tasks.forEach { task ->
                StatusRow(if (task.status == "in_progress") task.activeForm ?: task.title else task.title, task.status,
                    done = task.status == "completed")
                RowDivider()
            }
        }

        if (loaded.agents.isNotEmpty()) {
            DetailsHeading(stringResource(R.string.background_tasks))
            loaded.agents.forEach { agent ->
                val child = agent.chatId
                StatusRow(agent.description, agent.status, detail = statusText(agent.status),
                    onClick = child?.let { id -> { close(); model.open(model.chats.firstOrNull { it.id == id } ?: Chat(id, agent.description, false, emptyList())) } })
                RowDivider()
            }
        }

        loaded.memory?.takeIf { it.recalled.isNotEmpty() || it.saved.isNotEmpty() }?.let { memory ->
            DetailsHeading(stringResource(R.string.memory))
            (memory.recalled + memory.saved).forEach { item ->
                Text(item.content, Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = PresentationTokens.spaceRow.dp),
                    fontSize = PresentationTokens.typeChat.sp)
                RowDivider()
            }
        }

        if (loaded.files) {
            DetailsHeading(stringResource(R.string.workspace_files))
            Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button, onClick = openFiles)
                .padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(painterResource(R.drawable.ic_tool_folder), contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.workspace_project), fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.workspace_files_detail), fontSize = PresentationTokens.typeMeta.sp,
                        fontWeight = FontWeight.Medium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Icon(painterResource(R.drawable.ic_chevron_right), contentDescription = null, modifier = Modifier.size(16.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            RowDivider()
        }
    }
}

@Composable
private fun WorkspaceFolder(model: MobileModel, chatId: String, path: String, open: (String) -> Unit) {
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
    val loaded = listing
    when {
        loaded == null -> if (failed) DetailsMessage(stringResource(R.string.workspace_failed)) { attempt++ }
            else Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        loaded.entries.isEmpty() -> DetailsMessage(stringResource(R.string.workspace_empty))
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
                    Text(entry.name, Modifier.weight(1f), fontSize = PresentationTokens.typeChat.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    when {
                        opening == child -> CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                        entry.isDir -> Icon(painterResource(R.drawable.ic_chevron_right), contentDescription = null,
                            modifier = Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        else -> Text(android.text.format.Formatter.formatShortFileSize(context, entry.size),
                            fontSize = PresentationTokens.typeMeta.sp, fontWeight = FontWeight.Medium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                RowDivider()
            }
            if (loaded.truncated) Text(stringResource(R.string.workspace_truncated), Modifier.padding(16.dp),
                fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

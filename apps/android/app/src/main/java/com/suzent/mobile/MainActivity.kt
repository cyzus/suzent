package com.suzent.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    private val model: MobileModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { SuzentTheme { MobileScreen(model) } }
    }
    override fun onStart() { super.onStart(); model.setForeground(true) }
    override fun onStop() { model.setForeground(false); super.onStop() }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MobileScreen(model: MobileModel) {
    var showAccess by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(model.connected) { if (!model.connected) showAccess = false }
    Scaffold(topBar = {
        Column(Modifier.statusBarsPadding()) {
            SuzentWordmark()
            HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
            if (model.connected) {
                Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SuzentAction(stringResource(R.string.chats), { model.selected = null; showAccess = false },
                        enabled = !model.streaming && !model.busy, compact = true)
                    Spacer(Modifier.weight(1f))
                    SuzentAction(stringResource(R.string.access), { showAccess = !showAccess }, compact = true)
                    SuzentAction(stringResource(R.string.refresh), model::refresh, compact = true)
                }
            }
        }
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).imePadding().padding(horizontal = 16.dp)) {
            model.error?.let { message ->
                Card(Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                    Text(message, Modifier.padding(12.dp))
                    TextButton(onClick = { model.error = null }) { Text(stringResource(R.string.dismiss)) }
                }
            }
            when {
                !model.connected -> PairingView(model)
                showAccess -> AccessView(model)
                model.selected != null -> Conversation(model)
                else -> ChatList(model)
            }
        }
    }
}

@Composable
private fun ChatList(model: MobileModel) {
    LazyColumn {
        item {
            Text(stringResource(R.string.chats), Modifier.padding(vertical = 12.dp), style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            SuzentAction(stringResource(R.string.new_chat), model::create, prominent = true,
                enabled = !model.busy && model.device?.permissions?.createChats == true)
            Spacer(Modifier.height(16.dp))
        }
        items(model.chats, key = { it.id }) { chat ->
            Row(Modifier.fillMaxWidth().clickable { model.open(chat) }.heightIn(min = 72.dp).padding(vertical = 16.dp),
                horizontalArrangement = Arrangement.SpaceBetween) {
                Text(chat.title, modifier = Modifier.weight(1f), fontWeight = FontWeight.Bold)
                if (chat.running) CircularProgressIndicator(Modifier.size(20.dp))
            }
            HorizontalDivider()

        }
    }
}

@Composable
private fun AccessView(model: MobileModel) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceLarge.dp)) {
        model.device?.let { ClientPermissionsView(it, model.origin) }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(stringResource(R.string.enable_node), modifier = Modifier.weight(1f))
            Switch(checked = model.nodeEnabled, onCheckedChange = model::toggleNode)
        }
        Text(model.nodeStatus, style = MaterialTheme.typography.bodySmall)
        TextButton(onClick = model::forget, enabled = !model.busy) { Text(stringResource(R.string.forget)) }
        Text(stringResource(R.string.revoke_help), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun ColumnScope.Conversation(model: MobileModel) {
    val chat = model.selected ?: return
    LaunchedEffect(chat.id) { model.watchApprovals(chat.id) }
    val liveTools = model.liveParts.filter { it.type == "tool" }.map { it.toolCallId }.toSet()
    val messages = remember(chat.messages, liveTools) { presentMessages(chat.messages, liveTools) }
    LazyColumn(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceLarge.dp)) {
        item { Text(chat.title, style = MaterialTheme.typography.titleLarge) }
        items(messages) { message -> MessageView(message) }
        if (model.streaming || model.liveParts.isNotEmpty()) item {
            if (model.liveParts.isEmpty()) Text(stringResource(R.string.working), color = MaterialTheme.colorScheme.onSurfaceVariant)
            else ActivityContent(model.liveParts, live = model.streaming)
        }
        item { ApprovalCards(model) }
    }
    Column(Modifier.fillMaxWidth().padding(vertical = 16.dp)
        .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp), horizontalAlignment = androidx.compose.ui.Alignment.End) {
        BasicTextField(value = model.draft, onValueChange = { model.draft = it },
            modifier = Modifier.fillMaxWidth(), minLines = 2, maxLines = 6,
            textStyle = MaterialTheme.typography.bodyLarge.copy(color = MaterialTheme.colorScheme.onSurface),
            cursorBrush = androidx.compose.ui.graphics.SolidColor(MaterialTheme.colorScheme.primary),
            decorationBox = { inner ->
                Box {
                    if (model.draft.isEmpty()) Text(stringResource(R.string.message), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    inner()
                }
            })
        if (model.streaming || chat.running) {
            SuzentAction(stringResource(R.string.stop), model::stop, prominent = true,
                enabled = model.device?.permissions?.stop == true, compact = true)
        } else {
            SuzentAction(stringResource(R.string.send), model::send, prominent = true,
                enabled = !model.busy && model.draft.isNotBlank() && model.device?.permissions?.send == true, compact = true)
        }
    }
}

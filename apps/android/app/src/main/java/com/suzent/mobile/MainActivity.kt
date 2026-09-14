package com.suzent.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.*
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
        TopAppBar(title = { Text(stringResource(R.string.app_name)) }, actions = {
            if (model.connected) {
                TextButton(onClick = { model.selected = null; showAccess = false }, enabled = !model.streaming && !model.busy) {
                    Text(stringResource(R.string.chats))
                }
                TextButton(onClick = { showAccess = !showAccess }) { Text(stringResource(R.string.access)) }
                TextButton(onClick = model::refresh) { Text(stringResource(R.string.refresh)) }
            }
        })
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
    LazyColumn(verticalArrangement = Arrangement.spacedBy(PresentationTokens.spacePage.dp)) {
        item {
            Button(onClick = model::create, enabled = !model.busy && model.device?.permissions?.createChats == true) { Text(stringResource(R.string.new_chat)) }
        }
        items(model.chats, key = { it.id }) { chat ->
            OutlinedCard(onClick = { model.open(chat) }, modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(chat.title, modifier = Modifier.weight(1f))
                    if (chat.running) CircularProgressIndicator(Modifier.size(20.dp))
                }
            }
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
    LazyColumn(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text(chat.title, style = MaterialTheme.typography.headlineSmall) }
        items(presentMessages(chat.messages)) { message -> MessageView(message) }
        if (model.streaming || model.liveText.isNotEmpty()) item {
            MarkdownText(model.liveText.ifEmpty { stringResource(R.string.working) })
        }
    }
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(value = model.draft, onValueChange = { model.draft = it },
            label = { Text(stringResource(R.string.message)) }, modifier = Modifier.weight(1f), maxLines = 6)
        if (model.streaming || model.chats.any { it.id == chat.id && it.running }) {
            Button(onClick = model::stop, enabled = model.device?.permissions?.stop == true) { Text(stringResource(R.string.stop)) }
        } else {
            Button(onClick = model::send, enabled = !model.busy && model.draft.isNotBlank() && model.device?.permissions?.send == true) {
                Text(stringResource(R.string.send))
            }
        }
    }
}

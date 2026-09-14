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
import androidx.compose.runtime.Composable
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
    Scaffold(topBar = {
        TopAppBar(title = { Text(stringResource(R.string.app_name)) }, actions = {
            if (model.connected) {
                TextButton(onClick = { model.selected = null }, enabled = !model.streaming && !model.busy) {
                    Text(stringResource(R.string.chats))
                }
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
                !model.connected -> ConnectionForm(model)
                model.selected != null -> Conversation(model)
                else -> ChatList(model)
            }
        }
    }
}

@Composable
private fun ConnectionForm(model: MobileModel) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(stringResource(R.string.your_backend), style = MaterialTheme.typography.headlineSmall)
        OutlinedTextField(value = model.origin, onValueChange = { model.origin = it },
            label = { Text(stringResource(R.string.backend_address)) }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = model.token, onValueChange = { model.token = it },
            label = { Text(stringResource(R.string.host_token)) }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
        Text(stringResource(R.string.host_token_help), style = MaterialTheme.typography.bodySmall)
        Button(onClick = model::connect, enabled = !model.busy && model.token.isNotBlank()) {
            Text(stringResource(R.string.connect))
        }
    }
}

@Composable
private fun ChatList(model: MobileModel) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(stringResource(R.string.enable_node))
                Switch(checked = model.nodeEnabled, onCheckedChange = model::toggleNode)
            }
            Text(model.nodeStatus, style = MaterialTheme.typography.bodySmall)
            Button(onClick = model::create, enabled = !model.busy) { Text(stringResource(R.string.new_chat)) }
        }
        items(model.chats, key = { it.id }) { chat ->
            OutlinedCard(onClick = { model.open(chat) }, modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(chat.title, modifier = Modifier.weight(1f))
                    if (chat.running) CircularProgressIndicator(Modifier.size(20.dp))
                }
            }
        }
        item {
            TextButton(onClick = model::forget, enabled = !model.busy) { Text(stringResource(R.string.forget)) }
            Text(stringResource(R.string.revoke_help), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun ColumnScope.Conversation(model: MobileModel) {
    val chat = model.selected ?: return
    LazyColumn(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text(chat.title, style = MaterialTheme.typography.headlineSmall) }
        items(presentMessages(chat.messages)) { message -> MessageView(message) }
        if (model.streaming) item {
            MarkdownText(model.liveText.ifEmpty { stringResource(R.string.working) })
        }
    }
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(value = model.draft, onValueChange = { model.draft = it },
            label = { Text(stringResource(R.string.message)) }, modifier = Modifier.weight(1f), maxLines = 6)
        if (model.streaming || model.chats.any { it.id == chat.id && it.running }) {
            Button(onClick = model::stop) { Text(stringResource(R.string.stop)) }
        } else {
            Button(onClick = model::send, enabled = !model.busy && model.draft.isNotBlank()) {
                Text(stringResource(R.string.send))
            }
        }
    }
}

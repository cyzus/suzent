package com.suzent.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

@Composable
fun PairingView(model: MobileModel) {
    var scanning by remember { mutableStateOf(false) }
    val launchScanner = { scanning = true }

    if (scanning) PairingScanner(model) { scanning = false }
    var paste by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().padding(top = 16.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceLarge.dp)) {
        Column(Modifier.fillMaxWidth().background(Color(PresentationTokens.yellow))
            .border(PresentationTokens.borderWidth.dp, Color.Black).padding(PresentationTokens.spaceLarge.dp),
            verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceSmall.dp)) {
            Text(stringResource(R.string.pairing_heading), style = MaterialTheme.typography.titleLarge, color = Color.Black)
            Text(stringResource(R.string.pairing_intro), color = Color.Black)
        }
        val invitation = model.pairingInvitation
        val code = model.pairingCode
        if (code != null) {
            LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(stringResource(R.string.waiting_approval), style = MaterialTheme.typography.titleLarge)
            Text(code, style = MaterialTheme.typography.headlineLarge)
            Text(stringResource(R.string.compare_code))
            SuzentAction(stringResource(R.string.cancel_pairing), model::cancelPairing)
        } else if (invitation != null) {
            Text(stringResource(R.string.confirm_desktop), style = MaterialTheme.typography.titleLarge)
            model.pairingPreview?.let { preview ->
                Text(preview.desktopName, style = MaterialTheme.typography.titleLarge)
                val permissions = preview.permissions
                Column(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (permissions.allChats && permissions.createChats && permissions.send && permissions.stop && permissions.approveTools) {
                        Text(stringResource(R.string.full_access), style = MaterialTheme.typography.titleMedium)
                        Text(stringResource(R.string.full_access_summary))
                    } else {
                    Text(if (permissions.allChats) stringResource(R.string.all_conversations)
                        else stringResource(R.string.shared_conversations, permissions.chatIds.size))
                    listOf(R.string.create_conversations to permissions.createChats, R.string.send_messages to permissions.send,
                        R.string.stop_responses to permissions.stop, R.string.approve_tools to permissions.approveTools).forEach { (label, allowed) ->
                        Text(stringResource(label) + ": " + stringResource(if (allowed) R.string.allowed else R.string.not_allowed))
                    }
                    }
                }
            }
            Text(invitation.origin)
            Text(stringResource(if (invitation.phoneConfirmation) R.string.confirm_connection_help else R.string.confirm_desktop_help))
            if (model.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            SuzentAction(stringResource(if (invitation.phoneConfirmation) R.string.confirm_connection else R.string.request_pairing),
                model::approveDestination, prominent = true, enabled = !model.busy)
            SuzentTextButton(onClick = model::cancelPairing, enabled = !model.busy) { Text(stringResource(R.string.cancel_pairing)) }
        } else if (model.busy) {
            LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(stringResource(R.string.checking_addresses))
            SuzentAction(stringResource(R.string.cancel_pairing), model::cancelPairing)
        } else {
            Text(stringResource(R.string.pairing_steps))
            SuzentAction(stringResource(R.string.scan_desktop), {
                launchScanner()
            }, prominent = true, enabled = !model.busy)
            SuzentTextButton(onClick = { paste = !paste }) { Text(stringResource(R.string.paste_invitation)) }
            if (paste) {
                SuzentTextInput(model.invitationText, { model.invitationText = it }, stringResource(R.string.pairing_invitation), multiline = true)
                SuzentAction(stringResource(R.string.review_invitation), { model.stageInvitation(model.invitationText) },
                    enabled = !model.busy && model.invitationText.isNotBlank())
            }
            if (model.canReconnect) {
                HorizontalDivider()
                Text(model.origin, style = MaterialTheme.typography.bodySmall)
                SuzentAction(stringResource(R.string.reconnect), model::connect, enabled = !model.busy)
            }
        }
        Spacer(Modifier.height(PresentationTokens.spaceLarge.dp))
    }
}

@Composable
fun ClientPermissionsView(device: ClientDevice, origin: String) {
    Column(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline)
        .padding(PresentationTokens.spacePage.dp), verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceSmall.dp)) {
        Text(stringResource(R.string.desktop_access), style = MaterialTheme.typography.titleLarge)
        Text(device.name, style = MaterialTheme.typography.titleMedium)
        Text(origin, style = MaterialTheme.typography.bodySmall)
        Text(if (device.permissions.allChats) stringResource(R.string.all_conversations)
            else stringResource(R.string.shared_conversations, device.permissions.chatIds.size))
        listOf(R.string.create_conversations to device.permissions.createChats,
            R.string.send_messages to device.permissions.send, R.string.stop_responses to device.permissions.stop, R.string.approve_tools to device.permissions.approveTools).forEach { (label, enabled) ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(stringResource(label))
                Text(stringResource(if (enabled) R.string.allowed else R.string.not_allowed), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Text(stringResource(R.string.manage_access), style = MaterialTheme.typography.bodySmall)
        Text(stringResource(R.string.tool_approval_desktop), style = MaterialTheme.typography.bodySmall)
    }
}

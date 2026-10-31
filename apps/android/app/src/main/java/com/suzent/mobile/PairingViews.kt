package com.suzent.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

const val PRIVACY_POLICY_URL = "https://suzent.com/mobile-privacy"

@Composable
fun PairingView(model: MobileModel) {
    var scanning by remember { mutableStateOf(false) }
    if (scanning) PairingScanner(model) { scanning = false }
    if (model.pairingCode == null && model.pairingInvitation == null && !model.busy) PairingWelcome(model) { scanning = true }
    else PairingProgressView(model)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PairingWelcome(model: MobileModel, scan: () -> Unit) {
    var paste by remember { mutableStateOf(false) }
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    BoxWithConstraints(Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
        Column(Modifier.widthIn(max = 480.dp).fillMaxWidth().verticalScroll(rememberScrollState()).heightIn(min = maxHeight)
            .padding(horizontal = 8.dp).padding(bottom = PresentationTokens.spaceSmall.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.weight(1f).heightIn(min = PresentationTokens.spaceLarge.dp))
            GreetingCube(engaged = false, modifier = Modifier.size(168.dp))
            Text(stringResource(R.string.pairing_heading), Modifier.padding(top = PresentationTokens.spaceLarge.dp),
                style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
            Text(stringResource(R.string.pairing_intro), Modifier.padding(top = PresentationTokens.spaceSmall.dp),
                color = muted, textAlign = TextAlign.Center)
            Spacer(Modifier.weight(1f).heightIn(min = PresentationTokens.spaceLarge.dp))
            SuzentAction(stringResource(R.string.scan_desktop), scan, prominent = true)
            Text(stringResource(R.string.pairing_where), Modifier.padding(top = PresentationTokens.spaceMedium.dp),
                color = muted, fontSize = PresentationTokens.typeCaption.sp, textAlign = TextAlign.Center)
            Row(Modifier.padding(top = PresentationTokens.spaceSmall.dp), verticalAlignment = Alignment.CenterVertically) {
                SuzentTextButton(onClick = { paste = true }) {
                    Text(stringResource(R.string.paste_invitation), fontSize = PresentationTokens.typeCaption.sp, fontWeight = FontWeight.Medium)
                }
                Text("·", color = muted, modifier = Modifier.clearAndSetSemantics {})
                SuzentTextButton(onClick = model::startDemo) {
                    Text(stringResource(R.string.demo_enter), fontSize = PresentationTokens.typeCaption.sp, fontWeight = FontWeight.Medium)
                }
            }
            val uriHandler = LocalUriHandler.current
            SuzentTextButton(onClick = { uriHandler.openUri(PRIVACY_POLICY_URL) }) {
                Text(stringResource(R.string.privacy_policy), color = muted, fontSize = PresentationTokens.typeCaption.sp)
            }
        }
    }
    if (paste) ModalBottomSheet(onDismissRequest = { paste = false }, shape = RectangleShape,
        containerColor = MaterialTheme.colorScheme.surface) {
        Column(Modifier.fillMaxWidth().padding(horizontal = PresentationTokens.spacePage.dp).padding(bottom = PresentationTokens.spaceLarge.dp),
            verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceMedium.dp)) {
            Text(stringResource(R.string.pairing_invitation), fontSize = PresentationTokens.typeSection.sp, fontWeight = FontWeight.Bold)
            SuzentTextInput(model.invitationText, { model.invitationText = it }, stringResource(R.string.pairing_invitation), multiline = true)
            SuzentAction(stringResource(R.string.review_invitation), { paste = false; model.stageInvitation(model.invitationText) },
                prominent = true, enabled = model.invitationText.isNotBlank())
        }
    }
}

@Composable
private fun PairingProgressView(model: MobileModel) {
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
            PairingProgress(stringResource(R.string.waiting_approval))
            PairingCode(code)
            Text(stringResource(R.string.compare_code))
            SuzentAction(stringResource(R.string.cancel_pairing), model::cancelPairing)
        } else if (invitation != null) {
            Text(stringResource(R.string.confirm_desktop), style = MaterialTheme.typography.titleLarge)
            model.pairingPreview?.let { preview ->
                Text(preview.desktopName, style = MaterialTheme.typography.titleLarge)
                val permissions = preview.permissions
                Column(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.manage_conversations) + ": " + stringResource(if (permissions.manageChats) R.string.allowed else R.string.not_allowed))
                    if (permissions.allChats && permissions.createChats && permissions.manageChats && permissions.send && permissions.stop && permissions.approveTools) {
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
                    if (permissions.allChats) Text(stringResource(R.string.regent_permission), style = MaterialTheme.typography.bodySmall)
                }
            }
            Text(invitation.origin)
            Text(stringResource(if (invitation.phoneConfirmation) R.string.confirm_connection_help else R.string.confirm_desktop_help))
            if (model.busy) PairingProgress(model.pairingStatus ?: stringResource(R.string.pairing_finishing))
            SuzentAction(stringResource(if (invitation.phoneConfirmation) R.string.confirm_connection else R.string.request_pairing),
                model::approveDestination, prominent = true, enabled = !model.busy)
            SuzentTextButton(onClick = model::cancelPairing, enabled = !model.busy) { Text(stringResource(R.string.cancel_pairing)) }
        } else if (model.busy) {
            PairingProgress(model.pairingStatus ?: stringResource(R.string.checking_addresses))
            SuzentAction(stringResource(R.string.cancel_pairing), model::cancelPairing)
        }
        Spacer(Modifier.height(PresentationTokens.spaceLarge.dp))
    }
}

@Composable
fun PairingProgress(status: String, color: Color = MaterialTheme.colorScheme.onSurface) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(PresentationTokens.spaceMedium.dp),
        modifier = Modifier.semantics(mergeDescendants = true) {}) {
        CircularProgressIndicator(Modifier.size(20.dp), color = color, strokeWidth = 2.dp)
        Text(status, color = color)
    }
}

@Composable
fun PairingCode(code: String) {
    Text(code, style = MaterialTheme.typography.headlineLarge, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold,
        letterSpacing = 4.sp)
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
        if (device.permissions.allChats) Text(stringResource(R.string.regent_permission), style = MaterialTheme.typography.bodySmall)
        listOf(R.string.manage_conversations to device.permissions.manageChats, R.string.create_conversations to device.permissions.createChats,
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

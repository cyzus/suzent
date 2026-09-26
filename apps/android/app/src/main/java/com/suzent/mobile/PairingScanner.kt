package com.suzent.mobile

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import android.Manifest
import android.content.pm.PackageManager
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.Image
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.zxing.BarcodeFormat
import com.journeyapps.barcodescanner.BarcodeCallback
import com.journeyapps.barcodescanner.BarcodeResult
import com.journeyapps.barcodescanner.BarcodeView
import com.journeyapps.barcodescanner.DefaultDecoderFactory
import kotlin.math.sin

@Composable
fun PairingScanner(model: MobileModel, close: () -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var paste by remember { mutableStateOf(false) }
    var torch by remember { mutableStateOf(false) }
    var cameraFailed by remember { mutableStateOf(false) }
    var foreground by remember { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) }
    val camera = remember { BarcodeView(context).apply {
        decoderFactory = DefaultDecoderFactory(listOf(BarcodeFormat.QR_CODE))
    } }
    var allowed by remember { mutableStateOf(context.checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed = it }
    LaunchedEffect(Unit) { if (!allowed) permission.launch(Manifest.permission.CAMERA) }
    val found = model.pairingInvitation != null || model.pairingCode != null
    val active = !found && !model.busy && model.error == null && !paste && foreground
    val latestActive by rememberUpdatedState(active)
    val reset = { model.cancelPairing(); model.error = null }
    DisposableEffect(camera, lifecycle, allowed) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                foreground = true
                if (allowed) try { camera.resume() } catch (_: Exception) { cameraFailed = true }
            }
            if (event == Lifecycle.Event.ON_PAUSE) { foreground = false; torch = false; camera.pause() }
        }
        camera.addStateListener(object : com.journeyapps.barcodescanner.CameraPreview.StateListener {
            override fun previewSized() {}
            override fun previewStarted() {}
            override fun previewStopped() {}
            override fun cameraClosed() {}
            override fun cameraError(error: Exception) { cameraFailed = true }
        })
        lifecycle.addObserver(observer)
        if (allowed && foreground) try { camera.resume() } catch (_: Exception) { cameraFailed = true }
        onDispose { lifecycle.removeObserver(observer); camera.setTorch(false); camera.pause() }
    }
    LaunchedEffect(active) {
        if (active) camera.decodeSingle(object : BarcodeCallback {
            override fun barcodeResult(result: BarcodeResult) {
                if (latestActive) result.text?.let(model::stageInvitation)
            }
        }) else camera.stopDecoding()
    }
    LaunchedEffect(torch) { camera.setTorch(torch) }
    val initialPairingVersion = remember { model.pairingVersion }
    LaunchedEffect(model.pairingVersion) { if (model.pairingVersion != initialPairingVersion) close() }
    Dialog(onDismissRequest = { reset(); close() }, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        BoxWithConstraints(Modifier.fillMaxSize().background(Color.Black)) {
            val frameSize = minOf(maxWidth * 0.76f, maxHeight * 0.38f)
            if (allowed && !cameraFailed) AndroidView(factory = { camera }, modifier = Modifier.fillMaxSize())
            Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Black.copy(alpha = .75f), Color.Transparent, Color.Black.copy(alpha = .85f)))))
            Column(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 24.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("▪ SUZENT ▪", fontSize = 21.sp, fontWeight = FontWeight.Black, modifier = Modifier.weight(1f))
                    val cancelLabel = stringResource(R.string.cancel_pairing)
                    SuzentTextButton(onClick = { reset(); close() }, modifier = Modifier.semantics { contentDescription = cancelLabel }) { Text("×", color = Color.White, fontSize = 28.sp) }
                }
                Text(stringResource(R.string.scan_heading), color = Color.White, style = MaterialTheme.typography.titleLarge, modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 24.dp))
                Text(stringResource(R.string.scan_hint), color = Color.White, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 8.dp))
            }
            val offset by animateDpAsState(if (found) (-65).dp else (-20).dp, spring(dampingRatio = .9f), label = "scan frame")
            if (allowed && !cameraFailed) ScanFrame(active, found, Modifier.align(Alignment.Center).offset(y = offset).size(frameSize))
            else Text(stringResource(R.string.camera_unavailable), color = Color.White, modifier = Modifier.align(Alignment.Center).padding(32.dp))
            Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().navigationBarsPadding()) {
                AnimatedVisibility(visible = !found, modifier = Modifier.align(Alignment.BottomCenter), exit = fadeOut(tween(120))) {
                    Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                        AnimatedVisibility(model.error != null, enter = fadeIn() + slideInVertically { it / 4 }) {
                            Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text(model.error.orEmpty(), Modifier.weight(1f), color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.bodySmall)
                                SuzentTextButton(onClick = reset) { Text(stringResource(R.string.scan_again)) }
                            }
                        }
                        if (model.busy) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text(stringResource(R.string.checking_addresses), color = Color.White) }
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            SuzentTextButton(onClick = { torch = !torch }, enabled = allowed && !cameraFailed,
                                modifier = Modifier.border(1.dp, Color.White).background(if (torch) Color(PresentationTokens.yellow) else Color.Black)) {
                                Text(stringResource(R.string.flashlight), color = if (torch) Color.Black else Color.White)
                            }
                            Box(Modifier.weight(1f)) { SuzentAction(stringResource(R.string.paste_invitation), { paste = true }, compact = true) }
                        }
                        Text(stringResource(R.string.pairing_steps), color = Color.White.copy(alpha = .8f), style = MaterialTheme.typography.bodySmall)
                    }
                }
                AnimatedVisibility(found, modifier = Modifier.align(Alignment.BottomCenter), enter = slideInVertically(spring(dampingRatio = .9f)) { it } + fadeIn(), exit = slideOutVertically { it } + fadeOut()) {
                    Column(Modifier.fillMaxWidth().heightIn(max = 360.dp).background(MaterialTheme.colorScheme.surface)
                        .verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(stringResource(R.string.desktop_recognized), Modifier.weight(1f), fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.labelMedium)
                            SuzentTextButton(onClick = reset) { Text(stringResource(R.string.scan_again)) }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Image(painterResource(R.drawable.suzent_logo), contentDescription = null, modifier = Modifier.size(42.dp))
                            Text(model.pairingPreview?.desktopName ?: stringResource(R.string.confirm_desktop), style = MaterialTheme.typography.titleLarge)
                        }
                        Text(model.pairingInvitation?.origin.orEmpty(), style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
                        if (model.pairingCode != null) {
                            Text(stringResource(R.string.waiting_approval)); Text(model.pairingCode.orEmpty(), style = MaterialTheme.typography.headlineLarge)
                        } else model.pairingInvitation?.let { invitation ->
                            var details by remember { mutableStateOf(false) }
                            model.pairingPreview?.let { preview ->
                                SuzentTextButton(onClick = { details = !details }) { Text(stringResource(R.string.desktop_access) + if (details) " −" else " +") }
                                if (details) {
                                    val p = preview.permissions
                                    Text(if (p.allChats) stringResource(R.string.all_conversations) else stringResource(R.string.shared_conversations, p.chatIds.size))
                                    listOf(R.string.create_conversations to p.createChats, R.string.send_messages to p.send,
                                        R.string.stop_responses to p.stop, R.string.approve_tools to p.approveTools).forEach { (label, enabled) ->
                                        Text(stringResource(label) + ": " + stringResource(if (enabled) R.string.allowed else R.string.not_allowed), style = MaterialTheme.typography.bodySmall)
                                    }
                                }
                            }
                            Text(stringResource(if (invitation.phoneConfirmation) R.string.confirm_connection_help else R.string.confirm_desktop_help), style = MaterialTheme.typography.bodySmall)
                            model.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                            if (model.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                            SuzentAction(stringResource(if (invitation.phoneConfirmation) R.string.confirm_connection else R.string.request_pairing), model::approveDestination, prominent = true, enabled = !model.busy)
                        }
                    }
                }
            }
        }
        if (paste) AlertDialog(onDismissRequest = { paste = false }, title = { Text(stringResource(R.string.paste_invitation)) }, text = {
            OutlinedTextField(model.invitationText, { model.invitationText = it }, minLines = 3, label = { Text(stringResource(R.string.pairing_invitation)) })
        }, confirmButton = { SuzentTextButton(onClick = { paste = false; model.stageInvitation(model.invitationText) }, enabled = !model.busy && model.invitationText.isNotBlank()) { Text(stringResource(R.string.review_invitation)) } })
    }
}

@Composable
private fun ScanFrame(active: Boolean, found: Boolean, modifier: Modifier) {
    val motion = android.animation.ValueAnimator.areAnimatorsEnabled()
    val phase = if (active && motion) {
        val transition = rememberInfiniteTransition(label = "scanner")
        val value by transition.animateFloat(0f, (Math.PI * 2).toFloat(), infiniteRepeatable(tween(3900, easing = LinearEasing)), label = "scan line")
        value
    } else 0f
    val color by animateColorAsState(if (found) Color(0xFFB5E4C3) else Color.White, label = "scan corners")
    Canvas(modifier) {
        val length = (if (found) 34 else 26).dp.toPx()
        listOf(Triple(Offset.Zero, 1f, 1f), Triple(Offset(size.width, 0f), -1f, 1f), Triple(Offset(0f, size.height), 1f, -1f), Triple(Offset(size.width, size.height), -1f, -1f)).forEach { (origin, dx, dy) ->
            drawLine(color, origin, origin + Offset(dx * length, 0f), 3.dp.toPx())
            drawLine(color, origin, origin + Offset(0f, dy * length), 3.dp.toPx())
        }
        if (active) {
            val y = 20.dp.toPx() + (sin(phase) + 1f) / 2f * (size.height - 40.dp.toPx()).coerceAtLeast(0f)
            drawLine(Color(PresentationTokens.blue), Offset(12.dp.toPx(), y), Offset(size.width - 12.dp.toPx(), y), 1.dp.toPx())
        }
    }
}

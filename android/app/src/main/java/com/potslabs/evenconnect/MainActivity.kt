package com.potslabs.evenconnect

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val vm: MainViewModel by viewModels()

    private val permLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results -> if (results.values.all { it }) vm.scan() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { EvenConnectApp(vm) { requestPermsAndScan() } }
    }

    private fun requestPermsAndScan() {
        val perms = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        else arrayOf(Manifest.permission.BLUETOOTH, Manifest.permission.BLUETOOTH_ADMIN,
            Manifest.permission.ACCESS_FINE_LOCATION)
        val missing = perms.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) vm.scan() else permLauncher.launch(missing.toTypedArray())
    }
}

// ── Theme ─────────────────────────────────────────────────────────────────────
private val BgDark    = Color(0xFF0D0D0D)
private val Surface   = Color(0xFF1A1A1A)
private val CardBg    = Color(0xFF242424)
private val Accent    = Color(0xFF39FF14)
private val TextMain  = Color(0xFFE8E8E8)
private val TextMuted = Color(0xFF777777)
private val Red       = Color(0xFFFF4444)
private val Border    = Color(0xFF333333)

private val Palette = darkColorScheme(
    background = BgDark, surface = Surface, primary = Accent, onPrimary = Color.Black,
    onBackground = TextMain, onSurface = TextMain, surfaceVariant = CardBg,
    onSurfaceVariant = TextMuted, outline = Border,
)

// ── App ───────────────────────────────────────────────────────────────────────
@Composable
fun EvenConnectApp(vm: MainViewModel, onScan: () -> Unit) {
    MaterialTheme(colorScheme = Palette) {
        val nav   = rememberNavController()
        val entry by nav.currentBackStackEntryAsState()
        val cur   = entry?.destination?.route ?: "home"

        Scaffold(
            bottomBar = {
                NavigationBar(containerColor = Surface, tonalElevation = 0.dp) {
                    data class NavItem(val route: String, val label: String)
                    listOf(
                        NavItem("home",    "Home"),
                        NavItem("send",    "Text"),
                        NavItem("image",   "Image"),
                        NavItem("compose", "Compose"),
                        NavItem("log",     "Log"),
                    ).forEach { item ->
                        NavigationBarItem(
                            selected = cur == item.route,
                            onClick  = { nav.navigate(item.route) { launchSingleTop = true; restoreState = true } },
                            icon     = {
                                when (item.route) {
                                    "home"    -> Icon(Icons.Default.Home, null)
                                    "send"    -> Icon(Icons.AutoMirrored.Filled.Send, null)
                                    "image"   -> Icon(Icons.Default.Image, null)
                                    "compose" -> Icon(Icons.Default.Layers, null)
                                    else      -> Icon(Icons.AutoMirrored.Filled.List, null)
                                }
                            },
                            label = { Text(item.label, fontSize = 11.sp) },
                        )
                    }
                }
            }
        ) { pad ->
            NavHost(nav, "home", Modifier.padding(pad)) {
                composable("home")    { HomeScreen(vm, onScan) }
                composable("send")    { TextScreen(vm) }
                composable("image")   { ImageScreen(vm) }
                composable("compose") { ComposeScreen(vm) }
                composable("log")     { LogScreen(vm) }
            }
        }
    }
}

// ── Home ──────────────────────────────────────────────────────────────────────
@Composable
fun HomeScreen(vm: MainViewModel, onScan: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()

    Column(
        modifier = Modifier.fillMaxSize().background(BgDark).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(20.dp, Alignment.CenterVertically),
    ) {
        Text("EvenConnect", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Accent)
        Text("G1 Glasses Controller", fontSize = 14.sp, color = TextMuted)
        Spacer(Modifier.height(4.dp))

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = CardBg),
            shape = RoundedCornerShape(16.dp),
        ) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    val dotColor = when (state) {
                        G1BleManager.State.CONNECTED  -> Accent
                        G1BleManager.State.SCANNING,
                        G1BleManager.State.CONNECTING -> Color(0xFFFFAA00)
                        else -> Color(0xFF444444)
                    }
                    Box(Modifier.size(10.dp).clip(CircleShape).background(dotColor))
                    Text(
                        when (state) {
                            G1BleManager.State.CONNECTED  -> "Connected"
                            G1BleManager.State.SCANNING   -> "Scanning…"
                            G1BleManager.State.CONNECTING -> "Connecting…"
                            else -> "Disconnected"
                        },
                        fontWeight = FontWeight.SemiBold, color = TextMain,
                    )
                }
                Text("Right tap → next page  ·  Left tap → previous page", fontSize = 12.sp, color = TextMuted)
                Text("Text: display-only mode (no AI activation)", fontSize = 11.sp, color = TextMuted)
            }
        }

        // Action button — explicit if/else avoids Compose when-trailing-lambda ambiguity
        if (state == G1BleManager.State.DISCONNECTED) {
            Button(
                onClick = onScan,
                modifier = Modifier.fillMaxWidth().height(52.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Accent, contentColor = Color.Black),
                shape = RoundedCornerShape(12.dp),
            ) {
                Icon(Icons.Default.Bluetooth, null, Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text("Scan & Connect", fontWeight = FontWeight.Bold, fontSize = 16.sp)
            }
        } else if (state == G1BleManager.State.CONNECTED) {
            OutlinedButton(
                onClick = { vm.disconnect() },
                modifier = Modifier.fillMaxWidth().height(52.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Red),
                shape = RoundedCornerShape(12.dp),
            ) {
                Icon(Icons.Default.BluetoothDisabled, null, Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text("Disconnect", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            }
        } else {
            OutlinedButton(
                onClick = {},
                enabled = false,
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = RoundedCornerShape(12.dp),
            ) {
                CircularProgressIndicator(Modifier.size(20.dp), color = Accent, strokeWidth = 2.dp)
                Spacer(Modifier.width(8.dp))
                Text("Working…")
            }
        }
    }
}

// ── Text ──────────────────────────────────────────────────────────────────────
@Composable
fun TextScreen(vm: MainViewModel) {
    val state by vm.state.collectAsStateWithLifecycle()
    var text    by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    val scope   = rememberCoroutineScope()
    val connected = state == G1BleManager.State.CONNECTED

    Column(
        modifier = Modifier.fillMaxSize().background(BgDark).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Send Text", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Accent,
            modifier = Modifier.padding(top = 8.dp))

        OutlinedTextField(
            value = text, onValueChange = { text = it },
            modifier = Modifier.fillMaxWidth().weight(1f),
            placeholder = { Text("Type or paste text…", color = TextMuted) },
            colors = fieldColors(), shape = RoundedCornerShape(12.dp),
        )

        Text("${text.lines().size} lines · ${text.length} chars", fontSize = 11.sp, color = TextMuted)

        OutlinedButton(
            onClick = {
                text = "Morning Brief\n---------------------\nGood morning. Tap right\nto continue.\n\nTasks -- Today\n---------------------\n[ ] Review open PRs\n[ ] Team standup 10am\n[ ] Ship BLE fix\n\nQuick Note\n---------------------\nKiroshiOS manual\npagination via tap\nis now working!"
            },
            colors = ButtonDefaults.outlinedButtonColors(contentColor = TextMuted),
            shape = RoundedCornerShape(8.dp),
        ) { Text("Load sample (3 pages)", fontSize = 13.sp) }

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(
                onClick = { text = "" },
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = TextMuted),
                shape = RoundedCornerShape(12.dp),
            ) { Text("Clear") }

            Button(
                onClick = {
                    sending = true
                    vm.sendText(text.trim())
                    scope.launch { delay(600L); sending = false }
                },
                enabled = connected && text.isNotBlank() && !sending,
                modifier = Modifier.weight(2f).height(52.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Accent, contentColor = Color.Black,
                    disabledContainerColor = Color(0xFF2A2A2A), disabledContentColor = TextMuted,
                ),
                shape = RoundedCornerShape(12.dp),
            ) {
                if (sending) {
                    CircularProgressIndicator(Modifier.size(18.dp), color = Color.Black, strokeWidth = 2.dp)
                } else {
                    Icon(Icons.AutoMirrored.Filled.Send, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Send to Glasses", fontWeight = FontWeight.Bold)
                }
            }
        }

        if (!connected) Text("Connect to glasses on the Home tab first.", fontSize = 12.sp, color = TextMuted)
    }
}

// ── Image ─────────────────────────────────────────────────────────────────────
@Composable
fun ImageScreen(vm: MainViewModel) {
    val state   by vm.state.collectAsStateWithLifecycle()
    val preview by vm.imagePreview.collectAsStateWithLifecycle()
    val bmp     by vm.imageBmp.collectAsStateWithLifecycle()
    val status  by vm.imageStatus.collectAsStateWithLifecycle()
    val connected = state == G1BleManager.State.CONNECTED

    val picker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia()
    ) { uri -> uri?.let { vm.loadImage(it) } }

    Column(
        modifier = Modifier.fillMaxSize().background(BgDark).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Image", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Accent,
            modifier = Modifier.padding(top = 8.dp))

        Box(
            modifier = Modifier.fillMaxWidth().height(100.dp)
                .background(CardBg, RoundedCornerShape(12.dp))
                .border(1.dp, Border, RoundedCornerShape(12.dp)),
            contentAlignment = Alignment.Center,
        ) {
            if (preview != null) {
                Image(
                    bitmap = preview!!.asImageBitmap(), contentDescription = null,
                    modifier = Modifier.fillMaxSize().clip(RoundedCornerShape(12.dp)),
                    contentScale = ContentScale.Fit,
                )
                Text("576×136 glasses view", fontSize = 10.sp, color = TextMuted,
                    modifier = Modifier.align(Alignment.BottomEnd).padding(4.dp))
            } else {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.Image, null, tint = TextMuted, modifier = Modifier.size(32.dp))
                    Spacer(Modifier.height(4.dp))
                    Text("No image loaded", fontSize = 13.sp, color = TextMuted)
                }
            }
        }

        if (status.isNotBlank()) {
            Text(status, fontSize = 12.sp, color = if ("Error" in status) Red else Accent)
        }

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(
                onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = TextMain),
                shape = RoundedCornerShape(12.dp),
            ) {
                Icon(Icons.Default.FolderOpen, null, Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Pick Image")
            }
            if (bmp != null) {
                OutlinedButton(
                    onClick = { vm.clearImage() },
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = TextMuted),
                    shape = RoundedCornerShape(12.dp),
                ) { Text("Clear") }
            }
        }

        Button(
            onClick = { vm.sendImage() },
            enabled = connected && bmp != null,
            modifier = Modifier.fillMaxWidth().height(52.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Accent, contentColor = Color.Black,
                disabledContainerColor = Color(0xFF2A2A2A), disabledContentColor = TextMuted,
            ),
            shape = RoundedCornerShape(12.dp),
        ) {
            Icon(Icons.Default.Send, null, Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Text("Send to Glasses", fontWeight = FontWeight.Bold, fontSize = 16.sp)
        }

        if (!connected) Text("Connect to glasses on the Home tab first.", fontSize = 12.sp, color = TextMuted)

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = CardBg),
            shape = RoundedCornerShape(12.dp),
        ) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("About image mode", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = TextMuted)
                Text("Scaled to 576×136 · 1-bit monochrome · dark pixels = ON", fontSize = 11.sp, color = TextMuted, lineHeight = 16.sp)
                Text("Sent via BMP frame protocol (0x15 frames + CRC)", fontSize = 11.sp, color = TextMuted, lineHeight = 16.sp)
            }
        }
    }
}

// ── Compose ───────────────────────────────────────────────────────────────────
@Composable
fun ComposeScreen(vm: MainViewModel) {
    val state   by vm.state.collectAsStateWithLifecycle()
    val bg      by vm.composeBg.collectAsStateWithLifecycle()
    val layers  by vm.composeLayers.collectAsStateWithLifecycle()
    val preview by vm.composePreview.collectAsStateWithLifecycle()
    val connected = state == G1BleManager.State.CONNECTED

    val bgPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia()
    ) { uri -> uri?.let { vm.loadComposeBg(it) } }

    Column(
        modifier = Modifier.fillMaxSize().background(BgDark)
            .verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Compose", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Accent,
            modifier = Modifier.padding(top = 8.dp))

        // Live preview
        Box(
            modifier = Modifier.fillMaxWidth().height(100.dp)
                .background(CardBg, RoundedCornerShape(12.dp))
                .border(1.dp, Border, RoundedCornerShape(12.dp)),
            contentAlignment = Alignment.Center,
        ) {
            if (preview != null) {
                Image(
                    bitmap = preview!!.asImageBitmap(), contentDescription = null,
                    modifier = Modifier.fillMaxSize().clip(RoundedCornerShape(12.dp)),
                    contentScale = ContentScale.Fit,
                )
            } else {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.Layers, null, tint = TextMuted, modifier = Modifier.size(28.dp))
                    Text("Preview updates as you type", fontSize = 12.sp, color = TextMuted)
                }
            }
        }

        // Background card
        SectionCard("Background") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = { bgPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = TextMain),
                    shape = RoundedCornerShape(10.dp),
                ) { Text(if (bg != null) "Change BG" else "Add Background", fontSize = 13.sp) }
                if (bg != null) {
                    OutlinedButton(
                        onClick = { vm.clearComposeBg() },
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = TextMuted),
                        shape = RoundedCornerShape(10.dp),
                    ) { Text("Clear", fontSize = 13.sp) }
                }
            }
        }

        // Text layers
        SectionCard("Text Layers") {
            layers.forEachIndexed { i, layer ->
                ComposeLayerCard(i, layer,
                    onUpdate   = { vm.updateComposeLayer(i, it) },
                    onRemove   = { vm.removeComposeLayer(i) },
                    showRemove = layers.size > 1,
                )
                if (i < layers.size - 1) HorizontalDivider(color = Border, modifier = Modifier.padding(vertical = 6.dp))
            }
            Spacer(Modifier.height(4.dp))
            OutlinedButton(
                onClick = { vm.addComposeLayer() },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Accent),
                shape = RoundedCornerShape(10.dp),
            ) {
                Icon(Icons.Default.Add, null, Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Add Layer")
            }
        }

        Button(
            onClick = { vm.sendCompose() },
            enabled = connected,
            modifier = Modifier.fillMaxWidth().height(52.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Accent, contentColor = Color.Black,
                disabledContainerColor = Color(0xFF2A2A2A), disabledContentColor = TextMuted,
            ),
            shape = RoundedCornerShape(12.dp),
        ) {
            Icon(Icons.Default.Send, null, Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Text("Send to Glasses", fontWeight = FontWeight.Bold, fontSize = 16.sp)
        }

        if (!connected) Text("Connect to glasses on the Home tab first.", fontSize = 12.sp, color = TextMuted)
    }
}

@Composable
fun ComposeLayerCard(
    index: Int, layer: TextLayer,
    onUpdate: (TextLayer) -> Unit, onRemove: () -> Unit, showRemove: Boolean,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Layer ${index + 1}", fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                color = TextMuted, modifier = Modifier.weight(1f))
            if (showRemove) {
                IconButton(onClick = onRemove, modifier = Modifier.size(28.dp)) {
                    Icon(Icons.Default.Close, null, tint = TextMuted, modifier = Modifier.size(16.dp))
                }
            }
        }

        OutlinedTextField(
            value = layer.text, onValueChange = { onUpdate(layer.copy(text = it)) },
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("Enter text…", color = TextMuted) },
            colors = fieldColors(), shape = RoundedCornerShape(8.dp), maxLines = 3,
        )

        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf(HAlign.LEFT to "Left", HAlign.CENTER to "Center", HAlign.RIGHT to "Right")
                .forEach { (a, lbl) ->
                    FilterChip(
                        selected = a == layer.hAlign,
                        onClick  = { onUpdate(layer.copy(hAlign = a)) },
                        label    = { Text(lbl, fontSize = 11.sp) },
                        colors   = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = Accent, selectedLabelColor = Color.Black),
                    )
                }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf(VAlign.TOP to "Top", VAlign.MIDDLE to "Middle", VAlign.BOTTOM to "Bottom")
                .forEach { (a, lbl) ->
                    FilterChip(
                        selected = a == layer.vAlign,
                        onClick  = { onUpdate(layer.copy(vAlign = a)) },
                        label    = { Text(lbl, fontSize = 11.sp) },
                        colors   = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = Accent, selectedLabelColor = Color.Black),
                    )
                }
        }

        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Size:", fontSize = 12.sp, color = TextMuted)
            Slider(
                value = layer.sizeSp,
                onValueChange = { onUpdate(layer.copy(sizeSp = it)) },
                valueRange = 12f..36f,
                modifier = Modifier.weight(1f),
                colors = SliderDefaults.colors(thumbColor = Accent, activeTrackColor = Accent),
            )
            Text("${layer.sizeSp.toInt()}sp", fontSize = 11.sp, color = TextMuted,
                modifier = Modifier.width(30.dp))
            FilterChip(
                selected = layer.light,
                onClick  = { onUpdate(layer.copy(light = !layer.light)) },
                label    = { Text(if (layer.light) "Light" else "Dark", fontSize = 11.sp) },
                colors   = FilterChipDefaults.filterChipColors(
                    selectedContainerColor = Accent, selectedLabelColor = Color.Black),
            )
        }
    }
}

// ── Log ───────────────────────────────────────────────────────────────────────
@Composable
fun LogScreen(vm: MainViewModel) {
    val lines     by vm.logLines.collectAsStateWithLifecycle()
    val listState = rememberLazyListState()

    LaunchedEffect(lines.size) {
        if (lines.isNotEmpty()) listState.animateScrollToItem(lines.size - 1)
    }

    Column(Modifier.fillMaxSize().background(BgDark).padding(16.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Activity Log", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Accent)
            Text("${lines.size}", fontSize = 12.sp, color = TextMuted)
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            state = listState,
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            items(lines) { line ->
                Text(
                    text = line,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    lineHeight = 15.sp,
                    color = when {
                        "Error" in line || "failed" in line.lowercase() -> Red
                        "Single Tap" in line || "Change Page" in line   -> Accent
                        else -> TextMuted
                    },
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 1.dp),
                )
            }
        }
    }
}

// ── Shared helpers ────────────────────────────────────────────────────────────
@Composable
fun SectionCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = CardBg),
        shape = RoundedCornerShape(12.dp),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = TextMuted)
            content()
        }
    }
}

@Composable
fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor   = Accent,  unfocusedBorderColor = Border,
    focusedTextColor     = TextMain, unfocusedTextColor   = TextMain,
    cursorColor          = Accent,
    focusedContainerColor   = CardBg, unfocusedContainerColor = CardBg,
)

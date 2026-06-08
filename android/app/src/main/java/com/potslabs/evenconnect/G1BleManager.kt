package com.potslabs.evenconnect

import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.util.UUID

@SuppressLint("MissingPermission")
class G1BleManager(private val context: Context) {

    enum class State { DISCONNECTED, SCANNING, CONNECTING, CONNECTED }

    private val btManager  = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val adapter    get() = btManager.adapter
    private val leScanner  get() = adapter.bluetoothLeScanner

    private var leftGatt:  BluetoothGatt? = null
    private var rightGatt: BluetoothGatt? = null
    private var leftTx:    BluetoothGattCharacteristic? = null
    private var rightTx:   BluetoothGattCharacteristic? = null
    private var leftReady  = false
    private var rightReady = false

    private val _state  = MutableStateFlow(State.DISCONNECTED)
    private val _log    = MutableSharedFlow<String>(extraBufferCapacity = 256)

    val state:       StateFlow<State>   = _state.asStateFlow()
    val log:         SharedFlow<String> = _log.asSharedFlow()
    val isConnected  get() = _state.value == State.CONNECTED

    private val scope    = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val handler  = Handler(Looper.getMainLooper())
    private var scanCb:  ScanCallback? = null
    private var hbJob:   Job? = null

    // Text pagination state
    private var pages       = emptyList<String>()
    private var currentPage = 0
    private var lastAdvance = 0L

    // ── Scan ─────────────────────────────────────────────────────────────────

    fun scan() {
        if (_state.value != State.DISCONNECTED) return
        leftReady = false; rightReady = false
        _state.value = State.SCANNING
        log("Scanning for G1 glasses…")

        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()

        scanCb = object : ScanCallback() {
            override fun onScanResult(ct: Int, result: ScanResult) {
                val name = result.device.name ?: return
                when {
                    "_L_" in name && leftGatt  == null -> connectGlass(result.device, "left")
                    "_R_" in name && rightGatt == null -> connectGlass(result.device, "right")
                }
            }
            override fun onScanFailed(err: Int) { log("Scan failed: $err") }
        }
        leScanner.startScan(null, settings, scanCb!!)
        handler.postDelayed({
            stopScan()
            if (!leftReady && !rightReady) { _state.value = State.DISCONNECTED; log("No glasses found — tap Scan to retry") }
        }, 15_000)
    }

    private fun stopScan() { scanCb?.let { runCatching { leScanner.stopScan(it) } }; scanCb = null }

    // ── GATT connect ─────────────────────────────────────────────────────────

    private fun connectGlass(device: BluetoothDevice, side: String) {
        if (_state.value == State.SCANNING) _state.value = State.CONNECTING
        log("Connecting $side (${device.name})…")

        device.connectGatt(context, false, object : BluetoothGattCallback() {

            override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    log("$side link up")
                    gatt.discoverServices()
                } else {
                    log("$side disconnected")
                    if (side == "left")  { leftGatt  = null; leftTx  = null; leftReady  = false }
                    else                 { rightGatt = null; rightTx = null; rightReady = false }
                    gatt.close(); recalcState()
                }
            }

            override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
                val svc = gatt.getService(UUID.fromString(G1Protocol.UART_SERVICE)) ?: return
                val tx  = svc.getCharacteristic(UUID.fromString(G1Protocol.UART_TX))  ?: return
                val rx  = svc.getCharacteristic(UUID.fromString(G1Protocol.UART_RX))  ?: return

                if (side == "left") { leftGatt  = gatt; leftTx  = tx }
                else                { rightGatt = gatt; rightTx = tx }

                gatt.setCharacteristicNotification(rx, true)
                rx.getDescriptor(UUID.fromString(G1Protocol.CCCD_UUID))?.let { desc ->
                    writeDescriptor(gatt, desc, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                }

                handler.postDelayed({
                    writeChar(gatt, tx, byteArrayOf(0x4D, 0x01))
                    handler.postDelayed({ writeChar(gatt, tx, G1Protocol.timeSync()) }, 250)
                    if (side == "left") leftReady = true else rightReady = true
                    recalcState()
                }, 400)
            }

            // API 33+
            override fun onCharacteristicChanged(gatt: BluetoothGatt, ch: BluetoothGattCharacteristic, value: ByteArray) =
                onNotification(side, value)

            // API < 33
            @Suppress("DEPRECATION")
            override fun onCharacteristicChanged(gatt: BluetoothGatt, ch: BluetoothGattCharacteristic) {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU)
                    onNotification(side, ch.value ?: return)
            }

        }, BluetoothDevice.TRANSPORT_LE)
    }

    // ── BLE write helpers ─────────────────────────────────────────────────────

    private fun writeChar(gatt: BluetoothGatt, ch: BluetoothGattCharacteristic, data: ByteArray) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            gatt.writeCharacteristic(ch, data, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT)
        else {
            @Suppress("DEPRECATION") ch.value = data
            @Suppress("DEPRECATION") gatt.writeCharacteristic(ch)
        }
    }

    private fun writeCharNoResp(gatt: BluetoothGatt, ch: BluetoothGattCharacteristic, data: ByteArray) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            gatt.writeCharacteristic(ch, data, BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE)
        else {
            @Suppress("DEPRECATION") ch.value = data
            @Suppress("DEPRECATION") ch.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
            @Suppress("DEPRECATION") gatt.writeCharacteristic(ch)
        }
    }

    private fun writeDescriptor(gatt: BluetoothGatt, desc: BluetoothGattDescriptor, value: ByteArray) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            gatt.writeDescriptor(desc, value)
        else {
            @Suppress("DEPRECATION") desc.value = value
            @Suppress("DEPRECATION") gatt.writeDescriptor(desc)
        }
    }

    private fun sendBoth(data: ByteArray) {
        leftGatt?.let  { g -> leftTx?.let  { tx -> writeChar(g, tx, data) } }
        rightGatt?.let { g -> rightTx?.let { tx -> writeChar(g, tx, data) } }
    }

    private fun sendBothNoResp(data: ByteArray) {
        leftGatt?.let  { g -> leftTx?.let  { tx -> writeCharNoResp(g, tx, data) } }
        rightGatt?.let { g -> rightTx?.let { tx -> writeCharNoResp(g, tx, data) } }
    }

    // ── Text ─────────────────────────────────────────────────────────────────

    fun sendText(text: String) {
        pages = G1Protocol.buildPages(text)
        currentPage = 0
        scope.launch { pushPage(0) }
    }

    private suspend fun pushPage(idx: Int) {
        if (idx >= pages.size) return
        sendBoth(G1Protocol.textDisplayPacket(pages[idx]))
        log("text page ${idx + 1}/${pages.size}")
    }

    private fun advancePage(forward: Boolean) {
        val now = System.currentTimeMillis()
        if (now - lastAdvance < 500 || pages.isEmpty()) return
        lastAdvance = now
        val next = currentPage + (if (forward) 1 else -1)
        if (next < 0 || next >= pages.size) return
        currentPage = next
        scope.launch { pushPage(next) }
    }

    // ── Image ─────────────────────────────────────────────────────────────────

    suspend fun sendImage(bmpData: ByteArray): Boolean {
        if (!leftReady && !rightReady) return false
        log("Sending image (${bmpData.size} bytes, ${G1Bmp.buildFrames(bmpData).size} frames)…")

        val frames = G1Bmp.buildFrames(bmpData)
        for (frame in frames) {
            sendBothNoResp(frame)
            delay(2)
        }
        delay(100)
        sendBoth(G1Bmp.END_CMD)
        delay(250)
        sendBoth(G1Bmp.crcCommand(bmpData))
        delay(200)
        log("Image sent")
        return true
    }

    // ── Events ────────────────────────────────────────────────────────────────

    private fun onNotification(side: String, data: ByteArray) {
        if (data.isEmpty()) return
        val cmd = data[0].toInt() and 0xFF
        if (cmd == 0x25) return  // heartbeat ack

        if (cmd == 0xF5 && data.size >= 2) {
            val code  = data[1].toInt() and 0xFF
            val label = G1Protocol.INTERACTION_LABELS[code] ?: "0x${code.toString(16).padStart(2,'0')}"
            log("$side — $label")
            when (code) {
                G1Protocol.EV_SINGLE_TAP,
                G1Protocol.EV_CHANGE_PAGE   -> advancePage(forward = side == "right")
                G1Protocol.EV_DISPLAY_READY -> { pages = emptyList(); currentPage = 0 }
            }
        } else if (cmd != 0x2C) {
            log("ble:$side 0x${cmd.toString(16).padStart(2,'0')} ${data.take(6).joinToString("") { "%02x".format(it) }}")
        }
    }

    // ── Connection state ──────────────────────────────────────────────────────

    private fun recalcState() {
        val ok = leftReady || rightReady
        _state.value = if (ok) State.CONNECTED else State.DISCONNECTED
        if (ok) { stopScan(); log("Connected — L:$leftReady R:$rightReady"); startHb() }
        else    { stopHb() }
    }

    private fun startHb() {
        hbJob?.cancel()
        hbJob = scope.launch { while (isActive) { delay(15_000); sendBoth(G1Protocol.heartbeat()) } }
    }
    private fun stopHb() { hbJob?.cancel(); hbJob = null }

    fun disconnect() {
        stopScan(); stopHb()
        leftGatt?.disconnect();  leftGatt?.close();  leftGatt  = null; leftTx  = null; leftReady  = false
        rightGatt?.disconnect(); rightGatt?.close(); rightGatt = null; rightTx = null; rightReady = false
        pages = emptyList(); currentPage = 0
        _state.value = State.DISCONNECTED
        log("Disconnected")
    }

    private fun log(msg: String) = scope.launch { _log.emit(msg) }
}

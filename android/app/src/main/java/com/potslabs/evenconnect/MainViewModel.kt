package com.potslabs.evenconnect

import android.app.Application
import android.graphics.Bitmap
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainViewModel(app: Application) : AndroidViewModel(app) {

    val ble = G1BleManager(app.applicationContext)
    val state = ble.state

    private val _log    = MutableStateFlow<List<String>>(emptyList())
    val logLines: StateFlow<List<String>> = _log.asStateFlow()

    // Image state
    private val _imageBmp    = MutableStateFlow<ByteArray?>(null)
    private val _imagePreview = MutableStateFlow<Bitmap?>(null)
    val imageBmp:     StateFlow<ByteArray?> = _imageBmp.asStateFlow()
    val imagePreview: StateFlow<Bitmap?>    = _imagePreview.asStateFlow()

    private val _imageStatus = MutableStateFlow("")
    val imageStatus: StateFlow<String> = _imageStatus.asStateFlow()

    // Compose state
    private val _composeBg      = MutableStateFlow<Bitmap?>(null)
    private val _composeLayers  = MutableStateFlow<List<TextLayer>>(listOf(TextLayer("", vAlign = VAlign.BOTTOM, hAlign = HAlign.LEFT)))
    private val _composePreview = MutableStateFlow<Bitmap?>(null)
    val composeBg:      StateFlow<Bitmap?>         = _composeBg.asStateFlow()
    val composeLayers:  StateFlow<List<TextLayer>>  = _composeLayers.asStateFlow()
    val composePreview: StateFlow<Bitmap?>          = _composePreview.asStateFlow()

    init {
        viewModelScope.launch {
            ble.log.collect { line -> _log.update { (it + line).takeLast(300) } }
        }
    }

    // ── Connection ────────────────────────────────────────────────────────────

    fun scan()       = ble.scan()
    fun disconnect() = ble.disconnect()

    // ── Text ─────────────────────────────────────────────────────────────────

    fun sendText(text: String) = ble.sendText(text)

    // ── Image ─────────────────────────────────────────────────────────────────

    fun loadImage(uri: Uri) {
        viewModelScope.launch(Dispatchers.IO) {
            _imageStatus.value = "Converting…"
            try {
                val bmp = G1Bmp.uriToGlassesBmp(getApplication(), uri)
                _imageBmp.value = bmp
                // Build a preview Bitmap from the BMP bytes for display
                val preview = android.graphics.BitmapFactory.decodeByteArray(bmp, 0, bmp.size)
                _imagePreview.value = preview
                _imageStatus.value = "Ready (${bmp.size} bytes)"
            } catch (e: Exception) {
                _imageStatus.value = "Error: ${e.message}"
            }
        }
    }

    fun sendImage() {
        val bmp = _imageBmp.value ?: return
        viewModelScope.launch {
            _imageStatus.value = "Sending…"
            val ok = ble.sendImage(bmp)
            _imageStatus.value = if (ok) "Sent ✓" else "Send failed"
        }
    }

    fun clearImage() { _imageBmp.value = null; _imagePreview.value = null; _imageStatus.value = "" }

    // ── Compose ───────────────────────────────────────────────────────────────

    fun loadComposeBg(uri: Uri) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val bmp = getApplication<Application>().contentResolver.openInputStream(uri)?.use {
                    android.graphics.BitmapFactory.decodeStream(it)
                }
                _composeBg.value = bmp
                refreshComposePreview()
            } catch (_: Exception) {}
        }
    }

    fun clearComposeBg() { _composeBg.value = null; refreshComposePreview() }

    fun updateComposeLayer(index: Int, layer: TextLayer) {
        _composeLayers.update { it.toMutableList().also { l -> if (index < l.size) l[index] = layer } }
        refreshComposePreview()
    }

    fun addComposeLayer() {
        _composeLayers.update { it + TextLayer("", vAlign = VAlign.BOTTOM, hAlign = HAlign.LEFT) }
    }

    fun removeComposeLayer(index: Int) {
        _composeLayers.update { it.toMutableList().also { l -> if (index < l.size) l.removeAt(index) } }
        refreshComposePreview()
    }

    private fun refreshComposePreview() {
        viewModelScope.launch(Dispatchers.IO) {
            val bmpBytes = G1Bmp.composeBmp(_composeBg.value, _composeLayers.value.filter { it.text.isNotBlank() })
            val preview  = android.graphics.BitmapFactory.decodeByteArray(bmpBytes, 0, bmpBytes.size)
            withContext(Dispatchers.Main) { _composePreview.value = preview }
        }
    }

    fun sendCompose() {
        viewModelScope.launch {
            val bmpBytes = withContext(Dispatchers.IO) {
                G1Bmp.composeBmp(_composeBg.value, _composeLayers.value.filter { it.text.isNotBlank() })
            }
            ble.sendImage(bmpBytes)
        }
    }

    override fun onCleared() { super.onCleared(); ble.disconnect() }
}

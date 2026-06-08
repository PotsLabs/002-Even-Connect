package com.potslabs.evenconnect

import android.content.Context
import android.graphics.*
import android.net.Uri
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.CRC32

/**
 * Converts images to the 576×136 1-bit BMP format required by the Even G1 glasses,
 * and builds the BLE frame packets for transmission.
 *
 * Polarity matches the Python _to_ready_bmp:
 *   luminance > 64  → bit 0 (pixel OFF on display)
 *   luminance ≤ 64  → bit 1 (pixel ON  on display)
 */
object G1Bmp {
    const val IMG_W = 576
    const val IMG_H = 136
    private const val PACKET_SIZE = 194
    private val BMP_ADDR = byteArrayOf(0x00, 0x1C.toByte(), 0x00, 0x00)

    val END_CMD = byteArrayOf(0x20, 0x0D, 0x0E)

    // ── Image loading ─────────────────────────────────────────────────────────

    fun uriToGlassesBmp(context: Context, uri: Uri): ByteArray {
        val src = context.contentResolver.openInputStream(uri)?.use {
            BitmapFactory.decodeStream(it)
        } ?: error("Could not decode image")
        return bitmapToGlassesBmp(src).also { src.recycle() }
    }

    fun bitmapToGlassesBmp(src: Bitmap): ByteArray {
        val scaled = Bitmap.createScaledBitmap(src, IMG_W, IMG_H, true)
        val pixels = toGrayPixels(scaled)
        if (scaled !== src) scaled.recycle()
        return buildBmp(pixels)
    }

    /** Render text lines onto a black canvas and return glasses-ready BMP bytes. */
    fun textToBmp(text: String, textSizeSp: Float = 22f): ByteArray {
        val bmp = Bitmap.createBitmap(IMG_W, IMG_H, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        canvas.drawColor(Color.BLACK)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = textSizeSp
            typeface = Typeface.MONOSPACE
        }
        var curY = 4f
        for (line in text.lines()) {
            canvas.drawText(line, 6f, curY + textSizeSp, paint)
            curY += textSizeSp + 2f
            if (curY + textSizeSp > IMG_H) break
        }
        val result = bitmapToGlassesBmp(bmp)
        bmp.recycle()
        return result
    }

    /** Composite text layers over an optional background image. */
    fun composeBmp(background: Bitmap?, textLayers: List<TextLayer>): ByteArray {
        val bmp = Bitmap.createBitmap(IMG_W, IMG_H, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        canvas.drawColor(Color.BLACK)

        if (background != null) {
            val scaled = Bitmap.createScaledBitmap(background, IMG_W, IMG_H, true)
            val grayPaint = Paint().apply {
                val cm = ColorMatrix().also { it.setSaturation(0f) }
                colorFilter = ColorMatrixColorFilter(cm)
            }
            canvas.drawBitmap(scaled, 0f, 0f, grayPaint)
            if (scaled !== background) scaled.recycle()
        }

        for (layer in textLayers) {
            val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = if (layer.light) Color.WHITE else Color.BLACK
                textSize = layer.sizeSp
                typeface = Typeface.MONOSPACE
            }
            val fm = paint.fontMetrics
            val textH = fm.bottom - fm.top
            val lines = layer.text.lines()
            val blockH = lines.size * (textH + 2f)
            val textW = lines.maxOfOrNull { paint.measureText(it) } ?: 0f

            val x = when (layer.hAlign) {
                HAlign.LEFT   -> layer.padding.toFloat()
                HAlign.CENTER -> (IMG_W - textW) / 2f
                HAlign.RIGHT  -> IMG_W - textW - layer.padding
            }
            val blockTop = when (layer.vAlign) {
                VAlign.TOP    -> layer.padding.toFloat()
                VAlign.MIDDLE -> (IMG_H - blockH) / 2f
                VAlign.BOTTOM -> IMG_H - blockH - layer.padding
            }
            lines.forEachIndexed { i, line ->
                canvas.drawText(line, x, blockTop - fm.top + i * (textH + 2f), paint)
            }
        }

        val result = bitmapToGlassesBmp(bmp)
        bmp.recycle()
        return result
    }

    // ── BMP building ──────────────────────────────────────────────────────────

    private fun toGrayPixels(bmp: Bitmap): IntArray {
        val pixels = IntArray(IMG_W * IMG_H)
        bmp.getPixels(pixels, 0, IMG_W, 0, 0, IMG_W, IMG_H)
        return pixels
    }

    private fun buildBmp(pixels: IntArray): ByteArray {
        val rowStride  = (IMG_W + 7) / 8  // 72 bytes, already 4-byte aligned
        val dataSize   = rowStride * IMG_H
        val dataOffset = 14 + 40 + 8
        val fileSize   = dataOffset + dataSize

        val buf = ByteBuffer.allocate(fileSize).order(ByteOrder.LITTLE_ENDIAN)
        // File header
        buf.put(byteArrayOf(0x42, 0x4D))
        buf.putInt(fileSize); buf.putInt(0); buf.putInt(dataOffset)
        // DIB header
        buf.putInt(40); buf.putInt(IMG_W); buf.putInt(-IMG_H)  // negative = top-down
        buf.putShort(1); buf.putShort(1)   // planes, bits/pixel
        buf.putInt(0); buf.putInt(0)        // compression, imageSize
        buf.putInt(0); buf.putInt(0)        // pixels/metre
        buf.putInt(2); buf.putInt(2)        // colors in table, important
        // Color table
        buf.put(byteArrayOf(0x00, 0x00, 0x00, 0x00))                          // 0 = black
        buf.put(byteArrayOf(0xFF.toByte(), 0xFF.toByte(), 0xFF.toByte(), 0x00)) // 1 = white
        // Pixel data
        for (y in 0 until IMG_H) {
            for (bx in 0 until rowStride) {
                var byte = 0
                for (bit in 0..7) {
                    val x = bx * 8 + bit
                    if (x < IMG_W) {
                        val p = pixels[y * IMG_W + x]
                        val lum = (Color.red(p) * 0.299 + Color.green(p) * 0.587 + Color.blue(p) * 0.114).toInt()
                        if (lum <= 64) byte = byte or (1 shl (7 - bit))  // dark = ON
                    }
                }
                buf.put(byte.toByte())
            }
        }
        return buf.array()
    }

    // ── Protocol frame builders ───────────────────────────────────────────────

    fun buildFrames(bmpData: ByteArray): List<ByteArray> {
        val frames = mutableListOf<ByteArray>()
        var offset = 0; var seq = 0
        while (offset < bmpData.size) {
            val chunk = bmpData.copyOfRange(offset, minOf(offset + PACKET_SIZE, bmpData.size))
            val header = if (seq == 0)
                byteArrayOf(0x15, (seq and 0xFF).toByte()) + BMP_ADDR
            else
                byteArrayOf(0x15, (seq and 0xFF).toByte())
            frames.add(header + chunk)
            offset += PACKET_SIZE; seq++
        }
        return frames
    }

    fun crcCommand(bmpData: ByteArray): ByteArray {
        val crc32 = CRC32()
        crc32.update(BMP_ADDR); crc32.update(bmpData)
        val crc = crc32.value
        return byteArrayOf(
            0x16,
            ((crc shr 24) and 0xFF).toByte(),
            ((crc shr 16) and 0xFF).toByte(),
            ((crc shr 8)  and 0xFF).toByte(),
            (crc           and 0xFF).toByte()
        )
    }
}

// ── Compose layer model ───────────────────────────────────────────────────────

enum class HAlign { LEFT, CENTER, RIGHT }
enum class VAlign { TOP, MIDDLE, BOTTOM }

data class TextLayer(
    val text:    String,
    val sizeSp:  Float  = 20f,
    val light:   Boolean = true,
    val hAlign:  HAlign  = HAlign.LEFT,
    val vAlign:  VAlign  = VAlign.BOTTOM,
    val padding: Int     = 8,
)

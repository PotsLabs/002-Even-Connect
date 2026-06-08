package com.potslabs.evenconnect

import java.time.LocalDateTime

object G1Protocol {
    const val UART_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    const val UART_TX      = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
    const val UART_RX      = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    const val CCCD_UUID    = "00002902-0000-1000-8000-00805f9b34fb"

    private val WEEKDAY_MAP = intArrayOf(1, 2, 3, 4, 5, 6, 0) // Python Mon=0 → G1 Sun=0

    fun timeSync(): ByteArray {
        val now = LocalDateTime.now()
        val y = now.year
        return byteArrayOf(
            0x4D, 0x0B, 0x00,
            (y and 0xFF).toByte(), ((y shr 8) and 0xFF).toByte(),
            now.monthValue.toByte(), now.dayOfMonth.toByte(),
            now.hour.toByte(), now.minute.toByte(), now.second.toByte(),
            WEEKDAY_MAP[now.dayOfWeek.value % 7].toByte(),
            0x00, 0x00
        )
    }

    fun heartbeat() = byteArrayOf(0x2C, 0x02)

    /**
     * Simple display packet: [0x4E, 0x71, len, ...text_utf8]
     *
     * Using ONLY this packet (no 0x31 AI-state packet) avoids triggering the Even AI
     * listening screen. Text is rendered directly with the 0x71 subcode.
     */
    fun textDisplayPacket(text: String): ByteArray {
        val bytes = text.toByteArray(Charsets.UTF_8)
        return byteArrayOf(0x4E, 0x71, (bytes.size and 0xFF).toByte()) + bytes
    }

    fun formatLines(text: String): List<String> {
        val lines = mutableListOf<String>()
        for (para in text.split("\n")) {
            if (para.isEmpty()) { lines.add(""); continue }
            var rem = para
            while (rem.length > 40) {
                val idx = rem.lastIndexOf(' ', 40).takeIf { it > 0 } ?: 40
                lines.add(rem.substring(0, idx))
                rem = rem.substring(idx).trimStart()
            }
            if (rem.isNotEmpty()) lines.add(rem)
        }
        return lines
    }

    fun buildPages(text: String): List<String> {
        val lines = formatLines(text)
        return lines.chunked(5).map { chunk ->
            val pad = (5 - chunk.size) / 2
            (List(pad) { "" } + chunk + List(5 - chunk.size - pad) { "" }).joinToString("\n")
        }
    }

    // Known 0xF5 subcommand codes (from Swift SDK + observed on device)
    val INTERACTION_LABELS = mapOf(
        0x00 to "Display Ready",    // exit / double-tap
        0x01 to "Change Page",      // tap in AI pagination mode
        0x02 to "Dashboard Open",
        0x03 to "Dashboard Close",
        0x06 to "Worn",
        0x07 to "Taken Off",
        0x09 to "Cradle Charged",
        0x0B to "Cradle Closed",
        0x11 to "Device Connected",
        0x12 to "Single Tap",       // observed during BMP display
        0x17 to "Trigger AI",
        0x18 to "Stop Recording",
        0x1E to "Dashboard Confirmed Open",
        0x1F to "Dashboard Confirmed Close",
    )

    const val EV_CHANGE_PAGE   = 0x01
    const val EV_SINGLE_TAP    = 0x12  // fires during text/image display
    const val EV_DISPLAY_READY = 0x00
}

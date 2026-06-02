"""
G1 command builders — pure functions that return bytes, no BLE I/O.

Sources:
  - g1-sample G1BluetoothManager.swift (authoritative implementations)
  - even_glasses/utils.py (construct_* functions)
  - eveng1_python_sdk/services/display.py
"""

import zlib
from .constants import (
    Cmd, DisplayStatus, ScreenAction, MicState, SilentMode,
    DashboardMode, DashboardPosition, TranslateLang,
    BMP_WIDTH, BMP_HEIGHT,
)


# ── Connection ─────────────────────────────────────────────────────────────────

def build_init() -> bytes:
    """[0x4D, 0x01] — send after connecting to both glasses."""
    return bytes([Cmd.INIT, 0x01])


def build_heartbeat() -> bytes:
    """[0x25, 0x02] — keep-alive, send every 15 s to both glasses."""
    return bytes([Cmd.HEARTBEAT, 0x02])


def build_exit_all() -> bytes:
    """[0x18] — exit all active functions and return to dashboard/idle."""
    return bytes([Cmd.EXIT_ALL])


# ── Text display ───────────────────────────────────────────────────────────────
# The official G1 SDK (g1-sample) uses a two-packet approach for text:
#   1. Direct subcode packet:  [0x4E, 0x71, len, ...utf8]
#   2. AI result packet:       [0x4E, seq, total, current, status, 0, 0, page, max, ...utf8]
# Packet 1 renders immediately; packet 2 sets pagination state for tap-to-advance.
# For simple single-page sends, only packet 2 is needed.

def build_text_direct(text: str) -> bytes:
    """
    [0x4E, 0x71, len, ...utf8] — immediate render, no Even AI chrome.
    Use for live preview / single-shot display where tap-to-advance is not needed.
    0x71 = SIMPLE_TEXT | NEW_CONTENT — confirmed in g1-sample sendTextPacket().
    """
    data = text.encode("utf-8")
    return bytes([Cmd.SEND_RESULT, 0x71, len(data) & 0xFF]) + data


def build_text_packet(
    text: str,
    seq: int = 0,
    total_pages: int = 1,
    current_page: int = 1,
    max_pages: int = 1,
    status: int = DisplayStatus.SIMPLE_TEXT,
    new_content: bool = True,
) -> bytes:
    """
    Full 0x4E AI-result packet — sets pagination state so firmware routes taps.
    status defaults to SIMPLE_TEXT (0x70) to avoid the Even AI recording overlay.
    Pass status=DisplayStatus.FINAL_TEXT (0x40) on the last page to dismiss overlay.
    """
    screen_status = status | (ScreenAction.NEW_CONTENT if new_content else 0)
    data = text.encode("utf-8")
    header = bytes([
        Cmd.SEND_RESULT,
        seq & 0xFF,
        total_pages & 0xFF,
        (current_page - 1) & 0xFF,   # 0-indexed current package
        screen_status & 0xFF,
        0x00, 0x00,                   # char position
        current_page & 0xFF,
        max_pages & 0xFF,
    ])
    return header + data


def build_display_complete(seq: int = 0) -> bytes:
    """
    [0x4E, seq, 1, 0, 0x40, 0, 0, 0, 1] — signal display complete.
    Sends FINAL_TEXT status to dismiss the Even AI recording overlay after BMP display.
    """
    return build_text_packet("", seq=seq, status=DisplayStatus.FINAL_TEXT, new_content=True)


# ── Device settings ────────────────────────────────────────────────────────────

def build_brightness(level: int, auto: bool = False) -> bytes:
    """
    [0x01, level, auto] — set display brightness.
    level: 0x00–0x29 (0–41). Source: g1-sample setBrightness().
    """
    level = max(0x00, min(0x29, level))
    return bytes([Cmd.BRIGHTNESS, level, 0x01 if auto else 0x00])


def build_silent_mode(enabled: bool) -> bytes:
    """[0x03, 0x0C|0x0A, 0x00] — enable/disable silent mode."""
    return bytes([Cmd.SILENT_MODE, SilentMode.ON if enabled else SilentMode.OFF, 0x00])


def build_tilt_angle(degrees: int) -> bytes:
    """
    [0x0B, degrees, 0x01] — set head-up display tilt angle.
    degrees: 0–60. Source: g1-sample setTiltAngle().
    """
    degrees = max(0, min(60, degrees))
    return bytes([Cmd.TILT_ANGLE, degrees & 0xFF, 0x01])


def build_mic(on: bool) -> bytes:
    """[0x0E, 0x01|0x00] — enable/disable right-glass microphone."""
    return bytes([Cmd.OPEN_MIC, MicState.ON if on else MicState.OFF])


# ── Dashboard ──────────────────────────────────────────────────────────────────

def build_dashboard_mode(mode: DashboardMode = DashboardMode.FULL) -> bytes:
    """
    [0x06, 0x07, 0x00, 0x00, 0x06, mode, 0x00] — set dashboard layout mode.
    Source: g1-sample setDashboardMode().
    """
    return bytes([Cmd.DASHBOARD_SHOW, 0x07, 0x00, 0x00, 0x06, int(mode), 0x00])


def build_dashboard_position(position: DashboardPosition, visible: bool = True) -> bytes:
    """
    [0x26, 0x07, 0x00, 0x01, 0x02, state, position] — set dashboard height.
    Source: g1-sample setDashboardPosition() / hideDashboard().
    """
    return bytes([
        Cmd.DASHBOARD_POS,
        0x07, 0x00, 0x01, 0x02,
        0x01 if visible else 0x00,
        int(position),
    ])


def build_dashboard_distance(distance: int) -> bytes:
    """
    [0x26, 0x80, 0x00, 0x00, 0x02, 0x01, 0x04, distance] — set dashboard depth.
    distance: 1–9. Source: g1-sample setDashboardDistance().
    """
    distance = max(1, min(9, distance))
    return bytes([Cmd.DASHBOARD_POS, 0x80, 0x00, 0x00, 0x02, 0x01, 0x04, distance])


# ── Translation ────────────────────────────────────────────────────────────────

def build_translation_setup() -> bytes:
    """[0x39, 0x05, 0x00, 0x00, 0x13] — initialize translation mode."""
    return bytes([Cmd.TRANSLATE_SETUP, 0x05, 0x00, 0x00, 0x13])


def build_translation_start() -> bytes:
    """[0x50, 0x06, 0x00, 0x00, 0x01, 0x01] — start translation on right glass."""
    return bytes([Cmd.TRANSLATE_START, 0x06, 0x00, 0x00, 0x01, 0x01])


def build_translation_config(src: TranslateLang, tgt: TranslateLang) -> bytes:
    """[0x1C, 0x00, src, tgt] — set translation language pair."""
    return bytes([Cmd.TRANSLATE_CFG, 0x00, int(src), int(tgt)])


def build_translation_init_channel(cmd_byte: int, seq: int) -> bytes:
    """
    [cmd, seq, 0x01, 0x00, 0x00, 0x00, 0x00, 0x0D] — initialize a translation display channel.
    cmd_byte: Cmd.TRANSLATE_ORIG (0x0F) or Cmd.TRANSLATE_XLAT (0x0D).
    Source: g1-sample startTranslation().
    """
    return bytes([cmd_byte, seq & 0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x0D])


def build_translation_send(cmd_byte: int, seq: int, text: str) -> bytes:
    """
    [cmd, seq, 0x01, 0x00, 0x00, 0x00, 0x20, 0x0D, ...utf8]
    cmd_byte: Cmd.TRANSLATE_ORIG or Cmd.TRANSLATE_XLAT.
    Source: g1-sample sendTranslation().
    """
    return bytes([cmd_byte, seq & 0xFF, 0x01, 0x00, 0x00, 0x00, 0x20, 0x0D]) + text.encode("utf-8")


# ── Time sync ─────────────────────────────────────────────────────────────────

def build_time_sync(now: "datetime") -> bytes:
    """
    [0x4D, 0x0B, 0x00, year_lo, year_hi, month, day, hour, min, sec, weekday, 0x00, 0x00]
    Weekday is remapped from Python (0=Mon) to glasses (0=Sun) via WEEKDAY_OFFSET.
    Source: api.py _construct_time_sync().
    """
    from .constants import WEEKDAY_OFFSET
    year = now.year
    return bytes([
        Cmd.INIT,
        0x0B, 0x00,                          # payload length 11, little-endian
        year & 0xFF,
        (year >> 8) & 0xFF,
        now.month,
        now.day,
        now.hour,
        now.minute,
        now.second,
        WEEKDAY_OFFSET[now.weekday()],
        0x00, 0x00,                          # reserved
    ])


# ── Battery ────────────────────────────────────────────────────────────────────

def build_battery_request() -> bytes:
    """[0x2C, 0x01] — request battery level from both glasses."""
    return bytes([Cmd.HEARTBEAT_ALT, 0x01])


# ── Notifications ──────────────────────────────────────────────────────────────

def build_notification_chunks(msg_id: int, app_id: str, title: str, message: str) -> list[bytes]:
    """
    Encode an NCS notification as chunked 0x4B packets (max 176 bytes payload each).
    Source: even_glasses/models.py Notification.construct_notification().
    """
    import json, time
    from datetime import datetime
    payload = json.dumps({
        "ncs_notification": {
            "msg_id": msg_id,
            "type": 1,
            "app_identifier": app_id,
            "title": title,
            "subtitle": "",
            "message": message,
            "time_s": int(time.time()),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "display_name": app_id,
        },
        "type": "Add",
    }).encode("utf-8")

    chunks = []
    max_chunk = 176
    parts = [payload[i:i + max_chunk] for i in range(0, len(payload), max_chunk)]
    for idx, part in enumerate(parts):
        header = bytes([Cmd.NOTIFICATION, msg_id & 0xFF, len(parts) & 0xFF, idx & 0xFF])
        chunks.append(header + part)
    return chunks

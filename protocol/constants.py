"""
G1 protocol constants — all command bytes, enums, and UUIDs.

Primary source: g1-sample/CommandsEnum.swift, DisplayStatusEnum.swift, DeviceOrdersEnum.swift
Cross-checked:  even_glasses/models.py, eveng1_python_sdk/utils/constants.py
"""

from enum import IntEnum


# ── BLE UUIDs ─────────────────────────────────────────────────────────────────

UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_UUID      = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_UUID      = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"


# ── Primary commands (first byte of every packet) ─────────────────────────────
# Source: g1-sample CommandsEnum.swift + even_glasses/models.py Command enum

class Cmd(IntEnum):
    BRIGHTNESS       = 0x01   # [0x01, level 0x00–0x29, auto 0|1]
    SILENT_MODE      = 0x03   # [0x03, 0x0C=on / 0x0A=off, 0x00]
    DASHBOARD_SHOW   = 0x06   # dashboard mode/position/time-weather
    TILT_ANGLE       = 0x0B   # [0x0B, degrees 0–60, 0x01]
    OPEN_MIC         = 0x0E   # [0x0E, 0x01=on / 0x00=off]
    TRANSLATE_ORIG   = 0x0F   # translation — original text channel
    TRANSLATE_XLAT   = 0x0D   # translation — translated text channel
    BMP_FRAME        = 0x15   # image data chunks (194 bytes each)
    BMP_END          = 0x20   # [0x20, 0x0D, 0x0E] — end of BMP transfer
    BMP_CRC          = 0x16   # [0x16, crc32_be(addr+data)]
    QUICK_NOTE       = 0x1E   # quick note add / delete
    QUICK_NOTE_2     = 0x21   # alternate quick note command seen in g1-sample
    DASHBOARD        = 0x22   # dashboard content command
    HEARTBEAT        = 0x25   # [0x25, 0x02] — keep-alive (0x2C also used)
    HEARTBEAT_ALT    = 0x2C   # [0x2C, 0x02] — heartbeat / also battery response
    DASHBOARD_POS    = 0x26   # dashboard position/distance
    GLASSES_WEAR     = 0x27   # wear detection enable/disable
    TRANSLATE_SETUP  = 0x39   # [0x39, 0x05, 0x00, 0x00, 0x13]
    TRANSLATE_START  = 0x50   # [0x50, 0x06, 0x00, 0x00, 0x01, 0x01]
    SEND_RESULT      = 0x4E   # display text / AI result (main display command)
    INIT             = 0x4D   # [0x4D, 0x01] — connection init
    NOTIFICATION     = 0x4B   # NCS notification (JSON payload)
    EXIT_ALL         = 0x18   # [0x18] — exit all functions / clear screen
    TRANSLATE_CFG    = 0x1C   # [0x1C, 0x00, src_lang, tgt_lang]
    DEVICE_ORDER     = 0xF5   # tap/gesture events FROM glasses + AI control TO glasses
    MIC_DATA         = 0xF1   # raw PCM audio stream FROM glasses


# ── Response bytes ─────────────────────────────────────────────────────────────

class Response(IntEnum):
    ACK  = 0xC9
    NACK = 0xCA


# ── Display status byte (byte 4 of 0x4E command) ──────────────────────────────
# Source: g1-sample DisplayStatusEnum.swift — most authoritative naming found.
#
# Used as: screen_status = DisplayStatus.SIMPLE_TEXT | ScreenAction.NEW_CONTENT
#
# CRITICAL: SIMPLE_TEXT (0x70) is the non-AI mode — use this to avoid the
# "Release to Finish recording" overlay. NORMAL_TEXT (0x30) activates Even AI
# chrome and should only be used when intentionally invoking the Even AI pipeline.

class DisplayStatus(IntEnum):
    NORMAL_TEXT  = 0x30   # Even AI displaying (automatic mode) — shows recording overlay
    FINAL_TEXT   = 0x40   # Even AI display complete — dismisses recording overlay
    MANUAL_PAGE  = 0x50   # Even AI manual/tap-to-advance mode
    ERROR_TEXT   = 0x60   # Even AI network error state
    SIMPLE_TEXT  = 0x70   # Direct text show — NO Even AI chrome (use this by default)


class ScreenAction(IntEnum):
    NEW_CONTENT = 0x01    # OR with DisplayStatus to indicate new content


# ── Device orders (0xF5 sub-commands FROM glasses) ────────────────────────────
# Source: g1-sample DeviceOrdersEnum.swift

class DeviceOrder(IntEnum):
    DISPLAY_READY         = 0x00   # glasses finished displaying, ready for next
    TRIGGER_CHANGE_PAGE   = 0x01   # tap — advance page
    TRIGGER_FOR_AI        = 0x17   # long press — user wants Even AI (decimal 23)
    TRIGGER_STOP_RECORD   = 0x18   # release after long press — stop recording (decimal 24)
    G1_IS_READY           = 0x09   # glasses booted and ready
    CASE_BATTERY          = 0x0F   # case battery level (follows 0xF5 response)


# ── Dashboard modes ────────────────────────────────────────────────────────────
# Source: g1-sample DisplayStatusEnum.swift DashboardMode

class DashboardMode(IntEnum):
    FULL    = 0x00
    DUAL    = 0x01
    MINIMAL = 0x02


class DashboardPosition(IntEnum):
    BOTTOM = 0x00
    P1     = 0x01
    P2     = 0x02
    P3     = 0x03
    P4     = 0x04
    P5     = 0x05
    P6     = 0x06
    P7     = 0x07
    TOP    = 0x08


# ── Mic / silent mode ─────────────────────────────────────────────────────────

class MicState(IntEnum):
    OFF = 0x00
    ON  = 0x01

class SilentMode(IntEnum):
    OFF = 0x0A
    ON  = 0x0C


# ── Translation languages ──────────────────────────────────────────────────────
# Source: g1-sample CommandsEnum.swift TranslateLanguage

class TranslateLang(IntEnum):
    CHINESE    = 0x01
    ENGLISH    = 0x02
    JAPANESE   = 0x03
    KOREAN     = 0x04
    FRENCH     = 0x05
    GERMAN     = 0x06
    SPANISH    = 0x07
    RUSSIAN    = 0x08
    DUTCH      = 0x09
    NORWEGIAN  = 0x0A
    DANISH     = 0x0B
    SWEDISH    = 0x0C
    FINNISH    = 0x0D
    ITALIAN    = 0x0E
    ARABIC     = 0x0F
    HINDI      = 0x10
    BENGALI    = 0x11
    CANTONESE  = 0x12


# ── BMP image constants ────────────────────────────────────────────────────────

BMP_WIDTH       = 576
BMP_HEIGHT      = 136
BMP_PACKET_SIZE = 194
BMP_ADDR        = bytes([0x00, 0x1C, 0x00, 0x00])  # Even AI flash slot
BMP_END_CMD     = bytes([0x20, 0x0D, 0x0E])


# ── Time sync ──────────────────────────────────────────────────────────────────
# Python's weekday() returns 0=Mon…6=Sun; glasses firmware expects 0=Sun…6=Sat.
# Source: api.py _PY_TO_GLASS_WEEKDAY

WEEKDAY_OFFSET: list[int] = [1, 2, 3, 4, 5, 6, 0]


# ── 0xF5 sub-command event labels (inbound FROM glasses) ──────────────────────
# Maps the second byte of every 0xF5 notification to a human-readable label.
# Source: api.py _INTERACTION_LABELS

F5_EVENTS: dict[int, str] = {
    0x00: "Display Ready",            # user exited or display finished rendering
    0x01: "Change Page",              # single tap — advance page in manual mode
    0x02: "Dashboard Open",
    0x03: "Dashboard Close",
    0x04: "Silent Mode On",
    0x05: "Silent Mode Off",
    0x06: "Worn",
    0x07: "Taken Off",
    0x08: "Cradle Open",
    0x09: "Cradle Charged",
    0x0B: "Cradle Closed",
    0x0F: "Case Battery",             # 3rd byte = battery % of charging case
    0x11: "Device Connected",
    0x17: "Trigger AI",               # long press — user invokes Even AI (decimal 23)
    0x18: "Stop Recording",           # long press released — recording ended (decimal 24)
    0x1E: "Dashboard Confirmed Open",
    0x1F: "Dashboard Confirmed Close",
}


# ── Inbound commands to suppress in event logs (too noisy) ────────────────────
# Source: api.py _KNOWN_SILENT

SILENT_CMDS: set[int] = {
    0x25,   # heartbeat ack
}


# ── System font search paths for BMP text rendering ───────────────────────────
# Tried in order; first existing file wins. Source: api.py _FONT_PATHS.

FONT_PATHS: list[str] = [
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

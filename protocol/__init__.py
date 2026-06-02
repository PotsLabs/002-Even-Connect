"""
G1 BLE protocol — canonical reference for KiroshiOS.

Sources cross-referenced:
  - g1-sample (Even Realities official Swift SDK)
  - eveng1_python_sdk (local)
  - even_glasses (pip package)

Import pattern:
    from protocol.constants import Cmd, DisplayStatus, DeviceOrder
    from protocol.commands import build_text, build_heartbeat, build_brightness
    from protocol.bmp import to_bmp_bytes, build_frames, build_crc_cmd, DISPLAY_COMPLETE
"""

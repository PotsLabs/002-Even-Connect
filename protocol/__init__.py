"""
G1 BLE protocol — canonical reference for KiroshiOS.

A self-contained package for communicating with Even Realities G1 smart glasses.
No external dependencies beyond bleak + PIL; no FastAPI or HTTP required.

Sources:
  - g1-sample (Even Realities official Swift SDK)
  - eveng1_python_sdk (local Python SDK)
  - even_glasses (pip package reference)

Architecture:
  - connect.py       : BLE connection, discovery, heartbeat, text/image pipelines
  - commands.py      : Packet builders (pure bytes)
  - bmp.py           : Image encoding, layer composition (pure bytes)
  - constants.py     : All enums, UUIDs, dimensions, event labels

Main APIs:

  Connection & Discovery:
    from protocol.connect import GlassesManager
    manager = GlassesManager()
    await manager.scan_and_connect(timeout=12)
    await manager.sync_time()
    await manager.set_event_handler(on_event)
    await manager.disconnect_all()

  Text Sending:
    from protocol.connect import send_text, send_page, step_text_page
    await send_text(manager, "Hello\nWorld")
    await send_page(manager, "Page 1", page_number=1, max_pages=2)
    await step_text_page(manager, forward=True)  # advance on tap

  Image Sending (Stereo):
    from protocol.connect import stereo_pair, send_bmp_to_glass
    left_bmp, right_bmp = stereo_pair(
        layers=[(image_bytes, 0.5)],  # (image, z-depth)
        max_disparity=10
    )
    await send_bmp_to_glass(manager.left_glass, left_bmp)
    await send_bmp_to_glass(manager.right_glass, right_bmp)

  Pure BMP Functions:
    from protocol.bmp import to_bmp_bytes, build_frames, compose_layers, compute_depth
    bmp = to_bmp_bytes(image_bytes)
    frames = build_frames(bmp)

  Packet Builders:
    from protocol.commands import build_text_packet, build_brightness, build_tilt_angle
    from protocol.constants import Cmd, DisplayStatus

Example: Full workflow
    from protocol.connect import GlassesManager, send_text

    manager = GlassesManager()
    if await manager.scan_and_connect(timeout=12):
        await manager.sync_time()
        await send_text(manager, "Hello glasses!")
        await manager.disconnect_all()
"""

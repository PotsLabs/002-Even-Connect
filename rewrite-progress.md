# api_v2.py — Rewrite Progress

> Status as of 2026-06-08. Tracking core pipeline completion: connection, text, image/stereo, compose.

---

## Current State: Ready for Testing

**Connection** ✅ 100% wired:
- GET `/api/status` (line 646) → `_connection_status(manager)`
- POST `/api/disconnect` (line 651) → `manager.disconnect_all()`
- GET `/api/events/stream` (line 657) → SSE logging relay
- POST `/api/connect-stream` (line 710) → Full SSE with scan/connect/sync/handlers

**Known Issues**:
- Line 724: Formatter string `%{levelname}s` should be `%(levelname)s` (cosmetic, won't crash)
- Lines 789–805: Dead code `connect_pipeline()` without decorator (safe to delete)
- Key mismatch: Returns `left_name`/`right_name` (snake_case) but frontend expects `leftName`/`rightName` (camelCase)

---

## Pipelines (as implemented)

### Connection (via SSE)
```
POST /api/connect-stream
  → _do_connect() async task
    → GlassesManager() instance
    → scan_and_connect(timeout=12)
    → _sync_time(manager)
    → _install_event_handlers(manager)
  → yields: log messages, then __DONE__{json} or __FAIL__{error}
```

### Text Send
```
POST /api/send-text (line 564)
  → _send_text(manager, text)
    → split into 5-line pages, store in _text_session
    → await _send_page(mgr, page[0], 1, total, seq=0)

Inbound tap event:
  → _glass_event_handler (line 405)
    → if code == PageControl: _step_text_page(manager, forward)
      → _send_page(mgr, page[idx], idx+1, total)
```

### Image/Stereo Send (using only stereo-compose path)
```
POST /api/send-stereo-compose (line 810)
  → image_pipeline(layers, max_disparity)
    → [_img_bmp_bytes(img) for img, z in layers] → [(bmp, z), ...]
    → _stereo_pair(bmp_layers, max_disparity)
      → _compute_depth(layers, max_disparity) → (left_layers, right_layers)
      → _compose_bmp(left_layers) → left_bmp
      → _compose_bmp(right_layers) → right_bmp
    → asyncio.gather(
        _send_bmp_to_glass(manager.left_glass, left_bmp),
        _send_bmp_to_glass(manager.right_glass, right_bmp),
      )
        → _build_image_frames(bmp)
        → _image_ACK_confirmation(glass, frames, end_cmd, crc_cmd)
          → write frames (0x002 gap)
          → _glass_request_check(end_cmd) → await 0xC9
          → _glass_request_check(crc_cmd) → await 0xC9
          → write _DISPLAY_COMPLETE
```

---

## Task Status

### Connection (SSE-driven)

| Done | Task | api_v2.py fn | Lines |
|------|------|--------------|-------|
| ✅ | BLE base class | `BleDevice` | 160–254 |
| ✅ | Single glass + heartbeat | `Glass` | 256–302 |
| ✅ | Scan + connect both | `GlassesManager.scan_and_connect` | 329–359 |
| ✅ | Disconnect both | `GlassesManager.disconnect_all` | 361–374 |
| ✅ | Time sync packet | `_construct_time_sync` | 388–403 |
| ✅ | Send time sync | `_sync_time` | 379–385 |
| ✅ | Install event handlers | `_install_event_handlers` | 425–429 |
| ✅ | Connection status dict | `_connection_status` | 431–441 |
| ✅ | FastAPI + CORS | `app = FastAPI()` | 135–143 |
| ✅ | GET /api/status | — | 646–648 |
| ✅ | POST /api/disconnect | — | 651–654 |
| ✅ | GET /api/events/stream | — | 657–679 |
| ✅ | POST /api/connect-stream | `connect_stream()` | 710–784 |
| ⚠️ | Dead code cleanup | `connect_pipeline()` | 789–805 (no decorator, unreachable) |

### Text Send

| Done | Task | api_v2.py fn | Lines |
|------|------|--------------|-------|
| ✅ | Paginate text | `_send_text` | 564–579 |
| ✅ | Send one page | `_send_page` | 583–602 |
| ✅ | Advance on tap | `_step_text_page` | 605–620 |
| ✅ | Event handler | `_glass_event_handler` | 405–421 |
| ✅ | Broadcast to queues | `_broadcast` | 555–560 |
| ⬜ | POST /api/send-text decorator | — | (has decorator, wrong signature) |

### Image Send (Stereo-Compose Only)

| Done | Task | api_v2.py fn | Lines |
|------|------|--------------|-------|
| ✅ | Image → 1-bit BMP | `_img_bmp_bytes` | 454–465 |
| ✅ | Build 0x15 frames | `_build_image_frames` | 468–476 |
| ✅ | CRC checksum | `_crc_checksum` | 449–452 |
| ✅ | Depth shift (z → pixel shift) | `_compute_depth` | 480–486 |
| ✅ | AND-blend layers | `_compose_bmp` | 490–510 |
| ✅ | Stereo pair orchestrator | `_stereo_pair` | 625–630 |
| ✅ | ACK handshake | `_glass_request_check` | 533–548 |
| ✅ | Frame send + ACK loop | `_image_ACK_confirmation` | 521–530 |
| ✅ | Top-level BMP send | `_send_bmp_to_glass` | 635–638 |
| ✅ | POST /api/send-stereo-compose | `image_pipeline()` | 810–819 |

### Compose (Text + Image Layers)

| Done | Task | api_v2.py fn | Lines |
|------|------|--------------|-------|
| ⬜ | Font loading | — | (not in api_v2.py) |
| ⬜ | Text rendering | — | (not in api_v2.py) |
| ⬜ | Pydantic payload model | `TextBlock`, `ImageLayer`, `ComposePayload` | 688–704 |
| ⬜ | POST /api/preview-compose | — | |
| ⬜ | POST /api/send-compose | — | |
| ⬜ | POST /api/preview-stereo-compose | — | |
| ⬜ | BMP → PNG preview | `_bmp_to_preview_png` | 512–517 (no decorator) |

### Data Connections (Obsidian)

| Done | Task | api_v2.py fn |
|------|------|--------------|
| ✅ | Obsidian integration module | `integrations/obsidian.py` |
| ✅ | Fetch notes + attachments | `ObsidianVault`, `sync_note()`, `send_obsidian_image()` |
| ⬜ | REST API proxy in api_v3.py | (defer) |

---

## Deferred / Nice-to-Have

### Preview Endpoints
- **`/api/preview-bmp`** — show what image looks like after conversion to 1-bit BMP
- **`/api/preview-stereo-compose`** — show left/right stereo pair before sending
- **Why removed:** Not core functionality; can be added back by calling `to_bmp_bytes()` + returning data URI
- **When:** Circle back after core pipeline is stable and tested
- **How:** Simple endpoint that takes image bytes, returns PNG data URL (no protocol changes needed)

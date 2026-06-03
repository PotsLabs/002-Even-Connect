# DATA_FLOW.md
> How information moves through the codebase — file by file, function by function.

---

## Architecture overview

```
┌──────────────────────────────────────────────────┐
│  React Frontend  (frontend/src/)                 │
│  App.jsx → tabs → api.js (fetch)                 │
└────────────────────┬─────────────────────────────┘
                     │ HTTP / SSE  (localhost:8000)
┌────────────────────▼─────────────────────────────┐
│  FastAPI Backend  (api.py)                        │
│  image pipeline · text paging · event broadcast  │
└──────────┬─────────────────────────┬─────────────┘
           │ even_glasses SDK        │ protocol/
           │ (BLE manager)           │ (pure byte builders)
┌──────────▼─────────────────────────▼─────────────┐
│  BLE layer  (bleak / GlassesManager)              │
│  UART TX/RX  ←→  Even G1 glasses firmware        │
└──────────────────────────────────────────────────┘
```

---

## 1. Entry points

| File | Role |
|---|---|
| `api.py` | FastAPI app + all HTTP routes + BLE orchestration |
| `frontend/src/main.jsx` | React app mount |
| `start.sh` | Shell launcher (starts uvicorn, opens browser) |

---

## 2. Backend — `api.py`

Single file; split here by responsibility.

### 2a. Global state (module-level)

| Name | Type | What it holds |
|---|---|---|
| `manager` | `GlassesManager` | Live BLE connection to both glasses |
| `is_connecting` | `bool` | Lock to prevent concurrent scan attempts |
| `_frame_cache` | `dict[str, dict]` | Precomputed BMP frames keyed by UUID |
| `_text_session` | `dict` | Active paginated text: pages, current index, total |
| `_event_subscribers` | `list[Queue]` | One asyncio Queue per open SSE client |

---

### 2b. BLE connection functions

```
connect()                     POST /api/connect
  └─ GlassesManager.scan_and_connect()
  └─ _sync_time(manager)
  └─ _install_event_handlers(manager)

connect_stream()              POST /api/connect-stream   (SSE)
  └─ same as above, but streams SDK log lines to the browser in real time
  └─ terminal signal: __DONE__{json} or __FAIL__{reason}

disconnect()                  POST /api/disconnect
  └─ manager.disconnect_all()

get_status()                  GET  /api/status
  └─ _connection_status() → {connected, left, right, leftName, rightName}
```

**Helper:**
- `_connection_status()` — reads `manager.left_glass` / `manager.right_glass`, returns dict

---

### 2c. Text display functions

```
send_text_endpoint()          POST /api/send-text
  └─ _send_text(manager, text)
       └─ format_text_lines(text_message)        # from even_glasses SDK
       └─ splits into 5-line pages
       └─ _send_page(mgr, page_text, page_num, max_pages)
            ├─ sends [0x4E, 0x71, len, ...utf8] to both glasses  (direct render)
            └─ send_text_packet(...)              # pagination state for tap routing

send_sample()                 POST /api/debug/send-sample
  └─ calls _send_text() with hardcoded _SAMPLE_TEXT
```

**Tap-to-advance (inbound event → page change):**
```
_glass_event_handler(glass, sender, data)
  └─ fires on every BLE notification from either glass
  └─ if cmd == 0xF5, code == 0x01 (Change Page):
       └─ _step_text_page(forward=True/False)
            └─ _send_page(manager, pages[next_idx], ...)
```

**Helpers:**
- `_send_page()` — sends the dual-packet for one page to both glasses
- `_step_text_page()` — debounced (0.5 s), advances `_text_session`
- `_construct_time_sync()` — builds 0x4D time-sync packet
- `_sync_time(manager)` — sends time-sync to both glasses

---

### 2d. Image pipeline functions

**Conversion (CPU, can run in thread pool):**

| Function | Input | Output |
|---|---|---|
| `_to_bmp_bytes(image_bytes)` | any image format | 576×136 1-bit BMP (black canvas letterbox) |
| `_invert_bmp(bmp_data)` | 1-bit BMP | pixel-inverted 1-bit BMP |
| `_to_ready_bmp(image_bytes)` | any image format | single-pass convert+invert — used for precompute |
| `_to_stereo_bmp_pair(image_bytes, ...)` | any image | (left BMP, right BMP) — luminance-based depth shift |

**Framing (CPU, fast):**

| Function | Input | Output |
|---|---|---|
| `_build_image_frames(bmp_data)` | BMP bytes | list of 0x15 protocol packets (194-byte chunks) |
| `_crc_command(bmp_data)` | BMP bytes | 6-byte 0x16 CRC packet (CRC32 over addr+data) |

**BLE transmission (async):**

| Function | What it does |
|---|---|
| `_send_image_to_glass(glass, frames, end_cmd, crc_cmd)` | writes frames, sends end command, verifies CRC ack, sends DISPLAY_COMPLETE |
| `_transmit_image(left_glass, right_glass, bmp_data)` | builds frames, sends to both glasses concurrently via `asyncio.gather` |

**Routes:**
```
send_image_endpoint()         POST /api/send-image
  └─ _invert_bmp(_to_bmp_bytes(decoded_b64))
  └─ _transmit_image(left, right, bmp)

send_stereo_image_endpoint()  POST /api/send-stereo-image
  └─ _to_stereo_bmp_pair(image_bytes, maxDisparity, blurRadius, invertDepth)
  └─ _send_image_to_glass(left, left_frames, end_cmd, left_crc)   ─┐ concurrent
  └─ _send_image_to_glass(right, right_frames, end_cmd, right_crc) ┘

preview_bmp()                 POST /api/preview-bmp
  └─ _to_bmp_bytes()  →  PNG base64 returned (no BLE)

preview_stereo_bmp()          POST /api/preview-stereo-bmp
  └─ _to_stereo_bmp_pair()  →  {left: png_b64, right: png_b64}
```

---

### 2e. Precompute queue functions

Converts images to frames in a background thread pool and caches them — removes PIL work from the BLE send hot path.

```
precompute_queue()            POST /api/queue/precompute
  └─ for each image in payload:
       ├─ mode="stereo"  → _to_stereo_bmp_pair() in executor
       │                 → caches {left_frames, right_frames, left_crc, right_crc}
       └─ mode="standard"→ _to_ready_bmp() in executor
                          → caches {frames, crc}

send_precomputed()            POST /api/send-precomputed/{image_id}
  └─ looks up _frame_cache[image_id]
  └─ sends cached frames (no PIL work)

delete_precomputed()          DELETE /api/queue/precomputed/{image_id}
  └─ pops from _frame_cache
```

---

### 2f. Compose functions

Composite renderer: background image + ordered image layers + text blocks → single BMP.

**Render helpers (CPU):**

| Function | What it does |
|---|---|
| `_compose_bmp(background_b64, blocks, image_layers)` | renders all layers onto 576×136 canvas, returns BMP |
| `_compose_stereo_bmp_pair(background_b64, blocks, max_disparity, background_z, image_layers)` | same, but generates separate left/right canvases shifted by each layer's z-depth |
| `_render_image_layer(canvas, layer, x_offset)` | OR-composites an ImageLayer onto existing canvas |
| `_render_block(draw, block, x_offset)` | draws a TextBlock with position/size/color/padding |
| `_shift_canvas(canvas, x_offset)` | translates canvas content horizontally (stereo parallax) |
| `_get_font(size)` | loads font from _FONT_PATHS, caches by size |
| `_bmp_to_preview_png(bmp_data)` | converts 1-bit BMP → PNG base64 for browser preview |

**Routes:**
```
preview_compose()             POST /api/preview-compose
  └─ _compose_bmp() → PNG preview (no BLE)

send_compose()                POST /api/send-compose
  └─ _compose_bmp() → _transmit_image(left, right, bmp)

precompute_compose()          POST /api/precompute-compose
  └─ _compose_bmp() → stores in _frame_cache → returns id + PNG thumbnail

preview_stereo_compose()      POST /api/preview-stereo-compose
  └─ _compose_stereo_bmp_pair() → {left: png, right: png}

send_stereo_compose()         POST /api/send-stereo-compose
  └─ _compose_stereo_bmp_pair()
  └─ _send_image_to_glass() ×2 concurrent
```

---

### 2g. Event stream (glasses → browser)

```
_glass_event_handler(glass, sender, data)   ← BLE notification callback
  └─ parses cmd byte:
       0xF5 → touchpad/wear event → _broadcast("INFO:touchpad:…")
       0x27 → wear detection     → _broadcast("INFO:wear:…")
       other                     → _broadcast("DEBUG:ble:…")
  └─ if 0xF5 subcode 0x01 → _step_text_page()
  └─ if 0xF5 subcode 0x00 → clears _text_session

_broadcast(line)
  └─ puts line into every queue in _event_subscribers

events_stream()               GET /api/events/stream    (SSE)
  └─ registers a new Queue in _event_subscribers
  └─ streams lines as SSE events
  └─ removes Queue on disconnect
```

---

### 2h. Obsidian proxy functions

All routes under `/api/obsidian/` proxy to the Obsidian Local REST API plugin.

| Route | Function | What it does |
|---|---|---|
| `GET /api/obsidian/config` | `obsidian_get_config()` | Returns current URL + masked key |
| `POST /api/obsidian/config` | `obsidian_set_config()` | Saves URL + API key to `_obsidian_cfg` |
| `GET /api/obsidian/ping` | `obsidian_ping()` | Tests Obsidian reachability |
| `GET /api/obsidian/files` | `obsidian_list_files()` | Lists vault files |
| `GET /api/obsidian/file/{path}` | `obsidian_get_file()` | Reads a note |
| `PUT /api/obsidian/file/{path}` | `obsidian_write_file()` | Creates/overwrites a note |
| `POST /api/obsidian/file/{path}/append` | `obsidian_append_file()` | Appends to a note |
| `DELETE /api/obsidian/file/{path}` | `obsidian_delete_file()` | Deletes a note |
| `POST /api/obsidian/search` | `obsidian_search()` | Full-text search |

**Helper:** `_obs(method, path, **kwargs)` — shared async httpx client, injects auth header

---

## 3. Protocol layer — `protocol/`

Pure functions that return `bytes`. No BLE I/O. Imported by `api.py` (partially) and available for reuse.

### `protocol/constants.py`
All command bytes, enums, UUIDs:
- `Cmd` — every first-byte command code (e.g. `Cmd.SEND_RESULT = 0x4E`)
- `DisplayStatus` — screen status byte values (SIMPLE_TEXT, FINAL_TEXT, etc.)
- `DeviceOrder` — sub-codes for 0xF5 events from glasses
- `DashboardMode`, `DashboardPosition`, `MicState`, `SilentMode`, `TranslateLang`
- `BMP_WIDTH`, `BMP_HEIGHT`, `BMP_PACKET_SIZE`, `BMP_ADDR`, `BMP_END_CMD`
- `F5_EVENTS` — human-readable label map for 0xF5 sub-codes
- `WEEKDAY_OFFSET` — Python weekday → glasses weekday remapping

### `protocol/commands.py`
Byte builders for every command type:
- `build_init()` → `[0x4D, 0x01]`
- `build_heartbeat()` → `[0x25, 0x02]`
- `build_exit_all()` → `[0x18]`
- `build_text_direct(text)` → `[0x4E, 0x71, len, ...utf8]`
- `build_text_packet(text, seq, total_pages, current_page, max_pages, status, new_content)` → full pagination packet
- `build_display_complete(seq)` → FINAL_TEXT packet to dismiss AI overlay
- `build_brightness(level, auto)` → `[0x01, level, auto]`
- `build_silent_mode(enabled)` → `[0x03, ...]`
- `build_tilt_angle(degrees)` → `[0x0B, degrees, 0x01]`
- `build_mic(on)` → `[0x0E, 0x01|0x00]`
- `build_dashboard_mode(mode)` → `[0x06, ...]`
- `build_dashboard_position(position, visible)` → `[0x26, ...]`
- `build_dashboard_distance(distance)` → `[0x26, 0x80, ...]`
- `build_translation_setup()` / `build_translation_start()` / `build_translation_config(src, tgt)`
- `build_translation_init_channel(cmd_byte, seq)` / `build_translation_send(cmd_byte, seq, text)`
- `build_time_sync(now)` → 13-byte time-sync packet
- `build_battery_request()` → `[0x2C, 0x01]`
- `build_notification_chunks(msg_id, app_id, title, message)` → list of 0x4B NCS packets

### `protocol/bmp.py`
Image pipeline functions (cleaner API than the raw api.py versions):
- `to_bmp_bytes(image_bytes, invert=True)` → 1-bit 576×136 BMP
- `to_bmp_bytes_inverted(image_bytes)` → alias for text/UI polarity
- `build_frames(bmp_data)` → list of 0x15 framed packets
- `build_crc_cmd(bmp_data)` → 6-byte CRC packet
- `to_stereo_pair(image_bytes, max_disparity, blur_radius, invert_depth, z_shift)` → (left BMP, right BMP)
- `compose_bmp(background_bytes, text_blocks, image_layers)` → 1-bit BMP

---

## 4. Frontend — `frontend/src/`

### `App.jsx` — root
- Owns global state: `tab`, `status`, `toasts`, `logs`, `visited`
- Polls `GET /api/status` every 4 s
- Opens `GET /api/events/stream` SSE when connected, feeds lines into `logs`
- Lazy-mounts Image and Send tabs so their state survives tab switches
- Passes `{ status, addToast, addLog }` as shared props to every tab

### `api.js` — HTTP client
- `request(path, options, timeoutMs)` — base fetch wrapper with abort timeout
- **Exports `api` object** — one method per backend route:
  - `status()`, `connect()`, `disconnect()`, `sendText(text)`
  - `sendImage(b64)`, `previewBmp(b64)`, `sendStereoImage(b64, params)`, `previewStereoBmp(b64, params)`
  - `precompute(images)`, `sendPrecomputed(id)`, `deletePrecomputed(id)`
  - `previewCompose(bg, blocks, imageLayers)`, `sendCompose(...)`, `precomputeCompose(...)`
  - `previewStereoCompose(...)`, `sendStereoCompose(...)`
  - `api.obsidian.*` — all 9 Obsidian proxy methods

### `components/Home.jsx`
- `handleConnect()` — streams `/api/connect-stream`, parses `__DONE__` / `__FAIL__` SSE signals
- `handleDisconnect()` — calls `api.disconnect()`
- Renders connection status, glass names, scanning state, Terminal log

### `components/ImageTab.jsx`
- `loadFile(file)` / `loadFiles(files)` — FileReader → base64 dataURL
- `triggerPrecompute(items)` — calls `api.precompute()`, updates queue item status
- `makeQueueItem(original, mode, stereo)` — creates a queue entry with UUID
- `sendItem(dataUrl, mode, stereo)` — calls `api.sendImage` or `api.sendStereoImage`
- `sendQueueItem(item)` — uses cached path (`api.sendPrecomputed`) if available, falls back to direct send
- `handleSend()` — single-image send for the currently loaded image
- `handlePreview()` — calls `api.previewBmp` or `api.previewStereoBmp`
- `addToQueue()` / `removeFromQueue(idx)` — queue CRUD
- `goToQueue(idx)` — navigates to an item and sends it if connected
- `handleDragStart/Enter/Over/End/ThumbDrop` — drag-to-reorder queue
- Auto-play loop (useEffect) — ticks through queue at `autoInterval` ms, calls `sendQueueItem`

### `components/SendTab.jsx`
Root: `SendTab` — renders sub-mode toggle (Text / Compose), lazy-mounts each section.

**`TextSection`**
- `handleSend()` — calls `api.sendText(text.trim())`
- `handlePaste()` — reads clipboard, appends to textarea
- `handleSaveNote()` / note delete — saves/removes from `localStorage` under `NOTES_KEY`

**`ComposeSection`**
- `loadBg(file)` / `setAsDefaultBg()` / `clearDefaultBg()` / `clearBg()` — background management + `localStorage` persistence
- `updateLayer(id, patch)` / `removeLayer(id)` / `moveLayer(idx, dir)` — layer list CRUD
- `loadImageForLayer(id, file)` — FileReader for image layers
- `handlePreview()` → `api.previewCompose()`
- `handleSend()` → `api.sendCompose()`
- `handleStereoPreview()` → `api.previewStereoCompose()` (only shown if any layer has z ≠ 0)
- `handleStereoSend()` → `api.sendStereoCompose()`

**Sub-components (inside SendTab.jsx):**
- `TextLayerControls({ layer, updateLayer })` — textarea + position grid + size/padding/depth/ink sliders
- `ImageLayerControls({ layer, updateLayer, loadImageForLayer })` — drop zone + position grid + depth slider
- `SliderRow(...)` — shared slider UI primitive

**Layer conversion helpers (module-level):**
- `toApiTextBlocks(layers)` — filters text layers with content, strips internal fields
- `toApiImageLayers(layers)` — filters image layers with data, strips data-URL prefix

### `components/ObsidianTab.jsx`
Obsidian vault browser + note editor. Calls `api.obsidian.*` methods.

### `components/Terminal.jsx`
Read-only scrolling log display, fed by `logs` prop from `App.jsx`.

---

## 5. Data shapes passed between frontend and backend

### Text
```
POST /api/send-text   { text: string }
```

### Image
```
POST /api/send-image          { imageData: string }   // base64, no data-URL prefix
POST /api/send-stereo-image   { imageData, maxDisparity, blurRadius, invertDepth }
POST /api/preview-bmp         { imageData }
POST /api/preview-stereo-bmp  { imageData, maxDisparity, blurRadius, invertDepth }
```

### Precompute
```
POST /api/queue/precompute    { images: [{ id, imageData, mode, maxDisparity, blurRadius, invertDepth }] }
→ { precomputed: [id, ...], errors: [{id, error}] }

POST /api/send-precomputed/{id}   (no body)
DELETE /api/queue/precomputed/{id}
```

### Compose
```
POST /api/preview-compose / send-compose / precompute-compose:
  {
    backgroundData: string,       // base64 or ""
    blocks: [{ text, position, size, color, padding, z }],
    imageLayers: [{ imageData, position, z }]
  }

POST /api/preview-stereo-compose / send-stereo-compose:
  { ...same, backgroundZ: int, maxDisparity: int }
```

### Events (SSE)
```
GET /api/events/stream
→ data: INFO:touchpad:right — Change Page  raw=f50100...
→ data: INFO:wear:left — Worn  raw=...
→ data: DEBUG:ble:right cmd=0x25  raw=...
```

### Connect stream (SSE)
```
POST /api/connect-stream
→ data: INFO:bleak:...         (SDK log lines)
→ data: __DONE__{"connected":true,"left":true,...}
→ data: __FAIL__No glasses found during scan
```

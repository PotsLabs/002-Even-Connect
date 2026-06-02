# EvenConnect — Next Actions

> Last updated: 2026-05-30

---

## QoL — Frontend ✅ Complete

| # | Task | Status |
|---|---|---|
| 1 | Compose tab: default text size and padding → 14px | ✅ Done |
| 2 | Compose tab: persistent default background image (localStorage) | ✅ Done |
| 3 | Image tab: restore queue state on tab switch (lazy-mount) | ✅ Done |
| 4 | Merge Text tab and Compose tab into one unified Send tab | ✅ Done |

---

## QoL — Stereo / Imaging ✅ Complete

| # | Task | Status |
|---|---|---|
| 5 | Stereo image: default max disparity → 10 | ✅ Done |
| 6 | Stereo compose: per-layer z-depth control (−5 → +5) | ✅ Done |
| 6a | Background image z-depth with positive and negative shift | ✅ Done |
| 6b | Image layers with independent z-depth in compose | ✅ Done |

**Implementation notes**
- All layers (background, image, text) use a unified `z / 5 × maxDisparity` shift formula
- Left eye: `−shift`, right eye: `+shift` (parallel-view convention)
- `_shift_canvas` handles background parallax; `_render_image_layer` handles image layers with OR-blend compositing
- Stereo preview/send buttons appear automatically when any layer has `z ≠ 0`

---

## Platform Ports

| # | Task | Status |
|---|---|---|
| 7 | Android application port | ✅ Done |
| 8 | macOS menubar (status bar) app port | Pending |

### Task 7 — Android ✅ Done

**Installed on:** Realme RMX3938 · Android 15 · SDK 35

**Location:** `android/` in project root

**Features shipped:**
- BLE scan → connect to both G1 glasses (left + right)
- Time sync on connect, 15 s heartbeat
- **Text tab**: direct display mode (`0x4E 0x71`) — no Even AI activation; right tap = next page, left tap = previous; `0xF5 0x12` mapped as Single Tap
- **Image tab**: gallery picker → scale to 576×136 → 1-bit BMP → send via `0x15` frame protocol + CRC
- **Compose tab**: live preview (Android Canvas) · optional background image · multiple text layers with H/V alignment, size, light/dark ink → send as composed BMP
- **Log tab**: live scrolling BLE event feed, colour-coded

**Known limitations / follow-up:**
- iOS notification reading blocked by Apple (cannot read other apps' notifications — OS-level policy, no workaround)
- iOS background BLE restricted after ~10 min; requires `UIBackgroundModes: bluetooth-central` + state restoration
- Obsidian integration not yet ported to Android
- No stereo/z-depth compose on Android yet (BMP only, no left/right pair)

### Task 8 — macOS Menubar (Pending)

**Recommended approach:** Native SwiftUI — `NSStatusItem` + `NSPopover`, `LSUIElement = YES` (no Dock icon), Login Item registration. Embed the Python backend as a bundled subprocess. Use `CoreBluetooth` directly (not the Python BLE stack).

**Do NOT use React Native for this target** — no clean `NSStatusItem` story in `react-native-macos`; native SwiftUI is 10× less friction.

---

## Architecture — React Native Consideration

**Question evaluated 2026-05-30:** Would porting the frontend to React Native give a single codebase for macOS, iOS, and Android?

**Answer: Yes for iOS + Android (~80% shared), No for macOS menubar.**

| Target | Recommended approach |
|---|---|
| Android | React Native — BLE (`react-native-ble-plx`), GPS, notifications all work standalone |
| iOS | React Native — BLE and GPS work; notification reading from other apps **impossible** (Apple policy) |
| macOS menubar | Native SwiftUI — `NSStatusItem` is not supported cleanly in `react-native-macos` |
| Web / power-user | Keep Python + React (current setup) |

**What transfers:** Business logic, BLE protocol bytes, HTTP calls, text formatting → all move to TypeScript unchanged.

**What does not transfer:** The existing JSX (React web) ≠ React Native. `<div>` → `<View>`, CSS → StyleSheet — it is a rendering-layer rewrite, not a copy-paste. Plan for ~1–2 weeks of UI migration.

---

## BLE Protocol — Key Findings

| Finding | Detail |
|---|---|
| Text display (no AI) | `[0x4E, 0x71, len, ...text]` — display-only subcode, no Even AI activation |
| Tap-to-advance | `0xF5 0x01` (AI pagination mode) and `0xF5 0x12` (single tap during display) both drive page advance |
| Right tap = forward | `glass.side == "right"` + `0xF5 0x01/0x12` |
| Left tap = backward | `glass.side == "left"` + `0xF5 0x01/0x12` |
| `0x50/0x51` status | Triggers microphone / Even AI listening — do not use for text display |
| `0x31` status | Triggers Even AI display mode — causes "Even AI Listening" flash on device |
| BMP tap events | `0xF5` events confirmed to fire during BMP image display |
| Image protocol | `0x15` frames (194-byte chunks) + `[0x20, 0x0D, 0x0E]` end + CRC32 command |

---

## KiroshiOS — Milestone Tracker

| Milestone | Description | Status |
|---|---|---|
| M0 | Send text to G1 over BLE | ✅ Done |
| M0a | Send images (BMP) to G1 over BLE | ✅ Done |
| M0b | Tap-to-advance pagination | ✅ Done |
| M0c | Compose (text + image layers) with stereo z-depth | ✅ Done |
| M0d | Android standalone app (no laptop required) | ✅ Done |
| M1 | Read Obsidian daily note → display as paginated text on glasses | Not started |
| M2 | Morning synthesis: calendar + daily note + sleep data → AI briefing | Not started |
| M3 | On-the-go voice capture → transcribe → save to vault | Not started |
| M4 | Rollover detection + task tracking with time | Not started |
| M5 | Ghost navigation from calendar events | Not started |
| M6 | Pre-meeting context flash cards | Not started |
| M7 | Financial capture + digest | Not started |
| M8 | macOS menubar app (KiroshiOS always-on runtime) | Not started |
| M9 | ATAK-Civ connector prototype | Not started |

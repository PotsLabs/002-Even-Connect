# EvenConnect — Next Actions

> Last updated: 2026-05-30

---

## QoL — Frontend

| # | Task | Status |
|---|---|---|
| 1 | Compose tab: default text size and padding → 14px | Pending |
| 2 | Compose tab: persistent default background image (localStorage) | Pending |
| 3 | Image tab: restore last-sent images on tab switch / app restart | Pending |
| 4 | Merge Text tab and Compose tab into one unified tab | Pending |

**Notes**
- Tasks 1 and 2 touch the compose tab directly — complete before task 4 (tab merge).
- Task 3 is isolated; can be done in any order.

---

## QoL — Stereo / Imaging

| # | Task | Status |
|---|---|---|
| 5 | Stereo image: default max disparity → 10 | Pending |
| 6 | Stereo compose: per-layer z-depth control (explicit depth instead of luminance proxy) | Pending |

**Notes**
- Task 5 is a one-liner in both the frontend state initialiser and the backend `StereoImagePayload` default.
- Task 6 requires a new backend render path: each compose layer gets a `z` value (0 = far / background, higher = closer). Left eye shifts layer pixels left by `z × disparity`; right eye shifts right. Background is always z = 0.

---

## Platform Ports

| # | Task | Status |
|---|---|---|
| 7 | Android application port | Pending |
| 8 | macOS menubar (status bar) app port | Pending |

**Notes**

### Task 7 — Android
- G1 BLE protocol is fully documented in the codebase; Android side is Kotlin BLE + UI.
- Two approaches: (a) Android app talks to the Python backend over local network — fast to build, requires desktop running; (b) replicate BLE logic natively in Kotlin — fully offline mobile runtime.
- Recommended start: approach (a) to validate UX, then migrate BLE to native for KiroshiOS mobile.

### Task 8 — macOS Menubar
- Swift/SwiftUI shell already exists in `g1-sample/`.
- Key changes: wrap main view in `NSStatusItem` + `NSPopover`, set `LSUIElement = YES` in `Info.plist` (removes Dock icon), add Login Item registration.
- UI needs a condensed popover layout: connection status pill, quick-send field, current page indicator.

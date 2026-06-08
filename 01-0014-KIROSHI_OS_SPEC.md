# KiroshiOS — Product Specification

> **Status:** M0 (core protocol + API refactored) → Ready for M1 (Obsidian integration).
> **Last updated:** 2026-06-09
> **Repository:** 005-EvenConnect (rewrite branch)

---

## Current Interface

### Runtime Composition (Background with Text Input)
<img width="1512" height="982" alt="Compose Screen" src="https://github.com/user-attachments/assets/6dfcfad2-a842-46ff-a464-55b5822eb8ab" />

### Image Queueing (Manual Cycle of Image List)
<img width="1512" height="982" alt="Screenshot 2026-05-26 at 20 51 03" src="https://github.com/user-attachments/assets/0322c869-a682-4ade-867e-f55027198d75" />

### Glasses Connection Terminal (BLE Status & Errors)
<img width="1512" height="982" alt="Screenshot 2026-05-26 at 20 52 36" src="https://github.com/user-attachments/assets/d1825376-ca12-4632-9aca-fb5a5ebf8a2b" />

---

## One-Line Summary

Pull what's in my Obsidian vault into my eyes during the day — with an AI layer that decides what to show and when.

---

## What This Is

KiroshiOS is a personal operating system for HUD smart glasses. It connects to your existing tools (Obsidian, calendar, health tracking, finances) and surfaces contextually relevant information on a heads-up display throughout the day. An AI middleware layer reads, synthesises, and reasons over your personal data to produce briefings, reminders, and nudges — all running locally and privately.

The name comes from Kiroshi Optics in Cyberpunk 2077 — cybernetic eye implants with AR overlays, modular software, and real-time data processing. This is the real-world version built on existing hardware.

## Core Value Proposition

The glasses answer one question at any moment: **"What matters to me right now?"** — drawn from everything you've already written, tracked, and scheduled. You don't open apps, you don't check your phone. You glance and you know.

---

## Current Hardware

**Even Realities G1**
- Display: 640×200px monochrome green, 20Hz, 25° FOV
- Usable render area: 576×136px, 1-bit BMP or paginated text (488px wide, ~5 lines)
- Input: two touchbars (left/right temple) — single tap, double tap, long press
- Connection: dual BLE (left arm + right arm), UART protocol
- No camera, no speakers — display + mic + touch only
- Python SDK available (`even_glasses` / bleak)

**Planned upgrade:** Even Realities G2 or equivalent 6DOF glasses when available. The software architecture is designed so the display layer swaps out while everything else stays.

---

## Architecture — Six Layers

### 1. BLE Transport
Talks to the glasses. Handles dual-BLE connection, send-left-wait-ACK-send-right protocol, decodes touchbar input. Thin wrapper around bleak + G1 wire protocol (0x4E text, 0x15 BMP). Everything above this layer doesn't know about BLE.

### 2. Display Engine
Two rendering paths:
- **Text mode** — paginated strings, 5 lines/screen, low BLE overhead. Preferred.
- **BMP mode** — 576×136 1-bit Pillow canvas for graphical layouts, icons, diagrams.
Includes text layout (word wrap, truncation, column alignment), pagination state, and a page indicator.

### 3. Event Bus
Async pub/sub. All components communicate here: touchbar events, context changes, data updates, module switches, render triggers. Decouples everything.

### 4. Context Engine
Combines location (GPS → semantic: home/work/transit), time (morning/work/evening/night), calendar (next event, in meeting?), and activity (stationary/walking/driving) into a Context object. Determines which module auto-activates.

### 5. Data Sources
Adapters that fetch external data on tiered schedules:
- **Fast (5s):** clock, active navigation, heart rate
- **Medium (30s):** weather, notification counts, battery
- **Slow (5min):** calendar sync, task counts, news
- **Glacial (30min):** financial data, analytics

Sources write to a shared state store. Modules read from it. Adding a source never requires changing a module.

### 6. Modules
Self-contained display modes. Each implements:
```
should_activate(context) → bool
on_input(event) → bool
tick(state) → None
render(state) → pages | bmp
```
Auto-activation priority: Alert → Navigation → Meeting → Analytics → Dashboard (default).
User overrides via touchbar: double-tap = home, long-press = voice command.

---

## Features — Ordered by Build Priority

### Phase 1: Morning Brief + Daily Loop (build first)

**Morning synthesis**
AI reads today's calendar, yesterday's daily note (what was finished, what wasn't), sleep/recovery from Garmin, and active project notes. Produces a single briefing screen: what happened, what's carrying over, what's ahead, how your body is doing.

**Rollover detection**
AI compares today's daily note template with yesterday's unchecked items. If a task has been carried forward multiple days, it surfaces that explicitly with a prompt to block time or drop it.

**Daily task view**
Today's tasks as an ordered list pulled from Obsidian daily note. Paginated via touchbar. Track time against active task.

**`even_print` — glasses stdout**
Drop-in utility for sending any Python value or terminal output directly to the glasses as paginated text. `even_print(value)` encodes the string representation, paginates it, and pushes it over BLE exactly like a manual text send — no HTTP, no frontend, no SSE. Intended for status checks, script output tails, and low-frequency log lines where you want eyes-up feedback without opening a terminal. Not for high-throughput streaming (use SSE + frontend for that).

**On-the-go capture**
Long press → voice note → AI transcribes → saves to correct location in Obsidian vault using the right template. Tags for today/this week/this month as appropriate. Items tagged "research" or "look into later" get filed for resurfacing.

**AI reminder layer**
Captured ideas and deferred tasks resurfaced at contextually appropriate times. Driven by tags, due dates, and AI judgment on relevance.

### Phase 2: Context-Aware Intelligence

**Ghost navigation**
Calendar event has a location + it's time to leave → navigation appears automatically. Heading, ETA, next turn. Disappears on arrival.

**Pre-meeting flash cards**
5 minutes before a calendar event: who you're meeting, last notes with them (from Obsidian), pending action items you owe them, relevant project context.

**Energy-aware scheduling**
Garmin recovery + calendar gaps → AI suggests what to do when. Low recovery = move gym, use gap for light work. High recovery = tackle the hard thinking.

**End of day capture**
Timed prompt (e.g. 18:00): tasks completed, items carried, voice prompt to append to daily note. Journal writes itself.

### Phase 3: Financial Awareness

**Manual spend capture**
Voice log ("spent R150 on groceries") or receipt photo-read → transcribed → saved to hledger. All local, no bank API needed initially.

**Spending digest**
End of day/week: total spent, budget vs actual, tied back to financial goals documented in the vault. "Your 'reduce eating out' goal — you're R400 over this week."

**Data privacy note:** No bank API integration planned for v1. All financial data is manually captured or read from local hledger journals. Inference runs locally.

### Phase 4: External Connectors

**Obsidian connector** — the first and primary connector. Reads/writes markdown files in the vault. Every other feature depends on this.

**Calendar connector** — Google Calendar API. Read events, locations, attendees.

**Health connector** — Garmin Connect export or Gadgetbridge for local-first watch data. Sleep, recovery, steps, heart rate.

**Comms connector** — notification counts from email, Slack, messaging. Read-only summaries, not full message content.

**Application connectors (future)** — VS Code, browser, terminal. Expose current application context to the glasses API for professional use cases.

### Phase 5: Tactical / Field Use (future)

**ATAK-Civ integration** — connector for the open-source situational awareness platform. Display coordinates, heading, team positions, mesh network comms (Meshtastic/Reticulum).

**PTT transcription** — push-to-talk audio from ATAK transcribed via speech-to-text, displayed on all connected glasses in real time. High-noise-environment communication.

**This is a validated market need** — unprompted feature request from a security industry professional for the G2 platform.

---

## Infrastructure — Privacy-First, Local-First

### v1: Files + Script
- Obsidian vault = the database (markdown files, already structured)
- Garmin exports CSV, hledger is plain text, calendar has a standard API
- A Python service reads local files, calls APIs, assembles payloads, pushes to glasses over BLE
- No server, no cloud, no database. Data stays where it already lives.

### v2: Multi-Device Sync
- **Syncthing** between devices (laptop, phone, home machine) keeping a shared data folder
- Each data source writes state to structured JSON/markdown
- Glasses client reads from whichever device is nearby
- Encrypted, peer-to-peer, no cloud vendor

### v3: Local AI
- **Ollama** with a small model (Llama 3.1 8B / Mistral 7B) for vault queries and synthesis
- All inference on local hardware, nothing leaves the network
- Powers the "what was that" recall, morning synthesis, and rollover detection

### v4: Local API Server
- **FastAPI on localhost** — single endpoint that any connector can POST context to
- Glasses BLE connection managed by this server, not by individual connectors
- This is when it becomes an OS rather than a script

---

## Design Principles

1. **The glasses are a dumb terminal.** All intelligence lives on the host.
2. **Context is king.** What's shown depends on where, when, and what you're doing. The OS decides; you just glance.
3. **Glanceability over density.** Every screen answers one question in under 2 seconds.
4. **Local-first, private by default.** No cloud accounts, no data leaving your network, no vendor lock-in. Obsidian vault is the source of truth.
5. **Read-write loop.** The glasses aren't just a display — they capture back into the vault. The system feeds itself.
6. **Modules are self-contained.** Adding a new feature = writing a new module class. Nothing else changes.
7. **Build where the river is.** Start with what's useful to you today. Don't build infrastructure ahead of need.

---

## Key Lessons Applied (from Launch Lab talk, 28 May 2026)

- "Don't build dams where there aren't rivers" → Build the Obsidian connector first because you use it daily. Pursue ATAK because someone is already asking for it.
- "Track engagement" → If you don't wear the glasses every day because they're useful, the product doesn't work. Morning brief is the engagement hook.
- "Go where Silicon Valley isn't looking" → Tactical field HUD for security teams on mesh networks. Knowledge worker vault-to-glasses bridge. Neither is a SF startup pitch.
- "Capital light + existing distribution" → Software layer on Even Realities hardware. No manufacturing.
- "You are not the failure — the thing you built didn't work" → Build small, prove value, iterate. Don't over-invest in infrastructure before the core loop works.
- "Try a thing. Speak to the market." → Demo the morning brief. Talk to the ATAK person.

---

## Open Questions

- [ ] G1 mic quality: is on-device voice capture good enough for transcription, or does it need phone mic passthrough?
- [ ] BLE bandwidth limits: how frequently can BMP frames be pushed before battery drain becomes a problem?
- [ ] Ollama model selection: what's the smallest model that can do useful synthesis over a markdown vault?
- [ ] Multi-user: does this ever need to support more than one person, or is it a personal tool only?
- [ ] Monetisation: personal tool → open source? Tactical connector → paid product? Module marketplace?

---

---

## Build Roadmap & Progress

### M0 — Core Protocol & API ✅ COMPLETE (2026-06-09)

**Architecture Refactored:** Separated BLE/protocol logic from HTTP API layer.

**Core Capabilities Wired:**
| Component | Status | Details |
|-----------|--------|---------|
| Connection | ✅ | Scan, dual-glass connect, time sync, event handlers |
| Text Send | ✅ | Paginate + tap-to-advance (5-line pages) |
| Image/Stereo | ✅ | 1-bit BMP, z-depth composition, ACK handshake |
| Obsidian Integration | ✅ | Module built (`integrations/obsidian.py`) |

**Tech Stack Cleanup:**
- ✅ Extracted `protocol/` package (pure bytes, no HTTP)
  - `connect.py`: BLE lifecycle + send pipelines
  - `bmp.py`: Image encoding + stereo composition
  - `commands.py`: Packet builders
  - `constants.py`: All enums, UUIDs
- ✅ Thin API layer: `api_v3.py` (231 lines, 72% reduction from v2)
- ✅ Frontend: React tabs (Text, Image, Obsidian, Logs)
- ✅ Android app: Fully standalone (no laptop required)
- ✅ Deferred: Preview endpoints (can add back later)

**Known Issues (low severity):**
- `leftName`/`rightName` camelCase mismatch (cosmetic)
- Preview endpoints not yet wired (nice-to-have)

---

### M1 — Obsidian Bridge (Next)

**Goal:** Read today's daily note from vault → paginate to glasses → tap to advance.

**What's needed:**
1. ObsidianVault API client (✅ done in `integrations/obsidian.py`)
2. Endpoint to call `sync_note()` from frontend
3. Test with actual vault

**Timeline:** ~1 week (API integration only)

---

### M2 — Morning Synthesis

**Goal:** Calendar + yesterday's note + sleep data → AI brief on glasses.

**Requirements:**
- Calendar connector (Google Calendar API)
- Garmin/health data fetch
- Local Ollama for synthesis
- 3–4 screen morning brief

**Timeline:** ~3 weeks (includes Ollama setup)

---

### M3 — On-the-Go Voice Capture

**Goal:** Long press → voice note → transcribe → save to vault with template.

**Requirements:**
- G1 microphone quality test
- Speech-to-text (local Whisper)
- Vault file write with date-based organization

**Timeline:** ~2 weeks

---

### M4 — Rollover Detection + Task Tracking

**Goal:** Daily note comparison → flag carried-over tasks → time tracking.

**Requirements:**
- Yesterday's note vs today's template parse
- Task list extraction
- Time tracking state machine

**Timeline:** ~2 weeks

---

### M5–M7 — Context-Aware Modules

| Milestone | Feature | Status |
|---|---|---|
| M5 | Ghost navigation (calendar location → ETA) | Planned |
| M6 | Pre-meeting flash cards (who, last notes, actions) | Planned |
| M7 | Financial capture + digest (spend logging + budget) | Planned |

---

### M8 — Local API Server (Multi-Connector)

**Goal:** Generalized connector architecture (no longer a Python script).

**Architecture:**
```
Obsidian ┐
Calendar ├─→ Connector Registry ─→ FastAPI ─→ Glasses
Health   ┤       (module mgmt)
Custom   ┘
```

**Timeline:** ~4 weeks (includes module system redesign)

---

### M9 — ATAK-Civ Tactical HUD (Future)

**Goal:** Display coordinates, team positions, mesh comms on glasses in field.

**Status:** Validated market need (unprompted request from security professional).

**Timeline:** Post-M4 (depends on field deployment opportunity).

---

## Frontend QoL (Complete — as of 2026-05-30)

| Task | Status |
|------|--------|
| Compose tab: default text size/padding → 14px | ✅ |
| Compose: persistent background (localStorage) | ✅ |
| Image tab: queue state restored on tab switch | ✅ |
| Text + Compose unified into Send tab | ✅ |
| Stereo: default max disparity → 10 | ✅ |
| Per-layer z-depth control (−5 → +5) | ✅ |

---

## Platform Ports

### Android ✅ SHIPPED

**Device:** Realme RMX3938 · Android 15 · SDK 35

**Features:**
- BLE scan, dual-glass connect, time sync
- Text display (direct mode, no AI overlay)
- Right tap = next, left tap = previous
- Image gallery → 1-bit BMP → send
- Live BLE event log (color-coded)

**Known Limitations:**
- No stereo/z-depth compose yet (BMP only)
- Obsidian integration not ported
- iOS background BLE restricted (~10 min timeout without state restoration)

### macOS Menubar (Pending)

**Recommended:** Native SwiftUI (`NSStatusItem` + `NSPopover`). Embed Python backend as subprocess. Use `CoreBluetooth` (not Python BLE stack).

**Why not React Native:** No clean `NSStatusItem` support in `react-native-macos`.

---

## Deferred / Nice-to-Have

### Preview Endpoints
- `/api/preview-bmp` — show 1-bit BMP preview
- `/api/preview-stereo-compose` — show left/right pair before send
- **Why deferred:** Not core; can be added once pipeline is stable
- **How:** Simple endpoints returning PNG data URIs

---

## Design Principles

1. **The glasses are a dumb terminal.** All intelligence lives on the host.
2. **Context is king.** What's shown depends on where, when, and what you're doing. The OS decides; you just glance.
3. **Glanceability over density.** Every screen answers one question in under 2 seconds.
4. **Local-first, private by default.** No cloud accounts, no data leaving your network, no vendor lock-in. Obsidian vault is the source of truth.
5. **Read-write loop.** The glasses aren't just a display — they capture back into the vault. The system feeds itself.
6. **Modules are self-contained.** Adding a new feature = writing a new module class. Nothing else changes.
7. **Build where the river is.** Start with what's useful to you today. Don't build infrastructure ahead of need.

---

## Key Lessons Applied (from Launch Lab talk, 28 May 2026)

- "Don't build dams where there aren't rivers" → Build the Obsidian connector first because you use it daily. Pursue ATAK because someone is already asking for it.
- "Track engagement" → If you don't wear the glasses every day because they're useful, the product doesn't work. Morning brief is the engagement hook.
- "Go where Silicon Valley isn't looking" → Tactical field HUD for security teams on mesh networks. Knowledge worker vault-to-glasses bridge. Neither is a SF startup pitch.
- "Capital light + existing distribution" → Software layer on Even Realities hardware. No manufacturing.
- "You are not the failure — the thing you built didn't work" → Build small, prove value, iterate. Don't over-invest in infrastructure before the core loop works.
- "Try a thing. Speak to the market." → Demo the morning brief. Talk to the ATAK person.

---

## Open Questions

- [ ] G1 mic quality: is on-device voice capture good enough for transcription, or does it need phone mic passthrough?
- [ ] BLE bandwidth limits: how frequently can BMP frames be pushed before battery drain becomes a problem?
- [ ] Ollama model selection: what's the smallest model that can do useful synthesis over a markdown vault?
- [ ] Multi-user: does this ever need to support more than one person, or is it a personal tool only?
- [ ] Monetisation: personal tool → open source? Tactical connector → paid product? Module marketplace?

---

*This document is the source of truth for KiroshiOS development. Update it as decisions are made, features ship, and the product evolves.*

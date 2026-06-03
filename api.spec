# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the KiroshiOS backend sidecar.
# Run via build.sh — do not call pyinstaller directly.

import os

ROOT = os.path.abspath('.')

# ── Data files bundled into the executable ────────────────────────────────────
datas = [
    # Local protocol package
    ('protocol', 'protocol'),
]

# Include Even Realities custom fonts when present (fall back to system fonts otherwise)
for _font in [
    'EvenSignature_Final 1.0_English Only.otf',
    'EvenRosterGrotesk_Final 1.0_English Only.otf',
    'EvenTimeBigPixel_v1.0.ttf',
]:
    _p = os.path.join(ROOT, 'image_tests', _font)
    if os.path.exists(_p):
        datas.append((_p, 'image_tests'))

# ── Hidden imports PyInstaller can't auto-detect ──────────────────────────────
hidden = [
    # BLE (bleak + CoreBluetooth bridge on macOS)
    'bleak',
    'bleak.backends.corebluetooth',
    'bleak.backends.corebluetooth.client',
    'bleak.backends.corebluetooth.scanner',
    'bleak.backends.corebluetooth.utils',
    # uvicorn internals selected dynamically at runtime
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    # starlette middleware used by FastAPI CORS + static files
    'starlette',
    'starlette.middleware',
    'starlette.middleware.cors',
    'starlette.staticfiles',
    'starlette.responses',
    'starlette.routing',
    # HTTP client
    'httpx',
    'httpx._transports.default',
    'httpx._transports.asgi',
    # even_glasses SDK
    'even_glasses',
    'even_glasses.bluetooth_manager',
    'even_glasses.commands',
    'even_glasses.models',
    'even_glasses.utils',
]

a = Analysis(
    ['api.py'],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter', 'matplotlib', 'scipy'],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

# One-file executable: include binaries + datas directly in EXE (no COLLECT step)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

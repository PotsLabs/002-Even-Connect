"""
G1 BLE connection management — handles all Bluetooth Low Energy communication.

Classes:
  - BleDevice: base class for BLE connections
  - Glass: single lens with heartbeat management
  - GlassesManager: manages left + right glasses pair

Usage:
  from protocol.connect import GlassesManager

  manager = GlassesManager()
  connected = await manager.scan_and_connect(timeout=12)
  await manager.sync_time()
  manager.set_event_handler(handler_func)
"""

import asyncio
import logging
import struct
from datetime import datetime
from typing import Callable, Awaitable, Optional

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from .constants import (
    UART_SERVICE_UUID, UART_TX_UUID, UART_RX_UUID,
    Cmd, Response, ConnectionState, WEEKDAY_OFFSET, SILENT_CMDS, F5_EVENTS,
    DisplayStatus, ScreenAction, BMP_WIDTH, BMP_HEIGHT,
)
from .commands import build_text_packet
from .bmp import (
    to_bmp_bytes,
    compute_depth,
    compose_layers,
    build_frames,
    build_crc_cmd,
    BMP_END_CMD,
    DISPLAY_COMPLETE,
)

logger = logging.getLogger(__name__)


# ── Packet builders ────────────────────────────────────────────────────────────

def build_heartbeat(seq: int) -> bytes:
    """[0x25, length, seq, 0x04, seq] — keep-alive packet."""
    length = 6
    return struct.pack(
        "BBBBBB",
        Cmd.HEARTBEAT,
        length & 0xFF,
        (length >> 8) & 0xFF,
        seq % 0xFF,
        0x04,
        seq % 0xFF,
    )


def build_time_sync() -> bytes:
    """[0x4D, 0x0B, 0x00, year_lo, year_hi, month, day, hour, min, sec, weekday, 0, 0]."""
    now = datetime.now()
    year = now.year
    return bytes([
        Cmd.INIT,
        0x0B, 0x00,
        year & 0xFF,
        (year >> 8) & 0xFF,
        now.month,
        now.day,
        now.hour,
        now.minute,
        now.second,
        WEEKDAY_OFFSET[now.weekday()],
        0x00, 0x00,
    ])


# ── BLE Connection Classes ─────────────────────────────────────────────────────

class BleDevice:
    """Base class for BLE connection to a single device."""

    def __init__(self, name: str, address: str):
        self.name = name
        self.address = address
        self.client = BleakClient(address, disconnected_callback=self._handle_disconnection)
        self.uart_tx = None
        self.uart_rx = None
        self._write_lock = asyncio.Lock()
        self.notifications_started = False
        self.desired_state = ConnectionState.DISCONNECTED
        self.notification_handler: Optional[Callable[..., Awaitable[None]]] = None

    async def connect(self) -> None:
        """Connect and discover UART characteristics."""
        try:
            await self.client.connect()
            uart_service = next(
                (s for s in self.client.services if s.uuid.lower() == UART_SERVICE_UUID.lower()),
                None,
            )
            if not uart_service:
                raise BleakError(f"UART service not found on {self.name}")

            self.uart_tx = next(
                (c for c in uart_service.characteristics if c.uuid.lower() == UART_TX_UUID.lower()),
                None,
            )
            self.uart_rx = next(
                (c for c in uart_service.characteristics if c.uuid.lower() == UART_RX_UUID.lower()),
                None,
            )

            if not self.uart_tx or not self.uart_rx:
                raise BleakError(f"UART TX/RX not found on {self.name}")

            await self.start_notifications()
        except Exception as e:
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """Stop notifications and close connection."""
        if self.notifications_started and self.uart_rx:
            try:
                await self.client.stop_notify(self.uart_rx)
            finally:
                self.notifications_started = False

        if self.client.is_connected:
            await self.client.disconnect()
            logger.info(f"Disconnected from {self.name}")

    async def start_notifications(self) -> None:
        """Enable notifications on RX characteristic."""
        if not self.notifications_started and self.uart_rx:
            await self.client.start_notify(self.uart_rx, self._handle_notification)
            self.notifications_started = True

    async def reconnect(self, retries: int = 3) -> None:
        """Attempt reconnection with backoff."""
        for attempt in range(1, retries + 1):
            try:
                await self.connect()
                return
            except Exception as e:
                logger.warning(f"Reconnect attempt {attempt}/{retries} failed for {self.name}: {e}")
                await asyncio.sleep(5)

    async def send(self, data: bytes) -> bool:
        """Write data to TX characteristic."""
        if not self.client.is_connected or not self.uart_tx:
            return False
        try:
            async with self._write_lock:
                await self.client.write_gatt_char(self.uart_tx, data, response=True)
            return True
        except Exception as e:
            logger.error(f"Send error on {self.name}: {e}")
            return False

    def _handle_disconnection(self, client: BleakClient) -> None:
        """Reconnect if we want to be connected."""
        if self.desired_state == ConnectionState.CONNECTED:
            asyncio.create_task(self.reconnect())

    async def _handle_notification(self, sender: int, data: bytes) -> None:
        """Route notifications to user handler."""
        if self.notification_handler:
            await self.notification_handler(self, sender, data)


class Glass(BleDevice):
    """A single glass (one lens) with heartbeat management."""

    def __init__(self, name: str, address: str, side: str, heartbeat_interval: float = 5):
        super().__init__(name, address)
        self.side = side  # "left" or "right"
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Connect and start heartbeat."""
        await super().connect()
        await self.start_heartbeat()

    async def disconnect(self) -> None:
        """Stop heartbeat and disconnect."""
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        await super().disconnect()

    async def start_heartbeat(self) -> None:
        """Start periodic heartbeat if not already running."""
        if self.heartbeat_task is None or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        """Send heartbeat every N seconds."""
        seq = 1
        while self.client.is_connected:
            try:
                heartbeat = build_heartbeat(seq)
                await self.send(heartbeat)
                seq += 1
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Heartbeat error on {self.name}: {e}")
                break


class GlassesManager:
    """Manages left and right glasses pair."""

    def __init__(self, left_address: Optional[str] = None, right_address: Optional[str] = None,
                 left_name: str = "G1 Left Glass", right_name: str = "G1 Right Glass"):
        self.desired_state = ConnectionState.DISCONNECTED
        self.left_glass: Optional[Glass] = (
            Glass(name=left_name, address=left_address, side="left")
            if left_address else None
        )
        self.right_glass: Optional[Glass] = (
            Glass(name=right_name, address=right_address, side="right")
            if right_address else None
        )

    async def scan_and_connect(self, timeout: int = 10) -> bool:
        """Scan for G1 devices (containing "_L_" or "_R_" in name) and connect."""
        try:
            logger.info("Scanning for glasses...")
            devices = await BleakScanner.discover(timeout=timeout)
            for device in devices:
                device_name = device.name or "Unknown"
                logger.info(f"Found: {device_name} ({device.address})")
                if "_L_" in device_name and not self.left_glass:
                    self.left_glass = Glass(name=device_name, address=device.address, side="left")
                elif "_R_" in device_name and not self.right_glass:
                    self.right_glass = Glass(name=device_name, address=device.address, side="right")

            connect_tasks = []
            if self.left_glass:
                connect_tasks.append(asyncio.create_task(self.left_glass.connect()))
            if self.right_glass:
                connect_tasks.append(asyncio.create_task(self.right_glass.connect()))

            if not connect_tasks:
                logger.error("No glasses found during scan")
                return False

            self.desired_state = ConnectionState.CONNECTED
            await asyncio.gather(*connect_tasks)
            logger.info("All glasses connected")
            return True

        except Exception as e:
            logger.error(f"Scan error: {e}")
            return False

    async def disconnect_all(self) -> None:
        """Disconnect from all glasses."""
        disconnect_tasks = []
        if self.left_glass and self.left_glass.client.is_connected:
            disconnect_tasks.append(asyncio.create_task(self.left_glass.disconnect()))
        if self.right_glass and self.right_glass.client.is_connected:
            disconnect_tasks.append(asyncio.create_task(self.right_glass.disconnect()))

        if disconnect_tasks:
            self.desired_state = ConnectionState.DISCONNECTED
            try:
                await asyncio.gather(*disconnect_tasks)
                logger.info("All glasses disconnected")
            except Exception as e:
                logger.error(f"Disconnect error: {e}")

    async def sync_time(self) -> None:
        """Send current system time to both glasses."""
        cmd = build_time_sync()
        for glass in (self.left_glass, self.right_glass):
            if glass and glass.client.is_connected:
                await glass.send(cmd)

    def set_event_handler(self, handler: Callable[..., Awaitable[None]]) -> None:
        """Set the notification handler for both glasses."""
        if self.left_glass:
            self.left_glass.notification_handler = handler
        if self.right_glass:
            self.right_glass.notification_handler = handler

    def connection_status(self) -> dict:
        """Return connection state for both glasses."""
        left_ok = bool(self.left_glass and self.left_glass.client.is_connected)
        right_ok = bool(self.right_glass and self.right_glass.client.is_connected)
        return {
            "connected": left_ok or right_ok,
            "left": left_ok,
            "right": right_ok,
            "left_name": self.left_glass.name if self.left_glass else None,
            "right_name": self.right_glass.name if self.right_glass else None,
        }


# ── Text Pipeline ─────────────────────────────────────────────────────────────

class TextSession:
    """Manages manual-paged text state and debouncing."""
    def __init__(self):
        self.pages = []
        self.current = 0
        self.total = 0
        self.last_advance = 0.0


_text_session = TextSession()


async def send_text(manager: "GlassesManager", text: str) -> None:
    """
    Send text in manual-page mode with tap-to-advance.
    Splits into 5-line pages and sends first page.
    """
    global _text_session
    lines = text.split("\n")
    pages = [lines[i : i + 5] for i in range(0, len(lines), 5)]
    total = len(pages)

    _text_session.pages = ["\n".join(p) for p in pages]
    _text_session.current = 0
    _text_session.total = total

    await send_page(manager, _text_session.pages[0], page_number=1, max_pages=total)


async def send_page(manager: "GlassesManager", text: str, page_number: int, max_pages: int) -> None:
    """
    Send one text page with dual-packet approach:
    1. Direct display packet (immediate render, no AI chrome)
    2. Pagination packet (firmware routes tap events)
    """
    text_bytes = text.encode("utf-8")

    # Packet 1: Direct render [0x4E, SIMPLE_TEXT|NEW_CONTENT, len, ...text]
    display_pkt = bytes([Cmd.SEND_RESULT, DisplayStatus.SIMPLE_TEXT | ScreenAction.NEW_CONTENT, len(text_bytes) & 0xFF]) + text_bytes

    # Packet 2: Pagination state [0x4E, seq, total, current, status, 0, 0, page, max, ...text]
    pagination_pkt = build_text_packet(
        text=text,
        seq=page_number - 1,
        total_pages=max_pages,
        current_page=page_number,
        max_pages=max_pages,
        status=DisplayStatus.SIMPLE_TEXT,
    )

    for glass in (manager.left_glass, manager.right_glass):
        if glass and glass.client.is_connected:
            await glass.send(display_pkt)
            await asyncio.sleep(0.05)
            await glass.send(pagination_pkt)
            await asyncio.sleep(0.05)


async def step_text_page(manager: "GlassesManager", forward: bool) -> None:
    """Advance or rewind current text page with debounce."""
    global _text_session

    now = asyncio.get_event_loop().time()
    if now - _text_session.last_advance < 0.5:
        return
    _text_session.last_advance = now

    pages = _text_session.pages
    if not pages:
        return

    next_idx = _text_session.current + (1 if forward else -1)
    next_idx = max(0, min(next_idx, _text_session.total - 1))
    if next_idx == _text_session.current:
        return

    _text_session.current = next_idx
    await send_page(manager, pages[next_idx], next_idx + 1, _text_session.total)


# ── Image Pipeline ────────────────────────────────────────────────────────────

def stereo_pair(
    layers: list[tuple[bytes, float]],
    max_disparity: int = 10,
) -> tuple[bytes, bytes]:
    """
    Compose left/right stereo BMPs from image layers with depth.

    Args:
        layers: list of (image_bytes, z_depth) where z ∈ [0.0, 1.0]
        max_disparity: max pixel shift for full depth range

    Returns:
        (left_bmp, right_bmp): ready-to-send 1-bit BMPs
    """
    # Convert images to BMPs (inverted for glasses polarity)
    bmp_layers = [(to_bmp_bytes(img, invert=True), z) for img, z in layers]

    # Compute left/right depth offsets
    left_layers, right_layers = compute_depth(bmp_layers, max_disparity)

    # Blend layers using AND logic
    left_bmp = compose_layers(left_layers)
    right_bmp = compose_layers(right_layers)

    return left_bmp, right_bmp


async def send_bmp_to_glass(glass: Optional[Glass], bmp_bytes: bytes) -> bool:
    """
    Send a display-ready BMP to one glass with frame handshake.

    Args:
        glass: Glass instance (left or right)
        bmp_bytes: 1-bit BMP data

    Returns:
        True if all frames + ACK + CRC verified; False otherwise.
    """
    if not glass or not glass.client.is_connected:
        return False

    try:
        # Build frames and send with 2ms spacing
        frames = build_frames(bmp_bytes)
        for frame in frames:
            await glass.client.write_gatt_char(glass.uart_tx, frame, response=False)
            await asyncio.sleep(0.002)

        # Verify end-of-transfer ACK (expect 0xC9 at byte 1)
        if not await verify_ack(glass, BMP_END_CMD, response_byte_idx=1):
            logger.warning(f"End ACK failed on {glass.name}")
            return False

        # Verify CRC (expect 0xC9 at byte 5)
        crc_cmd = build_crc_cmd(bmp_bytes)
        if not await verify_ack(glass, crc_cmd, response_byte_idx=5):
            logger.warning(f"CRC ACK failed on {glass.name}")
            return False

        # Send display complete to dismiss overlay
        await glass.client.write_gatt_char(glass.uart_tx, DISPLAY_COMPLETE, response=False)
        logger.info(f"Image sent successfully to {glass.name}")
        return True

    except Exception as e:
        logger.error(f"Image send error on {glass.name}: {e}")
        return False


# ── ACK Verification (for image transfers) ────────────────────────────────────

async def verify_ack(glass: Glass, cmd: bytes, response_byte_idx: int, timeout: float = 3.0) -> bool:
    """Send command to glass and verify ACK response at resp_byte_idx."""
    q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
    original_handler = glass.notification_handler

    async def _capture(g, sender, data: bytes) -> None:
        if q.empty():
            await q.put(data)

    glass.notification_handler = _capture
    try:
        await glass.client.write_gatt_char(glass.uart_tx, cmd, response=True)
        data = await asyncio.wait_for(q.get(), timeout=timeout)
        return len(data) > response_byte_idx and data[response_byte_idx] == Response.ACK
    except (asyncio.TimeoutError, Exception):
        return False
    finally:
        glass.notification_handler = original_handler

"""
Display service implementation for G1 glasses
"""
import asyncio
import io
import time
import zlib
from bleak import BleakClient
from typing import List, Optional
from PIL import Image, ImageOps
from utils.logger import setup_logger
from utils.constants import UUIDS

# Image transmission constants
_IMG_W = 576
_IMG_H = 136
_PACKET_SIZE = 194
_BMP_ADDRESS = bytes([0x00, 0x1C, 0x00, 0x00])


def _png_to_bmp_bytes(png_path: str) -> bytes:
    """Convert any PNG to a 1-bit 576×136 BMP, letterboxed on a black canvas."""
    img = Image.open(png_path).convert('L')
    img.thumbnail((_IMG_W, _IMG_H), Image.LANCZOS)
    canvas = Image.new('L', (_IMG_W, _IMG_H), 0)
    canvas.paste(img, ((_IMG_W - img.width) // 2, (_IMG_H - img.height) // 2))
    canvas = ImageOps.invert(canvas)
    bmp_img = canvas.point(lambda p: 255 if p > 64 else 0).convert('1')
    buf = io.BytesIO()
    bmp_img.save(buf, format='BMP')
    return buf.getvalue()


def _build_image_frames(bmp_data: bytes) -> List[bytes]:
    """Wrap 194-byte BMP chunks in the 0x15 protocol frame."""
    frames = []
    offset = 0
    seq = 0
    while offset < len(bmp_data):
        chunk = bmp_data[offset: offset + _PACKET_SIZE]
        header = bytes([0x15, seq & 0xFF]) + (_BMP_ADDRESS if seq == 0 else b'')
        frames.append(header + chunk)
        offset += _PACKET_SIZE
        seq += 1
    return frames


def _crc_command(bmp_data: bytes) -> bytes:
    """CRC32 over storage address + BMP data, prefixed with command 0x16."""
    crc = zlib.crc32(_BMP_ADDRESS + bmp_data) & 0xFFFFFFFF
    return bytes([0x16,
                  (crc >> 24) & 0xFF,
                  (crc >> 16) & 0xFF,
                  (crc >> 8) & 0xFF,
                  crc & 0xFF])

class DisplayService:
    """Handles text and image display"""
    
    # Constants from documentation
    #MAX_WIDTH_PIXELS = 488
    #FONT_SIZE = 21
    LINES_PER_SCREEN = 5
    CHARS_PER_LINE = 55  # Slightly reduced from 60 to give some margin for word wrapping
    MAX_TEXT_LENGTH = CHARS_PER_LINE * LINES_PER_SCREEN  # About 275 characters
    
    def __init__(self, connector):
        self.connector = connector
        self.logger = setup_logger()
        self._current_text = None  # Track currently displayed text
        
    def _split_text_into_chunks(self, text: str) -> List[str]:
        """Split text into screen-sized chunks, preserving word boundaries"""
        chunks = []
        lines = []
        current_line = []
        current_length = 0
        
        words = text.split()
        
        for word in words:
            word_length = len(word)
            # Check if adding this word would exceed line length
            if current_length + word_length + (1 if current_line else 0) > self.CHARS_PER_LINE:
                # Save current line and start new one
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_length = word_length
            else:
                current_line.append(word)
                current_length += word_length + (1 if current_line else 0)
        
        # Add last line if exists
        if current_line:
            lines.append(' '.join(current_line))
        
        # Combine lines into chunks that fit on screen
        current_chunk = []
        for line in lines:
            if len(current_chunk) >= self.LINES_PER_SCREEN:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
            current_chunk.append(line)
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        return chunks

    def validate_text(self, text: str) -> bool:
        """Validate text length and content"""
        if not text:
            raise ValueError("Text cannot be empty")
        return True

    async def send_text_sequential(self, text: str, hold_time: Optional[int] = None, show_exit: bool = True):
        """Send text to both glasses in sequence with acknowledgment"""
        # Keep existing connection checks
        if not self.connector.left_client.is_connected or not self.connector.right_client.is_connected:
            self.logger.error("One or both glasses disconnected. Please reconnect.")
            return False

        # Quick validation
        if not text:
            raise ValueError("Text cannot be empty")
            
        # Only chunk if text exceeds display limits
        chunks = self._split_text_into_chunks(text)
        text_to_send = chunks[0]  # Get first chunk with line breaks
            
        # Prepare command once for both glasses
        command = bytearray([
            0x4E,       # Text command
            0x00,       # Sequence number
            0x01,       # Total packages
            0x00,       # Current package
            0x71,       # Screen status (0x70 Text Show + 0x01 New Content)
            0x00, 0x00, # Character position
            0x00,       # Current page
            0x01,       # Max pages
        ])
        command.extend(text_to_send.encode('utf-8'))
        
        try:
            # Send to both glasses simultaneously
            tasks = [
                self.connector.uart_service.send_command_with_retry(self.connector.left_client, command),
                self.connector.uart_service.send_command_with_retry(self.connector.right_client, command)
            ]
            results = await asyncio.gather(*tasks)
            
            if all(results):
                if hold_time:
                    await asyncio.sleep(hold_time)
                    if show_exit:
                        await self.show_exit_message()
                return True
            else:
                self.logger.error("Failed to send to one or both glasses")
                return False
                
        except Exception as e:
            self.logger.error(f"Error sending text: {e}")
            return False

    async def display_text(self, text: str, hold_time: Optional[int] = None):
        """Display a single text with optional hold time"""
        self.validate_text(text)
        
        if len(text) <= self.MAX_TEXT_LENGTH:
            return await self.send_text_sequential(text, hold_time)
        else:
            self.logger.info("Text exceeds screen size, splitting into chunks...")
            chunks = self._split_text_into_chunks(text)
            return await self.display_text_sequence(chunks, hold_time)

    async def display_text_sequence(self, texts: List[str], hold_time: Optional[int] = 5):
        """Display a sequence of texts with specified hold time"""
        if not texts:
            raise ValueError("Text sequence cannot be empty")
            
        # Validate all texts first
        for text in texts:
            self.validate_text(text)
            if len(text) > self.MAX_TEXT_LENGTH:
                raise ValueError(f"Text exceeds maximum length of {self.MAX_TEXT_LENGTH} characters: {text[:50]}...")
        
        # Display each text in sequence
        for i, text in enumerate(texts, 1):
            self.logger.info(f"Displaying text {i} of {len(texts)}")
            show_exit = (i == len(texts))  # Only show exit on last text
            if not await self.send_text_sequential(text, hold_time, show_exit=show_exit):
                return False
                
        return True

    async def show_exit_message(self):
        """Display exit message and wait for user action"""
        if self._current_text != "Activity completed, double-tap to exit":
            await self.send_text_sequential("Activity completed, double-tap to exit", hold_time=3)

    async def send_image(self, png_path: str) -> bool:
        """Convert a PNG to a 1-bit 576×136 BMP and transmit it to both glasses.

        Protocol (per G1 documentation):
          1. Data frames (0x15): sent write-without-response for throughput, with a
             2ms inter-packet sleep to avoid overflowing the peripheral RX buffer.
          2. End command [0x20, 0x0D, 0x0E]: write-with-response (confirmed).
          3. CRC32 command [0x16, ...]: write-with-response (confirmed).
        Both glasses are sent concurrently — the protocol explicitly supports this.
        """
        if not self.connector.left_client or not self.connector.right_client:
            self.logger.error("Glasses not connected")
            return False

        t_convert = time.perf_counter()
        try:
            bmp_data = _png_to_bmp_bytes(png_path)
        except Exception as e:
            self.logger.error(f"Failed to convert image: {e}")
            return False
        self.logger.info(f"Image converted — {time.perf_counter() - t_convert:.3f}s")

        frames = _build_image_frames(bmp_data)
        end_cmd = bytes([0x20, 0x0D, 0x0E])
        crc_cmd = _crc_command(bmp_data)
        self.logger.info(f"Sending {len(frames)} packets to both glasses concurrently...")

        async def _send_to(side: str, client):
            t0 = time.perf_counter()
            for frame in frames:
                await client.write_gatt_char(UUIDS.UART_TX, frame, response=False)
                await asyncio.sleep(0.002)
            t_frames = time.perf_counter() - t0

            t0 = time.perf_counter()
            await client.write_gatt_char(UUIDS.UART_TX, end_cmd, response=True)
            t_end = time.perf_counter() - t0

            t0 = time.perf_counter()
            await client.write_gatt_char(UUIDS.UART_TX, crc_cmd, response=True)
            t_crc = time.perf_counter() - t0

            return side, t_frames, t_end, t_crc

        t_total = time.perf_counter()
        try:
            results = await asyncio.gather(
                _send_to("left",  self.connector.left_client),
                _send_to("right", self.connector.right_client),
            )
        except Exception as e:
            self.logger.error(f"Image send failed: {e}")
            return False

        total = time.perf_counter() - t_total
        for side, t_frames, t_end, t_crc in results:
            self.logger.info(
                f"[{side}]  frames {t_frames:.3f}s | end cmd {t_end:.3f}s | CRC {t_crc:.3f}s"
            )
        self.logger.info(f"Image sent successfully — total {total:.3f}s")
        return True
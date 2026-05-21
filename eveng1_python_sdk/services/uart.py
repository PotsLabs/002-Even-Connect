"""UART service for G1 glasses"""
import asyncio
from typing import Optional, Dict, Any, Callable
from bleak import BleakClient
from utils.constants import UUIDS, EventCategories
import time

class UARTService:
    """Handles UART communication with G1 glasses"""
    
    def __init__(self, connector):
        """Initialize UART service"""
        self.connector = connector
        self.logger = connector.logger
        self._notification_callbacks = []
        self._shutting_down = False

    async def send_command_with_retry(self, client: BleakClient, data: bytes, retries: int = 3) -> bool:
        """Send command with retry logic similar to official app"""
        for attempt in range(retries):
            try:
                await client.write_gatt_char(UUIDS.UART_TX, data, response=True)
                self.logger.debug(f"Command sent successfully on attempt {attempt + 1}")
                return True
            except Exception as e:
                self.logger.warning(f"Command failed on attempt {attempt + 1}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(0.5)  # Wait before retry
        return False
            
    async def start_notifications(self, client: BleakClient, side: str):
        """Start UART notifications for a client"""
        try:
            await client.start_notify(
                UUIDS.UART_RX,
                lambda _, data: asyncio.create_task(
                    self._handle_notification(side, data)
                )
            )
            self.logger.debug(f"Started UART notifications for {side} glass")
            
        except Exception as e:
            self.logger.error(f"Error starting notifications for {side} glass: {e}")
            raise
            
    async def _handle_notification(self, side: str, data: bytes):
        """Process incoming UART notification"""
        try:
            if self._shutting_down:  # Add early return if shutting down
                return
                
            if not data:
                return

            # Log raw data at debug level
            self.logger.debug(f"Received from {side}: {data.hex()}")
            notification_type = data[0]
            
            # Process based on notification type
            if notification_type == EventCategories.STATE_CHANGE:
                await self.connector.state_manager.process_raw_state(data, side)
            elif notification_type == EventCategories.HEARTBEAT:
                await self.connector.health_monitor.process_heartbeat(side, time.time())
                
            # Forward to event service if not shutting down
            if not self._shutting_down:
                await self.connector.event_service.process_notification(side, data)
                
        except Exception as e:
            if not self._shutting_down:  # Only log errors if not shutting down
                self.logger.error(f"Error handling notification: {e}")

    def add_notification_callback(self, callback: Callable):
        """Add callback for notifications"""
        if callback not in self._notification_callbacks:
            self._notification_callbacks.append(callback)

    def remove_notification_callback(self, callback: Callable):
        """Remove callback for notifications"""
        if callback in self._notification_callbacks:
            self._notification_callbacks.remove(callback)

    async def stop_notifications(self, client: BleakClient) -> None:
        """Stop notifications for UART service"""
        self._shutting_down = True  # Set shutdown flag first
        try:
            await client.stop_notify(UUIDS.UART_RX)
            self.logger.debug("Stopped UART notifications")
        except Exception as e:
            if "17" not in str(e):  # Ignore error code 17 during disconnect
                self.logger.error(f"Error stopping notifications: {e}") 
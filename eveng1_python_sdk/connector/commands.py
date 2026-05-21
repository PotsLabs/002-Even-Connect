"""
Command handling for G1 glasses
"""
import asyncio
import time
from typing import Dict, Any, Optional, Tuple
from bleak import BleakClient
from utils.constants import UUIDS, COMMANDS, EventCategories

class CommandManager:
    """Manages command queuing and execution"""
    
    def __init__(self, connector):
        self.connector = connector
        self.logger = connector.logger
        self._command_lock = asyncio.Lock()
        self._command_queue = asyncio.Queue()
        self._command_task = None
        self._heartbeat_task = None
        self._heartbeat_seq = 0
        self.last_heartbeat = None
        self.heartbeat_interval = 8.0  # Default interval

    async def start(self):
        """Start command processing"""
        if not self._command_task:
            self._command_task = asyncio.create_task(self._process_command_queue())
        if not self._heartbeat_task:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self):
        """Stop command processing"""
        if self._command_task:
            self._command_task.cancel()
            try:
                await self._command_task
            except asyncio.CancelledError:
                pass
            self._command_task = None
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def send_command(self, client: BleakClient, command: bytes, 
                          expect_response: bool = False, 
                          timeout: float = 2.0) -> Optional[Tuple[bytes, int]]:
        """Send command and optionally wait for response"""
        try:
            await self._command_queue.put((command, client))
            
            if expect_response:
                # Wait for response through event service
                response = await self._wait_for_response(command[0], timeout)
                if response:
                    return response.raw_data, response.raw_data[0]
            return None
            
        except Exception as e:
            self.logger.error(f"Error sending command: {e}")
            return None

    async def _wait_for_response(self, command_type: int, timeout: float) -> Optional[Any]:
        """Wait for command response"""
        try:
            # Create future for response
            future = asyncio.Future()
            
            def response_handler(data: bytes, context: Any):
                if data[0] in [EventCategories.COMMAND_RESPONSE, EventCategories.ERROR_RESPONSE]:
                    future.set_result(context)
            
            # Subscribe to raw events temporarily
            self.connector.event_service.subscribe_raw(EventCategories.RESPONSE, response_handler)
            
            try:
                return await asyncio.wait_for(future, timeout)
            except asyncio.TimeoutError:
                self.logger.warning(f"Command response timeout for type 0x{command_type:02x}")
                return None
            finally:
                self.connector.event_service.unsubscribe(response_handler)
                
        except Exception as e:
            self.logger.error(f"Error waiting for response: {e}")
            return None

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

    async def send_heartbeat(self, client: BleakClient) -> None:
        """Send heartbeat command with proper structure"""
        try:
            await self.send_command_with_retry(client, COMMANDS.HEARTBEAT_CMD)  # Restored original command
            self.last_heartbeat = time.time()
            # Log heartbeat to file only
            self.logger.debug(f"Heartbeat sent")
            
        except Exception as e:
            self.logger.error(f"Error sending heartbeat: {e}")
            raise

    async def _heartbeat_loop(self):
        """Maintain heartbeat with both glasses"""
        while True:
            try:
                # Send to both glasses
                for client in [self.connector.left_client, self.connector.right_client]:
                    if client and client.is_connected:
                        await self.send_heartbeat(client)
                        
                await asyncio.sleep(self.heartbeat_interval)
                
            except asyncio.CancelledError:
                self.logger.debug("Heartbeat loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(1)

    async def _process_command_queue(self):
        """Process commands in queue to prevent conflicts"""
        while True:
            try:
                command, client = await self._command_queue.get()
                async with self._command_lock:
                    await self.send_command_with_retry(client, command)
                await asyncio.sleep(0.1)  # Small delay between commands
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing command queue: {e}")
                await asyncio.sleep(1)

    async def queue_command(self, command: bytes, client: BleakClient):
        """Queue a command for processing"""
        await self._command_queue.put((command, client)) 

    def start_heartbeat(self):
        """Start the heartbeat task"""
        if not self._heartbeat_task:
            self.logger.debug("Starting heartbeat task")
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def stop_heartbeat(self):
        """Stop the heartbeat task"""
        if self._heartbeat_task:
            self.logger.debug("Stopping heartbeat task")
            self._heartbeat_task.cancel()
            self._heartbeat_task = None 
"""
Bluetooth specific functionality for G1 glasses
"""
import asyncio
import time
from bleak import BleakClient, BleakScanner
from typing import Optional
from rich.table import Table

from utils.constants import (
    UUIDS, COMMANDS, EventCategories, StateEvent, 
    StateColors, StateDisplay, ConnectionState
)
from utils.logger import user_guidance
from connector.pairing import PairingManager

class BLEManager:
    """Manages BLE connections for G1 glasses"""
    
    def __init__(self, connector):
        """Initialize BLE manager"""
        self.connector = connector
        self.logger = connector.logger
        self._error_count = 0
        self._last_error = None
        self._silent_mode = False
        self._last_heartbeat = None
        self._monitoring_task = None
        self.pairing_manager = PairingManager(connector)
        self._shutting_down = False

    async def scan_for_glasses(self) -> bool:
        """Scan for G1 glasses and save their addresses"""
        try:
            self.connector.state_manager.set_connection_state(ConnectionState.SCANNING)
            self.logger.info("Starting scan for glasses...")
            user_guidance(self.logger, "\n[yellow]Scanning for G1 glasses...[/yellow]")
            
            left_found = right_found = False
            devices = await BleakScanner.discover(timeout=15.0)
            
            # Log all found devices for debugging
            self.logger.debug("Found devices:")
            for device in devices:
                self.logger.debug(f"  {device.name} ({device.address})")
                if device.name:
                    if "_L_" in device.name:
                        self.connector.config.left_address = device.address
                        self.connector.config.left_name = device.name
                        left_found = True
                        user_guidance(self.logger, f"[green]Found left glass: {device.name}[/green]")
                    elif "_R_" in device.name:
                        self.connector.config.right_address = device.address
                        self.connector.config.right_name = device.name
                        right_found = True
                        user_guidance(self.logger, f"[green]Found right glass: {device.name}[/green]")

            if not (left_found and right_found):
                self.connector.state_manager.set_connection_state(ConnectionState.DISCONNECTED)
                user_guidance(self.logger, "\n[yellow]Glasses not found. Please ensure:[/yellow]")
                user_guidance(self.logger, "1. Glasses are properly prepared and seated in the powered cradle:")
                user_guidance(self.logger, "   - First close the left temple/arm")
                user_guidance(self.logger, "   - Then close the right temple/arm")
                user_guidance(self.logger, "   - Place glasses in cradle with both arms closed")
                user_guidance(self.logger, "2. Bluetooth is enabled on your computer (sometimes wifi on your computer can interfere with bluetooth)")
                user_guidance(self.logger, "3. Bluetooth is disabled on other nearby devices that have paired with the glasses")
                user_guidance(self.logger, "4. Glasses have not been added to Windows Bluetooth manager (remove if present)")
                user_guidance(self.logger, "5. If still not working, connect with the offical app and restart the glasses, then try again.")
                return False

            self.connector.config.save()
            return True

        except Exception as e:
            self.logger.error(f"Scan failed: {e}")
            self.connector.state_manager.set_connection_state(ConnectionState.DISCONNECTED)
            user_guidance(self.logger, f"\n[red]Error during scan: {e}[/red]")
            return False

    async def connect_to_glasses(self) -> bool:
        """Connect to both glasses"""
        try:
            self.logger.info("[yellow]Connecting to G1, please wait...[/yellow]")
            
            self.connector.state_manager.set_connection_state(ConnectionState.CONNECTING)
            
            # First verify/attempt pairing
            if not await self.pairing_manager.verify_pairing():
                self.logger.error("[red]Error connecting, retrying...[/red]")
                self.connector.state_manager.set_connection_state(ConnectionState.DISCONNECTED)
                return False

            # Connect to both glasses
            success = await self._connect_glass('left') and await self._connect_glass('right')
            
            if success:
                # Start command manager and heartbeat
                await self.connector.command_manager.start()
                self.logger.info("[green]Connected successfully[/green]")
                self.connector.state_manager.set_connection_state(ConnectionState.CONNECTED)
                # Start monitoring
                self._monitoring_task = asyncio.create_task(self._monitor_connection_quality())
            else:
                self.logger.error("[red]Error connecting, retrying...[/red]")
                self.connector.state_manager.set_connection_state(ConnectionState.DISCONNECTED)
                
            return success
            
        except Exception as e:
            self.logger.error(f"[red]Connection failed: {e}[/red]")
            self.connector.state_manager.set_connection_state(ConnectionState.DISCONNECTED)
            return False

    async def disconnect(self):
        """Disconnect from glasses"""
        try:
            self._shutting_down = True
            
            # Cancel monitoring task
            if self._monitoring_task:
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass
                self._monitoring_task = None
                
            # Stop command manager
            await self.connector.command_manager.stop()
            
            # Disconnect both glasses
            for side in ['left', 'right']:
                client = getattr(self.connector, f"{side}_client", None)
                if client and client.is_connected:
                    await client.disconnect()
                    setattr(self.connector, f"{side}_client", None)
                    
            self.connector.state_manager.set_connection_state(ConnectionState.DISCONNECTED)
            
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")

    def _create_status_table(self) -> Table:
        """Create status table with all required information"""
        table = Table(box=True, border_style="blue", title="G1 Glasses Status")
        
        # Connection states with colors
        for side in ['Left', 'Right']:
            client = getattr(self.connector, f"{side.lower()}_client", None)
            status = "[green]Connected[/green]" if client and client.is_connected else "[red]Disconnected[/red]"
            table.add_row(f"{side} Glass", status)
            
        # Physical state with appropriate color
        system_name, _ = StateEvent.get_physical_state(self.connector.state_manager._physical_state)
        state_colors = {
            "WEARING": "green",
            "TRANSITIONING": "yellow",
            "CRADLE": "blue",
            "CRADLE_CHARGING": "yellow",
            "CRADLE_FULL": "bright_blue",
            "UNKNOWN": "red"
        }
        color = state_colors.get(system_name, "white")
        state = self.connector.state_manager.physical_state
        table.add_row("State", f"[{color}]{state}[/{color}]")
        
        # Add last interaction if any
        interaction = self.connector.state_manager.last_interaction
        if interaction and interaction != "None":
            table.add_row("Last Interaction", f"[{StateColors.HIGHLIGHT}]{interaction}[/{StateColors.HIGHLIGHT}]")
        
        # Last heartbeat timing
        if self._last_heartbeat:
            elapsed = time.time() - self._last_heartbeat
            table.add_row("Last Heartbeat", f"{elapsed:.1f}s ago")
        
        # Silent mode status
        table.add_row("Silent Mode", 
                     f"[{StateColors.WARNING}]On[/{StateColors.WARNING}]" if self._silent_mode 
                     else f"[{StateColors.NEUTRAL}]Off[/{StateColors.NEUTRAL}]")
        
        # Error information
        if self._error_count > 0:
            table.add_row("Errors", f"[{StateColors.ERROR}]{self._error_count}[/{StateColors.ERROR}]")
            if self._last_error:
                table.add_row("Last Error", f"[{StateColors.ERROR}]{self._last_error}[/{StateColors.ERROR}]")
        
        return table

    async def _verify_connection(self, client: BleakClient, glass_name: str) -> bool:
        """Verify connection and services are available"""
        try:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.logger.debug(f"Verifying {glass_name} connection...")
                    
                    # Get UART service
                    uart_service = client.services.get_service(UUIDS.UART_SERVICE)
                    if not uart_service:
                        if attempt < max_retries - 1:
                            self.logger.debug(f"UART service not found for {glass_name}, retrying...")
                            continue
                        self.logger.error(f"UART service not found for {glass_name}")
                        return False
                    
                    # Verify characteristics
                    uart_tx = uart_service.get_characteristic(UUIDS.UART_TX)
                    uart_rx = uart_service.get_characteristic(UUIDS.UART_RX)
                    
                    if not uart_tx or not uart_rx:
                        if attempt < max_retries - 1:
                            self.logger.debug(f"UART characteristics not found for {glass_name}, retrying...")
                            continue
                        self.logger.error(f"UART characteristics not found for {glass_name}")
                        return False
                    
                    self.logger.info(f"{glass_name} connection verified successfully")
                    return True
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.logger.debug(f"Error verifying {glass_name} connection (attempt {attempt + 1}): {e}")
                        await asyncio.sleep(1)
                        continue
                    self.logger.error(f"Error verifying {glass_name} connection: {e}")
                    return False
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error in verification process for {glass_name}: {e}")
            return False

    async def send_heartbeat(self, client: BleakClient) -> None:
        """Send heartbeat command to specified glass"""
        await self.connector.command_manager.send_heartbeat(client)

    async def reconnect(self) -> bool:
        """Reconnect to both glasses"""
        try:
            await self.disconnect()
            return await self.connect_to_glasses()
        except Exception as e:
            self.logger.error(f"Reconnection failed: {e}")
            return False

    async def _monitor_connection_quality(self):
        """Monitor basic connection status"""
        self.logger.debug("Starting connection monitoring")
        
        while not self._shutting_down:
            try:
                # Check if clients are still connected
                for side in ['left', 'right']:
                    if self._shutting_down:
                        return
                        
                    client = getattr(self.connector, f"{side}_client", None)
                    if client and not client.is_connected:
                        self.logger.warning(f"{side.title()} glass disconnected")
                        self._error_count += 1
                        self._last_error = f"{side.title()} glass disconnected"
                
                await asyncio.sleep(10)
                    
            except Exception as e:
                if not self._shutting_down:
                    self._error_count += 1
                    self._last_error = str(e)
                    self.logger.error(f"Error in connection monitoring: {e}")
                await asyncio.sleep(10)

    async def verify_connection(self, client: BleakClient) -> bool:
        """Verify connection is working with heartbeat"""
        try:
            # Send initial heartbeat
            await self.send_heartbeat(client)
            
            # Wait for response
            start_time = time.time()
            while time.time() - start_time < 2.0:  # 2 second timeout
                if self.connector.uart_service.last_heartbeat and \
                   self.connector.uart_service.last_heartbeat > start_time:
                    return True
                await asyncio.sleep(0.1)
            
            self.logger.warning("Connection verification failed - no heartbeat response")
            return False
            
        except Exception as e:
            self.logger.error(f"Error verifying connection: {e}")
            return False 

    def _update_connection_quality(self, side: str, rssi: Optional[int] = None, error: bool = False):
        """Update connection quality metrics"""
        if side not in self.connector._connection_quality:
            self.connector._connection_quality[side] = {'rssi': None, 'errors': 0}
            
        if rssi is not None:
            self.connector._connection_quality[side]['rssi'] = rssi
            
        if error:
            self.connector._connection_quality[side]['errors'] += 1 

    async def start_monitoring(self):
        """Start connection quality monitoring"""
        if not self._monitoring_task:
            self.logger.info("Starting connection quality monitoring")
            self._monitoring_task = asyncio.create_task(self._monitor_connection_quality())

    async def stop_monitoring(self):
        """Stop connection quality monitoring"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None 

    async def _heartbeat_loop(self):
        """Maintain connection with regular heartbeats"""
        seq = 0
        while True:
            try:
                if self.connector.left_client and self.connector.right_client:
                    seq = (seq + 1) & 0xFF
                    data = bytes([0x25, 0x06, 0x00, seq, 0x04, seq])
                    
                    # Send to both glasses in sequence
                    await self.send_command(self.connector.left_client, data)
                    self.logger.debug(f"Heartbeat sent to Left: {data.hex()}")
                    await asyncio.sleep(0.2)
                    
                    await self.send_command(self.connector.right_client, data)
                    self.logger.debug(f"Heartbeat sent to Right: {data.hex()}")
                    
                    self._last_heartbeat = time.time()
                    await asyncio.sleep(self.connector.config.heartbeat_interval)
                    
            except Exception as e:
                self._error_count += 1
                self._last_error = f"Heartbeat failed: {e}"
                self.logger.error(self._last_error)
                await asyncio.sleep(2)

    async def _handle_disconnect(self, side: str):
        """Handle disconnection and attempt reconnection"""
        if self._shutting_down:
            return False
            
        self.logger.warning(f"{side.title()} glass disconnected")
        self._error_count += 1
        self._last_error = f"{side.title()} glass disconnected"

        for attempt in range(self.connector.config.reconnect_attempts):
            if self._shutting_down:
                return False
                
            try:
                self.logger.info(f"Attempting to reconnect {side} glass (attempt {attempt + 1})")
                if await self._connect_glass(side):
                    self.logger.info(f"Successfully reconnected {side} glass")
                    return True
                await asyncio.sleep(self.connector.config.reconnect_delay)
            except Exception as e:
                self.logger.error(f"Reconnection attempt {attempt + 1} failed: {e}")
        
        return False

    async def _connect_glass(self, side: str) -> bool:
        """Connect to a single glass with disconnect callback"""
        try:
            address = getattr(self.connector.config, f"{side}_address")
            if not address:
                self.logger.error(f"No {side} glass address configured")
                return False

            for attempt in range(self.connector.config.reconnect_attempts):
                try:
                    self.logger.info(f"Attempting to connect {side} glass (attempt {attempt + 1})")
                    client = BleakClient(
                        address,
                        disconnected_callback=lambda c: asyncio.create_task(self._handle_disconnect(side))
                    )
                    
                    await client.connect(timeout=self.connector.config.connection_timeout)
                    if client.is_connected:
                        setattr(self.connector, f"{side}_client", client)
                        await self.connector.uart_service.start_notifications(client, side)
                        return True
                        
                    await asyncio.sleep(self.connector.config.reconnect_delay)
                    
                except Exception as e:
                    self.logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                    if attempt < self.connector.config.reconnect_attempts - 1:
                        await asyncio.sleep(self.connector.config.reconnect_delay)
                        
            return False
            
        except Exception as e:
            self.logger.error(f"Error connecting to {side} glass: {e}")
            return False 

    def set_silent_mode(self, enabled: bool):
        """Toggle silent mode"""
        self._silent_mode = enabled
        # Log the change
        self.logger.info(f"Silent mode {'enabled' if enabled else 'disabled'}")
        # Update the status immediately
        self.connector.state_manager.update_status(self.get_status_data())

    def get_status_data(self) -> dict:
        """Get current status data for external display"""
        return {
            'connection': {
                'left': {
                    'connected': bool(self.connector.left_client and self.connector.left_client.is_connected),
                    'errors': self._error_count,
                    'last_error': self._last_error
                },
                'right': {
                    'connected': bool(self.connector.right_client and self.connector.right_client.is_connected),
                    'errors': self._error_count,
                    'last_error': self._last_error
                }
            },
            'heartbeat': self._last_heartbeat,
            'silent_mode': self._silent_mode
        } 
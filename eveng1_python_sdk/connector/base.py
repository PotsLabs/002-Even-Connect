"""
Base connector class for G1 glasses
"""
from rich.console import Console
from rich.live import Live
from rich.table import Table
import os
import time
import logging
import asyncio
from dataclasses import dataclass
from typing import Optional
from bleak import BleakClient

from connector.bluetooth import BLEManager
from connector.pairing import PairingManager
from connector.commands import CommandManager
from services.state import StateManager
from services.uart import UARTService
from services.events import EventService
from services.status import StatusManager
from services.health import HealthMonitor
from utils.logger import setup_logger
from utils.config import Config
from utils.constants import UUIDS, COMMANDS, StateEvent, EventCategories
from services.device import DeviceManager
from services.display import DisplayService

@dataclass
class G1Config:
    """Configuration for G1 glasses SDK"""
    CONFIG_FILE = "g1_config.json"
    
    # Logging configuration
    log_level: str = "INFO"
    log_file: str = "g1_connector.log"
    console_log: bool = True
    
    # Connection configuration
    heartbeat_interval: int = 8  # seconds
    reconnect_attempts: int = 3
    reconnect_delay: float = 1.0  # seconds
    
    # Device information (auto-populated)
    left_address: Optional[str] = None
    right_address: Optional[str] = None
    left_name: Optional[str] = None
    right_name: Optional[str] = None

class G1Connector:
    """Main connector class for G1 glasses"""
    
    def __init__(self, config: Optional[Config] = None):
        """Initialize connector with optional config"""
        # Core initialization
        self.config = config or Config.load()
        self.logger = setup_logger(self.config)
        
        # Initialize Rich console for status display
        self.console = Console()
        
        # Client connections
        self.left_client: Optional[BleakClient] = None
        self.right_client: Optional[BleakClient] = None
        
        # Connection quality tracking
        self._connection_quality = {
            'left': {'rssi': None, 'errors': 0},
            'right': {'rssi': None, 'errors': 0}
        }
        
        # Initialize all services and managers
        self._initialize_services()
        
    def _initialize_services(self):
        """Initialize services in correct order"""
        from connector.bluetooth import BLEManager
        from connector.commands import CommandManager
        from services.events import EventService
        from services.uart import UARTService
        from services.device import DeviceManager
        from services.state import StateManager
        
        # Core services first
        self.state_manager = StateManager(self)
        self.event_service = EventService(self)
        self.health_monitor = HealthMonitor(self)
        
        # Then dependent services
        self.uart_service = UARTService(self)
        self.device_manager = DeviceManager(self)
        self.display = DisplayService(self)  # Add display service
        
        # Finally managers
        self.command_manager = CommandManager(self)
        self.ble_manager = BLEManager(self)
        
        # Initialize Rich console for status display
        self.console = Console()
        
        # Initialize device managers
        self.pairing_manager = PairingManager(self)  # Device pairing
        
        # Set up event subscriptions
        self._setup_event_handlers()

    def _setup_event_handlers(self):
        """Set up core event handlers"""
        # Subscribe to connection state changes
        self.event_service.subscribe_connection(self._handle_connection_state)
        
        # Subscribe to error events
        self.event_service.subscribe_raw(EventCategories.ERROR, self._handle_error_event)
        
        # Subscribe to heartbeat events via health monitor
        self.health_monitor.subscribe_heartbeat(self._handle_heartbeat)

    async def _handle_connection_state(self, state):
        """Handle connection state changes"""
        try:
            # Update connection quality tracking
            if state == "Connected":
                for side in ['left', 'right']:
                    if getattr(self, f"{side}_client"):
                        self._connection_quality[side]['last_connected'] = time.time()
            
            # Update status display if running
            if hasattr(self, 'status_manager'):
                await self.status_manager.update()
                
        except Exception as e:
            self.logger.error(f"Error handling connection state: {e}")

    async def _handle_error_event(self, data, side):
        """Handle error events"""
        try:
            if side in self._connection_quality:
                self._connection_quality[side]['errors'] += 1
        except Exception as e:
            self.logger.error(f"Error handling error event: {e}")

    async def _handle_heartbeat(self, timestamp):
        """Handle heartbeat events"""
        try:
            # Update connection quality via health monitor
            for side in ['left', 'right']:
                if getattr(self, f"{side}_client"):
                    await self.health_monitor.process_heartbeat(side, timestamp)
        except Exception as e:
            self.logger.error(f"Error handling heartbeat: {e}")

    async def connect(self):
        """Connect to glasses"""
        try:
            self.state_manager.connection_state = "Connecting..."
            
            # Check if we need to do initial scanning
            if not self.config.left_address or not self.config.right_address:
                self.logger.info("No saved glasses found. Starting initial scan...")
                if not await self.ble_manager.scan_for_glasses():
                    self.state_manager.connection_state = "Disconnected"
                    return False
            
            # Attempt connection; if it fails, the stored UUID may have changed —
            # clear addresses and re-scan by name before retrying once.
            if not await self.ble_manager.connect_to_glasses():
                self.logger.info("Connection failed, rescanning for glasses...")
                self.config.left_address = None
                self.config.right_address = None
                if not await self.ble_manager.scan_for_glasses():
                    self.state_manager.connection_state = "Disconnected"
                    return False
                if not await self.ble_manager.connect_to_glasses():
                    self.state_manager.connection_state = "Disconnected"
                    return False
            
            self.state_manager.connection_state = "Connected"
            return True
                
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self.state_manager.connection_state = "Disconnected"
            return False

    async def disconnect(self):
        """Disconnect from glasses"""
        try:
            await self.ble_manager.disconnect()
            self.state_manager.connection_state = "Disconnected"
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")

    def get_connection_quality(self, side: str) -> dict:
        """Get connection quality metrics for a side"""
        return self._connection_quality.get(side, {}) 

    async def update_status(self):
        """Update and display current status"""
        try:
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Status", style="dim")
            table.add_column("Value")

            # Add status rows
            table.add_row(
                "Left Glass",
                "Connected" if self.left_client and self.left_client.is_connected else "Disconnected"
            )
            table.add_row(
                "Right Glass",
                "Connected" if self.right_client and self.right_client.is_connected else "Disconnected"
            )
            table.add_row(
                "State",
                self.state_manager.physical_state
            )

            # Add silent mode status if device manager exists
            if hasattr(self, 'device_manager'):
                table.add_row(
                    "Silent Mode",
                    "Enabled" if self.device_manager.silent_mode else "Disabled"
                )

            # Add error counts if any
            left_errors = self._connection_quality['left']['errors']
            right_errors = self._connection_quality['right']['errors']
            if left_errors > 0 or right_errors > 0:
                table.add_row(
                    "Errors",
                    f"Left: {left_errors}, Right: {right_errors}"
                )

            # Clear screen and display new status
            self.console.clear()
            self.console.print("\n[bold]G1 Glasses Status[/bold]")
            self.console.print(table)

        except Exception as e:
            self.logger.error(f"Error updating status: {e}") 